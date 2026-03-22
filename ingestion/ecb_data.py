"""
ECB (European Central Bank) ingestion via the ECB SDMX REST API.
No API key required.

API base: https://data-api.ecb.europa.eu/service/data/{flow}/{key}
Format:   ?format=csvdata

Fetches series defined in config.settings.ECB_SERIES.

Limitations:
  - ECB API returns CSV with metadata rows at top; parsing required
  - Some series have irregular update schedules
  - Rate decision dates may not align with calendar month-end
  - The SDMX key format is strict; wrong keys return 404
"""

import io
import time
import pandas as pd

from config.settings import ECB_SERIES, ECB_API_BASE
from ingestion.base_ingestion import BaseIngestion


class ECBIngestion(BaseIngestion):
    def __init__(self):
        super().__init__("ecb")

    # ── Public ─────────────────────────────────────────────────────────────────
    def fetch(self) -> dict[str, pd.DataFrame]:
        results = {}
        for name, flow_key in ECB_SERIES.items():
            df = self._fetch_series(name, flow_key)
            if df is not None:
                results[name] = df
            time.sleep(0.5)
        return results

    def fetch_combined(self) -> pd.DataFrame:
        frames = []
        for name, flow_key in ECB_SERIES.items():
            df = self._fetch_series(name, flow_key)
            if df is not None:
                frames.append(df[[name]])
            time.sleep(0.5)
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames, axis=1)
        combined.sort_index(inplace=True)
        self.save_raw(combined, "combined")
        return combined

    # ── Internal ────────────────────────────────────────────────────────────────
    def _fetch_series(self, name: str, flow_key: str) -> pd.DataFrame | None:
        flow, key = flow_key.split("/", 1)
        url = f"{ECB_API_BASE}/{flow}/{key}"
        self.logger.info(f"Fetching ECB series: {name} ({flow_key})")
        try:
            resp = self._get(url, params={"format": "csvdata"})
            df = self._parse_ecb_csv(resp.text, name)
            if df is not None and not df.empty:
                self.save_raw(df, name)
                self._stamp(name)
            return df
        except Exception as e:
            self.logger.error(f"ECB fetch failed for {name}: {e}")
            cached = self.load_raw(name)
            if cached is not None:
                self.logger.warning(f"Using cached ECB data for {name}")
                return cached
            return None

    def _parse_ecb_csv(self, text: str, name: str) -> pd.DataFrame | None:
        """
        ECB CSV format includes metadata header rows.
        Actual data rows start after the blank line separator.
        Columns include: KEY, FREQ, ..., TIME_PERIOD, OBS_VALUE
        """
        try:
            df = pd.read_csv(io.StringIO(text), sep=",", low_memory=False)
            # Locate value columns
            if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
                # Try alternative ECB format
                return self._parse_ecb_alt(text, name)

            out = df[["TIME_PERIOD", "OBS_VALUE"]].copy()
            out.rename(columns={"TIME_PERIOD": "date", "OBS_VALUE": name}, inplace=True)
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
            out[name] = pd.to_numeric(out[name], errors="coerce")
            out.dropna(subset=["date"], inplace=True)
            out.set_index("date", inplace=True)
            out.sort_index(inplace=True)
            return out
        except Exception as e:
            self.logger.error(f"ECB CSV parse error for {name}: {e}")
            return None

    def _parse_ecb_alt(self, text: str, name: str) -> pd.DataFrame | None:
        """Fallback parser for ECB compact format."""
        try:
            lines = [l for l in text.splitlines() if l.strip()]
            # Find data start: skip comment rows beginning with KEY
            data_lines = [l for l in lines if not l.startswith("KEY")]
            header = data_lines[0]
            df = pd.read_csv(io.StringIO("\n".join(data_lines)))
            if df.empty:
                return None
            # Last two meaningful columns are typically date and value
            df.columns = [c.strip() for c in df.columns]
            for time_col in ["TIME_PERIOD", "date", df.columns[-2]]:
                if time_col in df.columns:
                    break
            for val_col in ["OBS_VALUE", "value", df.columns[-1]]:
                if val_col in df.columns:
                    break
            out = df[[time_col, val_col]].copy()
            out.columns = ["date", name]
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
            out[name] = pd.to_numeric(out[name], errors="coerce")
            out.dropna(subset=["date"], inplace=True)
            out.set_index("date", inplace=True)
            return out
        except Exception as e:
            self.logger.error(f"ECB alt parse error for {name}: {e}")
            return None
