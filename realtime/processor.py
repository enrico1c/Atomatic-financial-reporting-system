"""
Real-time processor.
Combines live price data with ML predictions and macro context into a
single JSON payload broadcast to WebSocket clients every second.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from config.settings import CLEAN_DIR
from ml.predictor import Predictor
from realtime.data_feed import LiveDataFeed
from utils.logger import get_logger

log = get_logger("realtime.processor")


def _load_latest_macro() -> dict:
    """Load most-recent macro values from the clean CSV (static snapshot)."""
    macro = {}
    path = CLEAN_DIR / "macro_monthly.csv"
    if not path.exists():
        return macro
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        latest = df.iloc[-1].dropna()
        macro = {k: round(float(v), 4) for k, v in latest.items()}
    except Exception as e:
        log.warning(f"Could not load macro data: {e}")
    return macro


class RealtimeProcessor:
    """
    Orchestrates the real-time pipeline:
    1. Receives live price snapshots from LiveDataFeed.
    2. Runs ML predictions via Predictor.
    3. Builds the full output payload.
    4. Notifies registered broadcast callbacks (WebSocket server).
    """

    def __init__(self, feed: LiveDataFeed, predictor: Predictor):
        self.feed = feed
        self.predictor = predictor
        self._macro = _load_latest_macro()
        self._latest_payload: Optional[dict] = None
        self._broadcast_callbacks: list = []
        self._ticker_count = 0

        # Subscribe to feed updates
        feed.subscribe(self._on_feed_update)

    # ── Feed callback ──────────────────────────────────────────────────────────

    async def _on_feed_update(self, snapshot: dict) -> None:
        """Called each time the data feed fetches new prices."""
        payload = self._build_payload(snapshot)
        self._latest_payload = payload
        for cb in self._broadcast_callbacks:
            try:
                await cb(payload)
            except Exception as e:
                log.debug(f"Broadcast callback error: {e}")

    # ── Payload builder ────────────────────────────────────────────────────────

    def _build_payload(self, price_snapshot: dict) -> dict:
        """
        Build the full real-time payload including ML projections.
        This is the canonical structure sent to every WebSocket client.
        """
        now = datetime.now(timezone.utc)
        self._ticker_count += 1

        prices_out = {}
        projections_out = {}

        for ticker, info in price_snapshot.items():
            price = info.get("price")
            change = info.get("change_1m")

            prices_out[ticker] = {
                "price":      round(price, 4) if price is not None else None,
                "change_1m":  round(change * 100, 4) if change is not None else None,  # %
                "data_ts":    info.get("ts"),
                "bars_loaded": info.get("bars"),
            }

            # ML projections from the rolling price window
            win = self.feed.windows.get(ticker)
            if win and len(win) >= 30:
                proj = self.predictor.predict(ticker, win.series)
                if proj:
                    projections_out[ticker] = {
                        "return_1d_pct":        round(proj.get("return_1d", 0) * 100, 3),
                        "return_5d_pct":        round(proj.get("return_5d", 0) * 100, 3),
                        "projected_price_1d":   proj.get("projected_price_1d"),
                        "projected_price_5d":   proj.get("projected_price_5d"),
                        "trend":                proj.get("trend", "neutral"),
                    }

        return {
            "server_ts":   now.isoformat(),
            "update_seq":  self._ticker_count,
            "prices":      prices_out,
            "projections": projections_out,
            "macro":       self._macro,
        }

    # ── Second-by-second broadcast ─────────────────────────────────────────────

    async def run_second_ticker(self) -> None:
        """
        Runs a 1-second timer that re-broadcasts the latest payload to all
        connected clients — even between data feed updates.
        This ensures clients receive a message every single second.
        """
        log.info("Second-ticker started — broadcasting every 1s")
        while True:
            await asyncio.sleep(1)
            if self._latest_payload is not None:
                # Refresh the server timestamp each second
                self._latest_payload["server_ts"] = datetime.now(
                    timezone.utc
                ).isoformat()
                self._latest_payload["update_seq"] += 1
                for cb in self._broadcast_callbacks:
                    try:
                        await cb(self._latest_payload)
                    except Exception as e:
                        log.debug(f"Second-ticker broadcast error: {e}")

    # ── Subscriptions ──────────────────────────────────────────────────────────

    def subscribe_broadcast(self, callback) -> None:
        self._broadcast_callbacks.append(callback)

    @property
    def latest_payload(self) -> Optional[dict]:
        return self._latest_payload
