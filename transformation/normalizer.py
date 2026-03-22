"""
Normalisation and derived metrics.

Computes standard financial metrics from cleaned data:
  - Log returns, simple returns, rolling volatility
  - YoY / MoM growth rates
  - Z-score normalization
  - Yield spread (10Y - 2Y)
  - Real interest rate (nominal - CPI)
"""

import pandas as pd
import numpy as np

from utils.logger import get_logger

log = get_logger("transformation.normalizer")

TRADING_DAYS_PER_YEAR = 252


def compute_returns(prices: pd.DataFrame, price_col_suffix: str = "_close") -> pd.DataFrame:
    """
    Compute simple and log daily returns for each price column.
    Expects columns like 'AAPL_close', 'MSFT_close'.
    """
    price_cols = [c for c in prices.columns if c.endswith(price_col_suffix)]
    if not price_cols:
        # Try direct numeric columns
        price_cols = prices.select_dtypes(include="number").columns.tolist()

    returns = pd.DataFrame(index=prices.index)
    for col in price_cols:
        ticker = col.replace(price_col_suffix, "")
        series = prices[col].dropna()
        returns[f"{ticker}_ret_simple"] = series.pct_change()
        returns[f"{ticker}_ret_log"]    = np.log(series / series.shift(1))
    return returns.dropna(how="all")


def compute_rolling_volatility(
    returns: pd.DataFrame,
    window: int = 21,
    annualize: bool = True,
) -> pd.DataFrame:
    """
    Rolling standard deviation of returns, annualised if requested.
    """
    ret_cols = [c for c in returns.columns if c.endswith("_ret_log")]
    vols = pd.DataFrame(index=returns.index)
    factor = np.sqrt(TRADING_DAYS_PER_YEAR) if annualize else 1.0
    for col in ret_cols:
        ticker = col.replace("_ret_log", "")
        vols[f"{ticker}_vol_{window}d"] = returns[col].rolling(window).std() * factor
    return vols.dropna(how="all")


def compute_mom_growth(df: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """Month-over-month percentage change (for monthly-frequency data)."""
    num_cols = df.select_dtypes(include="number").columns
    return df[num_cols].pct_change(periods=periods).add_suffix(f"_mom_{periods}m")


def compute_yoy_growth(df: pd.DataFrame, periods: int = 12) -> pd.DataFrame:
    """Year-over-year percentage change (for monthly-frequency data)."""
    num_cols = df.select_dtypes(include="number").columns
    return df[num_cols].pct_change(periods=periods).add_suffix("_yoy")


def compute_zscore(df: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """Rolling Z-score for each numeric column."""
    num_cols = df.select_dtypes(include="number").columns
    z = pd.DataFrame(index=df.index)
    for col in num_cols:
        mu  = df[col].rolling(window).mean()
        sig = df[col].rolling(window).std()
        z[f"{col}_zscore"] = (df[col] - mu) / sig
    return z.dropna(how="all")


def compute_yield_spread(macro_monthly: pd.DataFrame) -> pd.Series:
    """10Y - 2Y Treasury yield spread (yield curve indicator)."""
    if "treasury_10y" in macro_monthly.columns and "treasury_2y" in macro_monthly.columns:
        spread = macro_monthly["treasury_10y"] - macro_monthly["treasury_2y"]
        spread.name = "yield_spread_10y_2y"
        return spread
    log.warning("treasury_10y or treasury_2y not found; skipping yield spread")
    return pd.Series(dtype=float, name="yield_spread_10y_2y")


def compute_real_rate(macro_monthly: pd.DataFrame) -> pd.Series:
    """Approximate real interest rate = Fed Funds Rate - YoY CPI."""
    if "fed_funds_rate" in macro_monthly.columns and "cpi_all_urban" in macro_monthly.columns:
        cpi_yoy = macro_monthly["cpi_all_urban"].pct_change(12) * 100
        real = macro_monthly["fed_funds_rate"] - cpi_yoy
        real.name = "real_fed_funds_rate"
        return real
    log.warning("Required columns for real rate missing")
    return pd.Series(dtype=float, name="real_fed_funds_rate")


def normalise_macro(fred_df: pd.DataFrame, ecb_df: pd.DataFrame) -> pd.DataFrame:
    """
    Align FRED (monthly) and ECB (monthly/daily) data to month-end.
    Returns merged macro DataFrame.
    """
    from transformation.cleaner import align_to_monthly

    # Both to monthly
    fred_m = align_to_monthly(fred_df, method="last")
    ecb_m  = align_to_monthly(ecb_df,  method="last") if not ecb_df.empty else pd.DataFrame()

    if not ecb_m.empty:
        macro = fred_m.join(ecb_m, how="outer", rsuffix="_ecb")
    else:
        macro = fred_m

    # Derived series
    spread = compute_yield_spread(macro)
    real_r = compute_real_rate(macro)
    macro["yield_spread_10y_2y"] = spread
    macro["real_fed_funds_rate"]  = real_r

    macro.sort_index(inplace=True)
    log.info(f"Normalised macro data: {macro.shape}, {macro.index.min()} → {macro.index.max()}")
    return macro
