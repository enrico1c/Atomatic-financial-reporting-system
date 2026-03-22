"""
Central configuration for the financial automation system.
Edit this file to customize tickers, indicators, and output paths.
"""

import os
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_DIR, CLEAN_DIR, OUTPUT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Yahoo Finance ─────────────────────────────────────────────────────────────
# Tickers to track for price data
PRICE_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "JPM", "GS", "BAC", "XOM", "SPY", "QQQ"]

# Tickers for full financial statements (income stmt, balance sheet, cash flow)
STATEMENT_TICKERS = ["AAPL", "MSFT", "JPM"]

# Price history window
PRICE_HISTORY_YEARS = 3

# ─── FRED Series ───────────────────────────────────────────────────────────────
# Maps readable name → FRED series ID
FRED_SERIES = {
    "fed_funds_rate":       "FEDFUNDS",      # Monthly, %
    "cpi_all_urban":        "CPIAUCSL",      # Monthly, index
    "unemployment_rate":    "UNRATE",         # Monthly, %
    "gdp_us":               "GDP",            # Quarterly, billions USD
    "treasury_10y":         "DGS10",          # Daily, %
    "treasury_2y":          "DGS2",           # Daily, %
    "m2_money_supply":      "M2SL",           # Monthly, billions USD
    "core_pce":             "PCEPILFE",       # Monthly, index
    "industrial_production": "INDPRO",        # Monthly, index
    "consumer_sentiment":   "UMCSENT",        # Monthly, index
}

FRED_BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# ─── ECB Series ────────────────────────────────────────────────────────────────
# Maps readable name → ECB SDMX flow key
ECB_SERIES = {
    "ecb_main_refi_rate":   "FM/B.U2.EUR.4F.KR.MRR_FR.LEV",
    "ecb_deposit_rate":     "FM/B.U2.EUR.4F.KR.DFR.LEV",
    "ecb_hicp_inflation":   "ICP/M.U2.N.000000.4.ANR",
    "euribor_3m":           "FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
}

ECB_API_BASE = "https://data-api.ecb.europa.eu/service/data"

# ─── World Bank Indicators ─────────────────────────────────────────────────────
# Maps readable name → World Bank indicator code
WORLD_BANK_INDICATORS = {
    "gdp_current_usd":      "NY.GDP.MKTP.CD",
    "gdp_growth":           "NY.GDP.MKTP.KD.ZG",
    "inflation_cpi":        "FP.CPI.TOTL.ZG",
    "unemployment_wb":      "SL.UEM.TOTL.ZS",
    "govt_debt_pct_gdp":    "GC.DOD.TOTL.GD.ZS",
    "current_account_gdp":  "BN.CAB.XOKA.GD.ZS",
}

WORLD_BANK_COUNTRIES = ["US", "DE", "GB", "JP", "CN", "FR", "IT", "CA"]
WORLD_BANK_START_YEAR = 2010

# ─── Reporting ─────────────────────────────────────────────────────────────────
REPORT_EXCEL_FILENAME = "financial_report_{date}.xlsx"
LATEST_EXCEL_FILENAME = "financial_report_latest.xlsx"

# ─── Insights thresholds ───────────────────────────────────────────────────────
THRESHOLDS = {
    "revenue_growth_high":      0.10,   # 10% MoM or YoY
    "revenue_growth_low":      -0.05,   # -5%
    "volatility_high_mult":     1.5,    # 1.5x historical avg
    "rate_rise_threshold":      0.25,   # 25bps
    "rate_fall_threshold":     -0.25,
    "inflation_high":           4.0,    # 4% annual
    "inflation_target":         2.0,
    "unemployment_high":        6.0,
    "yield_curve_inversion":    0.0,    # 10Y - 2Y spread
}

# ─── Scheduling ────────────────────────────────────────────────────────────────
# "daily" or "monthly"
REFRESH_FREQUENCY = "daily"
DAILY_RUN_TIME = "07:00"   # 24h format, server local time
