"""
KPI calculations from clean datasets.

Produces a KPI summary DataFrame with:
  - Price performance (1M, 3M, 6M, 1Y returns)
  - Realised volatility (21d, 63d)
  - Sharpe ratio (annualised, risk-free = latest 3M T-bill)
  - Max drawdown (rolling 252d)
  - Macro KPIs: yield spread, real rate, inflation delta
  - Financial statement KPIs: revenue growth, margins, leverage
"""

import pandas as pd
import numpy as np

from config.settings import STATEMENT_TICKERS, THRESHOLDS
from utils.logger import get_logger

log = get_logger("reporting.kpi_calculator")

TRADING_DAYS = 252
RISK_FREE_DEFAULT = 0.04  # fallback if rate unavailable


class KPICalculator:
    def __init__(self, clean_data: dict[str, pd.DataFrame]):
        self.data = clean_data

    # ── Public ─────────────────────────────────────────────────────────────────
    def compute_all(self) -> dict[str, pd.DataFrame]:
        kpis = {}
        kpis["price_kpis"]    = self._price_kpis()
        kpis["macro_kpis"]    = self._macro_kpis()
        kpis["statement_kpis"] = self._statement_kpis()
        kpis["kpi_summary"]   = self._build_summary(kpis)
        return kpis

    # ── Price KPIs ─────────────────────────────────────────────────────────────
    def _price_kpis(self) -> pd.DataFrame:
        df = self.data.get("prices_daily")
        if df is None or df.empty:
            return pd.DataFrame()

        close_cols = [c for c in df.columns if c.endswith("_close")]
        if not close_cols:
            return pd.DataFrame()

        rows = []
        rf = self._get_risk_free()

        for col in close_cols:
            ticker = col.replace("_close", "")
            series = df[col].dropna()
            if len(series) < 5:
                continue

            last = series.iloc[-1]
            ret_1m  = self._period_return(series, 21)
            ret_3m  = self._period_return(series, 63)
            ret_6m  = self._period_return(series, 126)
            ret_1y  = self._period_return(series, 252)

            # Realised vol
            log_ret = np.log(series / series.shift(1)).dropna()
            vol_21  = log_ret.tail(21).std() * np.sqrt(TRADING_DAYS) * 100
            vol_63  = log_ret.tail(63).std() * np.sqrt(TRADING_DAYS) * 100

            # Sharpe (1Y window)
            excess = log_ret.tail(252).mean() * TRADING_DAYS - rf
            denom  = log_ret.tail(252).std() * np.sqrt(TRADING_DAYS)
            sharpe = round(excess / denom, 3) if denom > 0 else None

            # Max drawdown (1Y)
            roll_max = series.tail(252).cummax()
            dd = (series.tail(252) - roll_max) / roll_max
            max_dd = dd.min() * 100

            rows.append({
                "ticker":      ticker,
                "last_price":  round(last, 2),
                "return_1m_%": round(ret_1m * 100, 2) if ret_1m is not None else None,
                "return_3m_%": round(ret_3m * 100, 2) if ret_3m is not None else None,
                "return_6m_%": round(ret_6m * 100, 2) if ret_6m is not None else None,
                "return_1y_%": round(ret_1y * 100, 2) if ret_1y is not None else None,
                "vol_21d_%":   round(vol_21, 2),
                "vol_63d_%":   round(vol_63, 2),
                "sharpe_1y":   sharpe,
                "maxdd_1y_%":  round(max_dd, 2),
            })

        return pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()

    # ── Macro KPIs ─────────────────────────────────────────────────────────────
    def _macro_kpis(self) -> pd.DataFrame:
        macro = self.data.get("macro_monthly")
        if macro is None or macro.empty:
            return pd.DataFrame()

        latest = macro.dropna(how="all").iloc[-1]
        prev   = macro.dropna(how="all").iloc[-2] if len(macro) > 1 else latest

        rows = {}
        for col in [
            "fed_funds_rate", "treasury_10y", "treasury_2y",
            "yield_spread_10y_2y", "real_fed_funds_rate",
            "cpi_all_urban", "unemployment_rate", "m2_money_supply",
            "ecb_main_refi_rate", "ecb_deposit_rate", "ecb_hicp_inflation",
        ]:
            if col in macro.columns:
                rows[col] = {
                    "latest":  round(float(latest.get(col, float("nan"))), 4),
                    "1m_ago":  round(float(prev.get(col, float("nan"))),   4),
                    "change":  round(float(latest.get(col, 0) - prev.get(col, 0)), 4),
                    "12m_avg": round(float(macro[col].tail(12).mean()), 4),
                }

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).T

    # ── Financial statement KPIs ────────────────────────────────────────────────
    def _statement_kpis(self) -> pd.DataFrame:
        rows = []
        for ticker in STATEMENT_TICKERS:
            key = f"financials_{ticker}_annual"
            df = self.data.get(key)
            if df is None or df.empty:
                continue

            row = {"ticker": ticker}

            # Revenue growth YoY
            rev_col = self._find_col(df, ["income_annual_total_revenue", "income_annual_revenue",
                                           "total_revenue", "revenue"])
            if rev_col:
                rev = df[rev_col].dropna().sort_index()
                if len(rev) >= 2:
                    row["revenue_yoy_%"] = round((rev.iloc[-1] / rev.iloc[-2] - 1) * 100, 2)
                    row["revenue_latest_m"] = round(rev.iloc[-1], 1)

            # Gross margin
            gp_col  = self._find_col(df, ["income_annual_gross_profit", "gross_profit"])
            if rev_col and gp_col:
                rev_v = df[rev_col].dropna().iloc[-1]
                gp_v  = df[gp_col].dropna().iloc[-1]
                if rev_v:
                    row["gross_margin_%"] = round(gp_v / rev_v * 100, 2)

            # Net margin
            ni_col = self._find_col(df, ["income_annual_net_income", "net_income"])
            if rev_col and ni_col:
                rev_v = df[rev_col].dropna().iloc[-1]
                ni_v  = df[ni_col].dropna().iloc[-1]
                if rev_v:
                    row["net_margin_%"] = round(ni_v / rev_v * 100, 2)

            # Debt-to-equity
            debt_col = self._find_col(df, ["balance_annual_total_debt", "total_debt"])
            eq_col   = self._find_col(df, ["balance_annual_stockholders_equity",
                                            "balance_annual_total_stockholders_equity"])
            if debt_col and eq_col:
                d = df[debt_col].dropna()
                e = df[eq_col].dropna()
                if not d.empty and not e.empty and e.iloc[-1]:
                    row["debt_to_equity"] = round(d.iloc[-1] / e.iloc[-1], 3)

            rows.append(row)

        return pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()

    # ── Summary table ──────────────────────────────────────────────────────────
    def _build_summary(self, kpis: dict) -> pd.DataFrame:
        """One-pager KPI table for the INSIGHTS sheet."""
        parts = []
        for name, df in kpis.items():
            if name == "kpi_summary" or df.empty:
                continue
            df = df.copy()
            df.insert(0, "category", name)
            parts.append(df)
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts)

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _period_return(self, series: pd.Series, days: int):
        if len(series) < days:
            return None
        return series.iloc[-1] / series.iloc[-days] - 1

    def _get_risk_free(self) -> float:
        macro = self.data.get("macro_monthly")
        if macro is not None and "treasury_2y" in macro.columns:
            val = macro["treasury_2y"].dropna().iloc[-1]
            return val / 100 if val > 1 else val
        return RISK_FREE_DEFAULT

    def _find_col(self, df: pd.DataFrame, candidates: list[str]) -> str | None:
        for c in candidates:
            if c in df.columns:
                return c
            # Partial match
            matches = [col for col in df.columns if c in col.lower()]
            if matches:
                return matches[0]
        return None
