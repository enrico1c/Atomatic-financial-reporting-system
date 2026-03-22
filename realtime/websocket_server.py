"""
FastAPI WebSocket server.

Endpoints:
  GET  /              → serves the live dashboard (HTML)
  GET  /api/snapshot  → current state as JSON (one-shot HTTP)
  WS   /ws            → WebSocket stream — sends JSON every second
  GET  /api/health    → health check
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config.settings import PRICE_TICKERS
from ml.predictor import Predictor
from realtime.data_feed import LiveDataFeed
from realtime.processor import RealtimeProcessor
from utils.logger import get_logger

log = get_logger("realtime.server")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(title="Financial Real-Time Stream", version="1.0.0")

# Mount static files (dashboard HTML/CSS/JS)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Global state (initialised in startup) ─────────────────────────────────────
_feed: LiveDataFeed = None
_predictor: Predictor = None
_processor: RealtimeProcessor = None
_connected: Set[WebSocket] = set()


# ── Broadcast helper ───────────────────────────────────────────────────────────

async def _broadcast(payload: dict) -> None:
    """Send JSON payload to all connected WebSocket clients."""
    if not _connected:
        return
    msg = json.dumps(payload)
    dead: Set[WebSocket] = set()
    for ws in list(_connected):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _connected.difference_update(dead)


# ── Startup / shutdown ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    global _feed, _predictor, _processor

    tickers = os.environ.get("RT_TICKERS", ",".join(PRICE_TICKERS)).split(",")
    tickers = [t.strip() for t in tickers if t.strip()]

    log.info(f"Starting real-time server for tickers: {tickers}")

    _feed = LiveDataFeed(tickers)
    _predictor = Predictor(tickers)
    _processor = RealtimeProcessor(_feed, _predictor)
    _processor.subscribe_broadcast(_broadcast)

    # Start background tasks
    asyncio.create_task(_feed.run(), name="data-feed")
    asyncio.create_task(_processor.run_second_ticker(), name="second-ticker")

    log.info("Server ready. Connect at ws://localhost:8000/ws")


@app.on_event("shutdown")
async def shutdown() -> None:
    if _feed:
        _feed.stop()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=FileResponse)
async def dashboard():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"message": "Dashboard not found. Connect via WebSocket at /ws"})


@app.get("/api/health")
async def health():
    return {"status": "ok", "connected_clients": len(_connected)}


@app.get("/api/snapshot")
async def snapshot():
    if _processor is None:
        return JSONResponse({"error": "Server not ready"}, status_code=503)
    payload = _processor.latest_payload
    if payload is None:
        # Return raw feed snapshot if processor hasn't emitted yet
        return JSONResponse(_feed.snapshot() if _feed else {})
    return JSONResponse(payload)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _connected.add(ws)
    client = f"{ws.client.host}:{ws.client.port}"
    log.info(f"WebSocket connected: {client} ({len(_connected)} total)")

    try:
        # Send current snapshot immediately on connect
        if _processor and _processor.latest_payload:
            await ws.send_text(json.dumps(_processor.latest_payload))

        # Keep connection alive; data is pushed via _broadcast
        while True:
            # Wait for client ping (or disconnect)
            data = await asyncio.wait_for(ws.receive_text(), timeout=60)
            if data == "ping":
                await ws.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as e:
        log.debug(f"WebSocket error ({client}): {e}")
    finally:
        _connected.discard(ws)
        log.info(f"WebSocket disconnected: {client} ({len(_connected)} remaining)")
