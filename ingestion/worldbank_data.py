"""
World Bank Open Data ingestion via the World Bank API v2.
No API key required.

API base: https://api.worldbank.org/v2/country/{country}/indicator/{indicator}
Format:   ?format=json&per_page=500

Fetches indicators defined in config.settings.WORLD_BANK_INDICATORS
for countries in config.settings.WORLD_BANK_COUNTRIES.

Limitations:
  - World Bank data is annual; updates with significant lag (1-2 years)
  - Not suitable for high-frequency monitoring; used for macro context
  - JSON response requires pagination handling for long series
"""

import time
import pandas as pd

from config.settings import (
    WORLD_BANK_INDICATORS,
    WORLD_BANK_COUNTRIES,
    WORLD_BANK_START_YEAR,
)
from ingestion.base_ingestion import BaseIngestion

WB_API_BASE = "https://api.worldbank.org/v2"


class WorldBankIngestion(BaseIngestion):
    def __init__(self):
        super().__init__("worldbank")

    # ── Public ─────────────────────────────────────────────────────────────────
    def fetch(self) -> dict[str, pd.DataFrame]:
        results = {}
        for ind_name, indicator in WORLD_BANK_INDICATORS.items():
            df = self._fetch_indicator(ind_name, indicator)
            if df is not None and not df.empty:
                results[ind_name] = df
            time.sleep(0.4)
        return results

    def fetch_combined(self) -> pd.DataFrame:
        """Fetch all indicators for all countries; return a multi-column DataFrame."""
        frames = {}
        for ind_name, indicator in WORLD_BANK_INDICATORS.items():
            df = self._fetch_indicator(ind_name, indicator)
            if df is not None:
                frames[ind_name] = df
            time.sleep(0.4)
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames.values(), axis=1, keys=frames.keys())
        self.save_raw(combined, "combined")
        return combined

    # ── Internal ────────────────────────────────────────────────────────────────
    def _fetch_indicator(self, ind_name: str, indicator: str) -> pd.DataFrame | None:
        self.logger.info(f"Fetching World Bank: {ind_name} ({indicator})")
        countries_str = ";".join(WORLD_BANK_COUNTRIES)
        url = f"{WB_API_BASE}/country/{countries_str}/indicator/{indicator}"
        params = {
            "format": "json",
            "per_page": 1000,
            "date": f"{WORLD_BANK_START_YEAR}:2025",
        }
        try:
            resp = self._get(url, params=params)
            data = resp.json()
            if not isinstance(data, list) or len(data) < 2:
                raise ValueError("Unexpected World Bank API response structure")
            records = data[1]
            if not records:
                return None
            rows = []
            for r in records:
                rows.append({
                    "year":    int(r["date"]),
                    "country": r["country"]["value"],
                    "iso":     r["countryiso3code"],
                    ind_name:  r["value"],
                })
            df = pd.DataFrame(rows)
            df[ind_name] = pd.to_numeric(df[ind_name], errors="coerce")
            df.sort_values(["country", "year"], inplace=True)
            self.save_raw(df, ind_name)
            self._stamp(ind_name)
            return df
        except Exception as e:
            self.logger.error(f"World Bank fetch failed for {ind_name}: {e}")
            cached = self.load_raw(ind_name)
            if cached is not None:
                self.logger.warning(f"Using cached World Bank data for {ind_name}")
                return cached
            return None

    def pivot_indicator(self, df: pd.DataFrame, value_col: str) -> pd.DataFrame:
        """Pivot long-format WB data to wide: rows=year, columns=country."""
        if df is None or df.empty:
            return pd.DataFrame()
        return df.pivot_table(index="year", columns="country", values=value_col)
