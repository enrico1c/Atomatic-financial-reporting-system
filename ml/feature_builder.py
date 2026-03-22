"""
Feature engineering for ML models.
Builds technical indicators and lagged features from price data.
"""

import numpy as np
import pandas as pd


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def build_features(close: pd.Series) -> pd.DataFrame:
    """
    Build ML feature matrix from a price series.

    Args:
        close: pd.Series of closing prices (DatetimeIndex)

    Returns:
        DataFrame of features with 'target_1d' and 'target_5d' columns.
        NaN rows are dropped.
    """
    f = pd.DataFrame(index=close.index)

    # ── Lagged returns ────────────────────────────────────────────────────────
    for lag in [1, 2, 3, 5, 10, 20]:
        f[f"ret_{lag}d"] = close.pct_change(lag)

    # ── Rolling volatility (annualised) ───────────────────────────────────────
    daily_ret = close.pct_change()
    for window in [5, 10, 20]:
        f[f"vol_{window}d"] = daily_ret.rolling(window).std() * np.sqrt(252)

    # ── RSI ───────────────────────────────────────────────────────────────────
    f["rsi_14"] = compute_rsi(close, 14)

    # ── MACD ──────────────────────────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    f["macd"] = macd_line
    f["macd_signal"] = signal_line
    f["macd_hist"] = macd_line - signal_line

    # ── Bollinger Band position ────────────────────────────────────────────────
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std().replace(0, np.nan)
    f["bb_pos"] = (close - sma20) / (2 * std20)

    # ── Price momentum ────────────────────────────────────────────────────────
    f["mom_5d"]  = close / close.shift(5)  - 1
    f["mom_20d"] = close / close.shift(20) - 1
    f["mom_60d"] = close / close.shift(60) - 1

    # ── Targets ───────────────────────────────────────────────────────────────
    f["target_1d"] = close.pct_change().shift(-1)   # next-day return
    f["target_5d"] = (close.shift(-5) / close) - 1  # 5-day ahead return

    return f.dropna()


FEATURE_COLS = [
    "ret_1d", "ret_2d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
    "vol_5d", "vol_10d", "vol_20d",
    "rsi_14",
    "macd", "macd_signal", "macd_hist",
    "bb_pos",
    "mom_5d", "mom_20d", "mom_60d",
]
