"""
Monthly report aggregation.

Builds a single wide DataFrame representing the most recent month's data:
  - Month-end prices for all tracked tickers
  - Monthly returns (simple)
  - Macro indicator snapshot (month-end values)
  - MoM and YoY changes where available

This DataFrame is written to the MONTHLY_REPORT sheet and also
used by the insights engine.
"""

from datetime import datetime

import pandas as pd
import numpy as np

from config.settings import PRICE_TICKERS
from utils.logger import get_logger

log = get_logger("reporting.monthly_report")


class MonthlyReportBuilder:
    def __init__(self, clean_data: dict[str, pd.DataFrame]):
        self.data = clean_data

    def build(self) -> pd.DataFrame:
        """
        Return a DataFrame indexed by month-end date with all key metrics.
        Last 24 months shown in the workbook.
        """
        frames = []

        prices_m = self._monthly_prices()
        if not prices_m.empty:
            frames.append(prices_m)

        macro_m = self._monthly_macro()
        if not macro_m.empty:
            frames.append(macro_m)

        if not frames:
            log.warning("No data available for monthly report")
            return pd.DataFrame()

        report = pd.concat(frames, axis=1)
        report.sort_index(inplace=True)
        log.info(f"Monthly report built: {report.shape}, last date: {report.index[-1].date()}")
        return report

    def _monthly_prices(self) -> pd.DataFrame:
        prices = self.data.get("prices_monthly")
        if prices is None or prices.empty:
            # Fall back to daily
            prices = self.data.get("prices_daily")
            if prices is None or prices.empty:
                return pd.DataFrame()
            close_cols = [c for c in prices.columns if c.endswith("_close")]
            prices = prices[close_cols].resample("ME").last()

        close_cols = [c for c in prices.columns if c.endswith("_close")]
        if not close_cols:
            close_cols = prices.columns.tolist()

        result = prices[close_cols].copy()
        # Add monthly return for each
        for col in close_cols:
            ticker = col.replace("_close", "")
            result[f"{ticker}_ret_1m_%"] = prices[col].pct_change() * 100
        return result

    def _monthly_macro(self) -> pd.DataFrame:
        macro = self.data.get("macro_monthly")
        if macro is None or macro.empty:
            return pd.DataFrame()

        keep_cols = [
            "fed_funds_rate", "treasury_10y", "treasury_2y", "yield_spread_10y_2y",
            "real_fed_funds_rate", "cpi_all_urban", "unemployment_rate",
            "ecb_main_refi_rate", "ecb_deposit_rate",
        ]
        available = [c for c in keep_cols if c in macro.columns]
        return macro[available].copy()
