"""
Real-time data feed.
Fetches latest market prices from Yahoo Finance on a configurable interval
and maintains an in-memory price window for ML feature generation.
"""

import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd
import yfinance as yf

from utils.logger import get_logger

log = get_logger("realtime.data_feed")

# How many recent data points to keep per ticker (for ML feature window)
PRICE_WINDOW = 120  # ~120 minutes of 1-min bars, or 120 trading days

# How often to actually call the Yahoo Finance API (seconds)
# Yahoo Finance tolerates ~1 call/ticker every 10-15 seconds.
FETCH_INTERVAL_SECONDS = 15


class PriceWindow:
    """Thread-safe rolling window of recent prices for one ticker."""

    def __init__(self, ticker: str, maxlen: int = PRICE_WINDOW):
        self.ticker = ticker
        self._prices: deque = deque(maxlen=maxlen)
        self._timestamps: deque = deque(maxlen=maxlen)
        self._last_update: Optional[datetime] = None

    def push(self, price: float, ts: datetime) -> None:
        self._prices.append(price)
        self._timestamps.append(ts)
        self._last_update = ts

    @property
    def series(self) -> pd.Series:
        return pd.Series(
            list(self._prices),
            index=pd.DatetimeIndex(list(self._timestamps)),
            name=self.ticker,
        )

    @property
    def latest_price(self) -> Optional[float]:
        return self._prices[-1] if self._prices else None

    @property
    def latest_ts(self) -> Optional[datetime]:
        return self._timestamps[-1] if self._timestamps else None

    @property
    def change_1m(self) -> Optional[float]:
        if len(self._prices) < 2:
            return None
        return (self._prices[-1] / self._prices[-2]) - 1

    def __len__(self) -> int:
        return len(self._prices)


class LiveDataFeed:
    """
    Maintains rolling price windows for all tracked tickers.
    Fetches updates from Yahoo Finance on FETCH_INTERVAL_SECONDS cadence.

    The feed fires registered callbacks each time new data arrives.
    The WebSocket server registers itself here to push updates to clients.
    """

    def __init__(self, tickers: list[str]):
        self.tickers = tickers
        self.windows: dict[str, PriceWindow] = {
            t: PriceWindow(t) for t in tickers
        }
        self._callbacks: list[Callable] = []
        self._running = False

        # Bootstrap with 1-minute historical bars so ML has enough data
        self._bootstrap()

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def _bootstrap(self) -> None:
        """Fetch 2 days of 1-min bars to warm up the price windows."""
        log.info("Bootstrapping price windows (2d × 1m bars)…")
        try:
            raw = yf.download(
                self.tickers,
                period="2d",
                interval="1m",
                group_by="ticker",
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                log.warning("Bootstrap returned no data.")
                return

            for ticker in self.tickers:
                try:
                    if len(self.tickers) == 1:
                        close = raw["Close"]
                    else:
                        close = raw[ticker]["Close"]

                    close = close.dropna()
                    for ts, price in close.items():
                        ts_utc = ts.to_pydatetime().replace(tzinfo=timezone.utc)
                        self.windows[ticker].push(float(price), ts_utc)

                    log.info(
                        f"  {ticker}: bootstrapped {len(self.windows[ticker])} bars, "
                        f"latest={self.windows[ticker].latest_price:.4f}"
                    )
                except Exception as e:
                    log.warning(f"  {ticker}: bootstrap failed — {e}")
        except Exception as e:
            log.warning(f"Bootstrap failed: {e}")

    # ── Fetch loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Async loop: fetch new prices every FETCH_INTERVAL_SECONDS,
        then fire callbacks with the updated snapshot.
        """
        self._running = True
        log.info(
            f"Data feed started — fetching every {FETCH_INTERVAL_SECONDS}s "
            f"for {len(self.tickers)} tickers"
        )

        while self._running:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._fetch_latest
                )
                for cb in self._callbacks:
                    try:
                        await cb(self.snapshot())
                    except Exception as e:
                        log.debug(f"Callback error: {e}")
            except Exception as e:
                log.warning(f"Fetch cycle error: {e}")

            await asyncio.sleep(FETCH_INTERVAL_SECONDS)

    def _fetch_latest(self) -> None:
        """Blocking call to yfinance — runs in a thread executor."""
        try:
            raw = yf.download(
                self.tickers,
                period="1d",
                interval="1m",
                group_by="ticker",
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                return

            now = datetime.now(timezone.utc)
            for ticker in self.tickers:
                try:
                    if len(self.tickers) == 1:
                        close = raw["Close"]
                    else:
                        close = raw[ticker]["Close"]

                    close = close.dropna()
                    if close.empty:
                        continue

                    last_ts = close.index[-1].to_pydatetime().replace(
                        tzinfo=timezone.utc
                    )
                    # Only push if this is newer than what we already have
                    current_latest = self.windows[ticker].latest_ts
                    if current_latest is None or last_ts > current_latest:
                        self.windows[ticker].push(float(close.iloc[-1]), last_ts)
                        log.debug(f"{ticker} → {close.iloc[-1]:.4f} @ {last_ts}")
                except Exception as e:
                    log.debug(f"  {ticker}: fetch error — {e}")
        except Exception as e:
            log.warning(f"yfinance fetch error: {e}")

    # ── Snapshot ───────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return current state for all tickers."""
        out = {}
        for ticker, win in self.windows.items():
            out[ticker] = {
                "price":     win.latest_price,
                "change_1m": win.change_1m,
                "ts":        win.latest_ts.isoformat() if win.latest_ts else None,
                "bars":      len(win),
            }
        return out

    # ── Subscriptions ──────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    def stop(self) -> None:
        self._running = False
