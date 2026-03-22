"""
Dataset merging and final clean dataset construction.

Produces:
  - clean/prices_daily.csv         — daily OHLCV + returns + volatility
  - clean/macro_monthly.csv        — monthly macro indicators (FRED + ECB merged)
  - clean/macro_worldbank.csv      — annual World Bank indicators
  - clean/financials_{ticker}.csv  — per-ticker financial statements
"""

import pandas as pd

from config.settings import CLEAN_DIR, STATEMENT_TICKERS
from transformation.cleaner import (
    clean_timeseries,
    clean_financial_statement,
    align_to_monthly,
)
from transformation.normalizer import (
    compute_returns,
    compute_rolling_volatility,
    compute_mom_growth,
    compute_yoy_growth,
    normalise_macro,
)
from utils.logger import get_logger

log = get_logger("transformation.merger")


class DataMerger:
    def __init__(self, raw_data: dict[str, pd.DataFrame]):
        """
        raw_data: dictionary of {dataset_name: DataFrame} from all ingestion modules.
        Expected keys:
          'prices', 'fred_combined', 'ecb_combined', 'worldbank_combined',
          '{TICKER}_income_annual', '{TICKER}_balance_annual', '{TICKER}_cashflow_annual', ...
        """
        self.raw = raw_data
        self.clean: dict[str, pd.DataFrame] = {}

    # ── Main pipeline ──────────────────────────────────────────────────────────
    def run(self) -> dict[str, pd.DataFrame]:
        log.info("Starting merge pipeline")
        self._build_prices()
        self._build_macro()
        self._build_financials()
        self._save_all()
        log.info(f"Merge complete. Datasets produced: {list(self.clean.keys())}")
        return self.clean

    # ── Prices ─────────────────────────────────────────────────────────────────
    def _build_prices(self):
        raw_prices = self.raw.get("prices")
        if raw_prices is None or raw_prices.empty:
            log.warning("No raw price data available")
            return

        prices = clean_timeseries(raw_prices, clip_outliers=True, ffill=True)
        returns = compute_returns(prices, price_col_suffix="_close")
        vols_21  = compute_rolling_volatility(returns, window=21)
        vols_63  = compute_rolling_volatility(returns, window=63)

        daily = prices.join(returns, how="left").join(vols_21, how="left").join(vols_63, how="left")
        self.clean["prices_daily"] = daily

        # Also store a monthly view
        close_cols = [c for c in prices.columns if c.endswith("_close")]
        if close_cols:
            monthly = align_to_monthly(prices[close_cols], method="last")
            self.clean["prices_monthly"] = monthly

    # ── Macro ──────────────────────────────────────────────────────────────────
    def _build_macro(self):
        fred_raw = self.raw.get("fred_combined", pd.DataFrame())
        ecb_raw  = self.raw.get("ecb_combined",  pd.DataFrame())

        fred_clean = clean_timeseries(fred_raw, ffill=True, interpolate=True) if not fred_raw.empty else pd.DataFrame()
        ecb_clean  = clean_timeseries(ecb_raw,  ffill=True, interpolate=True) if not ecb_raw.empty else pd.DataFrame()

        macro = normalise_macro(fred_clean, ecb_clean)

        # Month-over-month and year-over-year growth
        mom = compute_mom_growth(macro)
        yoy = compute_yoy_growth(macro)

        macro_full = pd.concat([macro, mom, yoy], axis=1)
        macro_full.sort_index(inplace=True)
        self.clean["macro_monthly"] = macro_full

        # World Bank
        wb_raw = self.raw.get("worldbank_combined", pd.DataFrame())
        if not wb_raw.empty:
            self.clean["macro_worldbank"] = wb_raw

    # ── Financial statements ────────────────────────────────────────────────────
    def _build_financials(self):
        for ticker in STATEMENT_TICKERS:
            frames = {}
            for stmt in ["income_annual", "balance_annual", "cashflow_annual",
                         "income_quarterly", "balance_quarterly", "cashflow_quarterly"]:
                key = f"{ticker}_{stmt}"
                raw = self.raw.get(key)
                if raw is not None and not raw.empty:
                    frames[stmt] = clean_financial_statement(raw)

            if frames:
                # Merge annual statements into one wide table per ticker
                annual_parts = {k: v for k, v in frames.items() if "annual" in k}
                if annual_parts:
                    # Concatenate along columns for the same periods
                    combined = pd.concat(
                        [df.add_prefix(f"{stmt}_") for stmt, df in annual_parts.items()],
                        axis=1,
                    )
                    self.clean[f"financials_{ticker}_annual"] = combined

                # Keep quarterly separately
                qtr_parts = {k: v for k, v in frames.items() if "quarterly" in k}
                if qtr_parts:
                    qtr_combined = pd.concat(
                        [df.add_prefix(f"{stmt}_") for stmt, df in qtr_parts.items()],
                        axis=1,
                    )
                    self.clean[f"financials_{ticker}_quarterly"] = qtr_combined

    # ── Save ───────────────────────────────────────────────────────────────────
    def _save_all(self):
        for name, df in self.clean.items():
            path = CLEAN_DIR / f"{name}.csv"
            df.to_csv(path)
            log.debug(f"Saved clean dataset: {path} ({df.shape})")

    @staticmethod
    def load_clean() -> dict[str, pd.DataFrame]:
        """Load all clean CSVs from disk."""
        data = {}
        for f in CLEAN_DIR.glob("*.csv"):
            try:
                data[f.stem] = pd.read_csv(f, index_col=0, parse_dates=True)
            except Exception as e:
                log.warning(f"Could not load {f}: {e}")
        return data
