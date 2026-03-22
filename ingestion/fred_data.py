"""
FRED (Federal Reserve Economic Data) ingestion via direct CSV download.
No API key required for CSV downloads.

URL pattern:
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID

Fetches all series defined in config.settings.FRED_SERIES.

Limitations:
  - FRED may throttle heavy scraping; spacing requests is recommended
  - Some series are revised retroactively (keep raw files for audit)
  - GDP is quarterly; CPI/unemployment are monthly; treasury yields are daily
"""

import time
import io
import pandas as pd

from config.settings import FRED_SERIES, FRED_BASE_URL
from ingestion.base_ingestion import BaseIngestion


class FREDIngestion(BaseIngestion):
    def __init__(self):
        super().__init__("fred")

    # ── Public ─────────────────────────────────────────────────────────────────
    def fetch(self) -> dict[str, pd.DataFrame]:
        results = {}
        for name, series_id in FRED_SERIES.items():
            df = self._fetch_series(name, series_id)
            if df is not None:
                results[name] = df
            time.sleep(0.3)  # polite pacing
        return results

    # ── Internal ────────────────────────────────────────────────────────────────
    def _fetch_series(self, name: str, series_id: str) -> pd.DataFrame | None:
        self.logger.info(f"Fetching FRED series: {series_id} ({name})")
        try:
            resp = self._get(FRED_BASE_URL, params={"id": series_id})
            df = pd.read_csv(io.StringIO(resp.text))
            date_col = next((c for c in df.columns if "date" in c.lower()), None)
            if date_col is None:
                raise ValueError(f"No date column found, got: {list(df.columns)}")
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df.rename(columns={date_col: "date", series_id: name}, inplace=True)
            # FRED uses "." for missing values
            df[name] = pd.to_numeric(df[name], errors="coerce")
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            self.save_raw(df, name)
            self._stamp(name)
            return df
        except Exception as e:
            self.logger.error(f"Failed to fetch FRED {series_id}: {e}")
            cached = self.load_raw(name)
            if cached is not None:
                self.logger.warning(f"Using cached data for {name}")
                return cached
            return None

    def fetch_combined(self) -> pd.DataFrame:
        """Fetch all FRED series and merge into a single wide DataFrame."""
        frames = []
        for name, series_id in FRED_SERIES.items():
            df = self._fetch_series(name, series_id)
            if df is not None:
                frames.append(df)
            time.sleep(0.3)
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames, axis=1)
        combined.sort_index(inplace=True)
        self.save_raw(combined, "combined")
        return combined
