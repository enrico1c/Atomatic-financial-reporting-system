#!/usr/bin/env python3
"""
Train ML projection models on historical price data.

Usage:
    python train.py                          # train all tickers in config
    python train.py --tickers AAPL MSFT TSLA

Prerequisites:
    Run 'python main.py' at least once to fetch and clean price data.
    Models are saved to data/models/{TICKER}_{1d|5d}.pkl
"""

import sys
from ml.trainer import train_all
from config.settings import PRICE_TICKERS
import argparse

parser = argparse.ArgumentParser(description="Train financial projection models")
parser.add_argument(
    "--tickers", nargs="+", default=PRICE_TICKERS,
    help="Tickers to train on (default: all configured tickers)"
)
args = parser.parse_args()

train_all(args.tickers)
