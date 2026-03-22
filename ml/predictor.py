"""
ML Predictor — loads saved models and generates real-time projections.
"""

import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ml.feature_builder import FEATURE_COLS, build_features
from utils.logger import get_logger

log = get_logger("ml.predictor")

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"


class Predictor:
    """
    Loads trained models from disk and produces forward projections
    given a window of recent price data.
    """

    def __init__(self, tickers: list[str]):
        self.tickers = tickers
        self._models: dict[str, dict] = {}   # {ticker: {"1d": pipe, "5d": pipe}}
        self._load_models()

    def _load_models(self) -> None:
        loaded, missing = [], []
        for ticker in self.tickers:
            self._models[ticker] = {}
            for horizon in ("1d", "5d"):
                path = MODEL_DIR / f"{ticker}_{horizon}.pkl"
                if path.exists():
                    with open(path, "rb") as f:
                        data = pickle.load(f)
                    self._models[ticker][horizon] = data["pipeline"]
                    loaded.append(f"{ticker}/{horizon}")
                else:
                    missing.append(f"{ticker}/{horizon}")

        if loaded:
            log.info(f"Loaded {len(loaded)} model(s): {', '.join(loaded)}")
        if missing:
            log.warning(
                f"No saved models for: {', '.join(missing)}. "
                "Run 'python train.py' first."
            )

    def predict(self, ticker: str, close_series: pd.Series) -> Optional[dict]:
        """
        Produce projections for a ticker from a recent price window.

        Args:
            ticker:       Stock symbol.
            close_series: pd.Series of historical closing prices
                          (minimum ~70 data points recommended).

        Returns:
            dict with keys 'return_1d', 'return_5d', 'projected_price_1d',
            'projected_price_5d', 'trend', or None if no models available.
        """
        if ticker not in self._models or not self._models[ticker]:
            return None

        try:
            features_df = build_features(close_series)
            if features_df.empty:
                return None

            last_row = features_df[FEATURE_COLS].iloc[[-1]].values
            last_price = float(close_series.dropna().iloc[-1])

            result: dict = {"last_price": last_price}

            for horizon in ("1d", "5d"):
                pipe = self._models[ticker].get(horizon)
                if pipe is None:
                    continue
                ret = float(pipe.predict(last_row)[0])
                proj_price = last_price * (1 + ret)
                result[f"return_{horizon}"] = round(ret, 6)
                result[f"projected_price_{horizon}"] = round(proj_price, 4)

            # Derive simple trend signal
            ret_1d = result.get("return_1d", 0.0)
            if ret_1d > 0.002:
                result["trend"] = "bullish"
            elif ret_1d < -0.002:
                result["trend"] = "bearish"
            else:
                result["trend"] = "neutral"

            return result

        except Exception as e:
            log.debug(f"Prediction error for {ticker}: {e}")
            return None
