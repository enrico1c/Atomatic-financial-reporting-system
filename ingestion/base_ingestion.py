"""
Base class for all data ingestion modules.
Provides retry logic, caching, and standard save/load helpers.
"""

import time
import json
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod

import pandas as pd
import requests

from config.settings import RAW_DIR
from utils.logger import get_logger


class BaseIngestion(ABC):
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2  # seconds

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.logger = get_logger(f"ingestion.{source_name}")
        self.raw_dir = RAW_DIR / source_name
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    # ── Abstract interface ─────────────────────────────────────────────────────
    @abstractmethod
    def fetch(self) -> dict[str, pd.DataFrame]:
        """Fetch all data for this source. Returns {name: DataFrame}."""
        ...

    # ── HTTP helpers ───────────────────────────────────────────────────────────
    def _get(self, url: str, params: dict = None, **kwargs) -> requests.Response:
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = requests.get(url, params=params, timeout=30, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                self.logger.warning(f"[{self.source_name}] GET attempt {attempt} failed: {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF * attempt)
                else:
                    raise

    # ── Persistence helpers ────────────────────────────────────────────────────
    def save_raw(self, df: pd.DataFrame, name: str) -> Path:
        path = self.raw_dir / f"{name}.csv"
        df.to_csv(path)
        self.logger.debug(f"Saved raw {name} → {path} ({len(df)} rows)")
        return path

    def load_raw(self, name: str) -> pd.DataFrame | None:
        path = self.raw_dir / f"{name}.csv"
        if path.exists():
            return pd.read_csv(path, index_col=0, parse_dates=True)
        return None

    def _stamp(self, name: str):
        """Write a timestamp file to record last successful fetch."""
        stamp = self.raw_dir / f"{name}.stamp"
        stamp.write_text(datetime.utcnow().isoformat())

    def _last_fetched(self, name: str) -> datetime | None:
        stamp = self.raw_dir / f"{name}.stamp"
        if stamp.exists():
            return datetime.fromisoformat(stamp.read_text().strip())
        return None

    def _is_stale(self, name: str, max_age_hours: int = 23) -> bool:
        last = self._last_fetched(name)
        if last is None:
            return True
        age = (datetime.utcnow() - last).total_seconds() / 3600
        return age > max_age_hours
