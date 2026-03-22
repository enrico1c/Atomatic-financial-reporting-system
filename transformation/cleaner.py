"""
Data cleaning rules applied to all raw ingested DataFrames.

Rules:
  1. Drop fully empty rows and columns
  2. Remove duplicate indices (keep last)
  3. Coerce numeric columns; non-parseable values → NaN
  4. Forward-fill gaps up to MAX_FFILL_PERIODS
  5. Interpolate remaining interior NaNs (linear)
  6. Drop rows where ALL values are NaN after filling
  7. Clip extreme outliers (>5 IQR from median) only for price/rate series
  8. Standardize column names: lowercase, spaces→underscore
"""

import re
import pandas as pd
import numpy as np

from utils.logger import get_logger

log = get_logger("transformation.cleaner")

MAX_FFILL_PERIODS = 5   # max consecutive NaNs to forward-fill
OUTLIER_IQR_MULT  = 5   # multiplier for IQR-based outlier removal


# ── Column name normalisation ──────────────────────────────────────────────────
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_clean_col(c) for c in df.columns]
    return df


def _clean_col(name: str) -> str:
    name = str(name).strip().lower()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


# ── Main cleaner ───────────────────────────────────────────────────────────────
def clean_timeseries(
    df: pd.DataFrame,
    clip_outliers: bool = False,
    ffill: bool = True,
    interpolate: bool = True,
) -> pd.DataFrame:
    """
    Apply standard cleaning pipeline to a time-indexed DataFrame.
    Returns a cleaned copy.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # 1. Normalize column names
    df = normalize_columns(df)

    # 2. Ensure datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[df.index.notna()]

    # 3. Sort chronologically
    df.sort_index(inplace=True)

    # 4. Drop fully empty rows / columns
    df.dropna(how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)

    # 5. Remove duplicate index entries (keep last observation)
    df = df[~df.index.duplicated(keep="last")]

    # 6. Coerce all columns to numeric where possible
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 7. Forward-fill up to MAX_FFILL_PERIODS (handles weekends/holidays)
    if ffill:
        df.ffill(limit=MAX_FFILL_PERIODS, inplace=True)

    # 8. Linear interpolation for interior gaps
    if interpolate:
        df.interpolate(method="time", limit=MAX_FFILL_PERIODS, inplace=True)

    # 9. Drop rows still entirely NaN
    df.dropna(how="all", inplace=True)

    # 10. Clip extreme outliers (optional, for price/rate series)
    if clip_outliers:
        df = _clip_outliers(df)

    log.debug(f"Cleaned DataFrame: {df.shape}, date range: {df.index.min()} → {df.index.max()}")
    return df


def clean_financial_statement(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean a financial statement DataFrame (income stmt, balance sheet, cash flow).
    Rows = reporting periods (datetime), columns = line items.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df = normalize_columns(df)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[df.index.notna()]

    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="last")]

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Scale to millions if values look like raw dollars (>1e9 majority)
    numeric_cols = df.select_dtypes(include="number").columns
    if len(numeric_cols):
        median_val = df[numeric_cols].abs().median().median()
        if median_val > 1e9:
            df[numeric_cols] = df[numeric_cols] / 1e6
            log.debug("Scaled financial statement values to millions USD")

    df.dropna(how="all", inplace=True)
    return df


# ── Helpers ────────────────────────────────────────────────────────────────────
def _clip_outliers(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include="number")
    for col in numeric.columns:
        q1   = numeric[col].quantile(0.25)
        q3   = numeric[col].quantile(0.75)
        iqr  = q3 - q1
        lo   = q1 - OUTLIER_IQR_MULT * iqr
        hi   = q3 + OUTLIER_IQR_MULT * iqr
        df[col] = df[col].clip(lower=lo, upper=hi)
    return df


def align_to_monthly(df: pd.DataFrame, method: str = "last") -> pd.DataFrame:
    """
    Resample a daily DataFrame to month-end frequency.
    method: 'last' | 'mean' | 'sum'
    """
    if df.empty:
        return df
    resampler = df.resample("ME")
    if method == "last":
        return resampler.last()
    elif method == "mean":
        return resampler.mean()
    elif method == "sum":
        return resampler.sum()
    return resampler.last()


def align_to_quarterly(df: pd.DataFrame, method: str = "last") -> pd.DataFrame:
    """Resample to quarter-end frequency."""
    if df.empty:
        return df
    resampler = df.resample("QE")
    return getattr(resampler, method)()
