"""
ML Trainer — loads historical price data, trains projection models per ticker,
and saves them to disk.

Usage:
    python train.py                  # train all configured tickers
    python train.py --tickers AAPL MSFT
"""

import argparse
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.settings import CLEAN_DIR, PRICE_TICKERS
from ml.feature_builder import FEATURE_COLS, build_features
from utils.logger import get_logger

log = get_logger("ml.trainer")

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def load_price_data() -> pd.DataFrame:
    path = CLEAN_DIR / "prices_daily.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Clean price data not found at {path}. "
            "Run 'python main.py' first to fetch and clean data."
        )
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    log.info(f"Loaded price data: {df.shape[0]} rows × {df.shape[1]} cols")
    return df


def _build_model(horizon: str) -> Pipeline:
    """Return a scikit-learn Pipeline for a given horizon."""
    if horizon == "1d":
        estimator = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42
        )
    else:  # 5d
        estimator = RandomForestRegressor(
            n_estimators=200, max_depth=6, min_samples_leaf=5, random_state=42
        )
    return Pipeline([("scaler", StandardScaler()), ("model", estimator)])


def train_ticker(prices_df: pd.DataFrame, ticker: str) -> dict:
    """
    Train 1-day and 5-day projection models for a single ticker.
    Returns a dict with model objects and evaluation metrics.
    """
    if ticker not in prices_df.columns:
        log.warning(f"Ticker '{ticker}' not found in price data — skipping")
        return {}

    close = prices_df[ticker].dropna()
    if len(close) < 100:
        log.warning(f"Not enough data for {ticker} ({len(close)} rows) — skipping")
        return {}

    features_df = build_features(close)
    X = features_df[FEATURE_COLS].values
    y_1d = features_df["target_1d"].values
    y_5d = features_df["target_5d"].values

    tscv = TimeSeriesSplit(n_splits=5)
    results = {}

    for horizon, y in [("1d", y_1d), ("5d", y_5d)]:
        pipe = _build_model(horizon)

        # Cross-validated evaluation (time-series aware)
        mae_scores, r2_scores = [], []
        for train_idx, test_idx in tscv.split(X):
            pipe.fit(X[train_idx], y[train_idx])
            y_pred = pipe.predict(X[test_idx])
            mae_scores.append(mean_absolute_error(y[test_idx], y_pred))
            r2_scores.append(r2_score(y[test_idx], y_pred))

        # Refit on all data
        pipe.fit(X, y)

        metrics = {
            "mae_mean": float(np.mean(mae_scores)),
            "mae_std":  float(np.std(mae_scores)),
            "r2_mean":  float(np.mean(r2_scores)),
        }
        log.info(
            f"  {ticker} [{horizon}] — MAE={metrics['mae_mean']:.4f} "
            f"R²={metrics['r2_mean']:.3f}"
        )
        results[horizon] = {"pipeline": pipe, "metrics": metrics}

    return results


def save_models(ticker: str, models: dict) -> None:
    for horizon, data in models.items():
        path = MODEL_DIR / f"{ticker}_{horizon}.pkl"
        with open(path, "wb") as f:
            pickle.dump(data, f)
        log.info(f"  Saved model → {path}")


def train_all(tickers: list[str]) -> None:
    log.info(f"Training ML models for {len(tickers)} tickers: {tickers}")
    prices_df = load_price_data()

    summary = []
    for ticker in tickers:
        log.info(f"Training {ticker}...")
        models = train_ticker(prices_df, ticker)
        if models:
            save_models(ticker, models)
            for h, d in models.items():
                summary.append({
                    "ticker": ticker,
                    "horizon": h,
                    **d["metrics"],
                })

    if summary:
        df_summary = pd.DataFrame(summary)
        summary_path = MODEL_DIR / "training_summary.csv"
        df_summary.to_csv(summary_path, index=False)
        log.info(f"\nTraining summary saved → {summary_path}")
        log.info("\n" + df_summary.to_string(index=False))
    else:
        log.warning("No models were trained. Check data availability.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train financial projection models")
    parser.add_argument("--tickers", nargs="+", default=PRICE_TICKERS)
    args = parser.parse_args()
    train_all(args.tickers)
