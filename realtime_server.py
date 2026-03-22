#!/usr/bin/env python3
"""
Start the real-time financial data WebSocket server.

Usage:
    python realtime_server.py                        # default port 8000
    python realtime_server.py --port 9000
    python realtime_server.py --tickers AAPL MSFT   # override tickers
    python realtime_server.py --host 0.0.0.0        # bind all interfaces

After starting:
    Dashboard  →  http://localhost:8000
    WebSocket  →  ws://localhost:8000/ws
    Snapshot   →  http://localhost:8000/api/snapshot
    Health     →  http://localhost:8000/api/health

The server will:
  1. Bootstrap 2 days of 1-minute bars from Yahoo Finance on startup.
  2. Fetch fresh prices every 15 seconds from Yahoo Finance.
  3. Stream the full payload (prices + ML projections + macro) to every
     connected client every second via WebSocket.
  4. Run ML projections if models are trained (python train.py).
"""

import argparse
import os
import sys

import uvicorn

parser = argparse.ArgumentParser(description="Real-time financial WebSocket server")
parser.add_argument("--host",    default="0.0.0.0",  help="Bind host (default: 0.0.0.0)")
parser.add_argument("--port",    default=8000, type=int, help="Port (default: 8000)")
parser.add_argument("--tickers", nargs="+", default=None, help="Override ticker list")
parser.add_argument("--reload",  action="store_true",    help="Hot-reload (dev mode)")
args = parser.parse_args()

if args.tickers:
    os.environ["RT_TICKERS"] = ",".join(args.tickers)

print(f"""
╔══════════════════════════════════════════════════════════╗
║       Financial Real-Time Monitor — Starting             ║
╠══════════════════════════════════════════════════════════╣
║  Dashboard   →  http://{args.host}:{args.port}
║  WebSocket   →  ws://{args.host}:{args.port}/ws
║  Snapshot    →  http://{args.host}:{args.port}/api/snapshot
║  Health      →  http://{args.host}:{args.port}/api/health
╚══════════════════════════════════════════════════════════╝
""")

uvicorn.run(
    "realtime.websocket_server:app",
    host=args.host,
    port=args.port,
    reload=args.reload,
    log_level="info",
)
