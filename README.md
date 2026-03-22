# Atomatic Financial Reporting System

A production-style Python + Excel financial data automation system.

## What it does

1. **Pulls** financial and macro data from Yahoo Finance, FRED, ECB, and World Bank — no API keys required
2. **Cleans** and standardises all data (ffill, interpolation, outlier clipping, frequency alignment)
3. **Computes** KPIs: returns, volatility, Sharpe ratio, drawdown, yield spread, real rates, revenue growth, margins
4. **Generates** a multi-sheet Excel workbook with formatted tables
5. **Produces** plain-English rule-based insights (no LLM required)
6. **Runs automatically** via built-in scheduler or cron

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Configure tickers and indicators
nano config/settings.py

# 3. Run the full pipeline
python main.py

# Output: data/output/financial_report_latest.xlsx
```

---

## Project Structure

```
.
├── config/
│   └── settings.py          # All configuration (tickers, FRED series, thresholds)
├── ingestion/
│   ├── base_ingestion.py    # Retry logic, caching, save/load helpers
│   ├── yahoo_finance.py     # Prices + financial statements via yfinance
│   ├── fred_data.py         # FRED macro series via CSV download (no key)
│   ├── ecb_data.py          # ECB rates/inflation via SDMX REST API (no key)
│   └── worldbank_data.py    # World Bank indicators via JSON API (no key)
├── transformation/
│   ├── cleaner.py           # Missing values, duplicates, normalization
│   ├── normalizer.py        # Returns, volatility, growth rates, derived metrics
│   └── merger.py            # Merges all sources into clean datasets
├── reporting/
│   ├── kpi_calculator.py    # Price KPIs, macro KPIs, financial statement KPIs
│   ├── insights_engine.py   # Rule-based text insight generation
│   └── monthly_report.py    # Monthly aggregation table
├── excel/
│   └── workbook_builder.py  # Builds the formatted Excel workbook
├── utils/
│   ├── logger.py            # Logging to console + file
│   └── date_utils.py        # Date helpers
├── data/
│   ├── raw/                 # Raw CSVs from each source
│   ├── clean/               # Cleaned/merged datasets
│   └── output/              # Final Excel reports
├── logs/                    # Daily log files
├── main.py                  # Pipeline entry point
├── scheduler.py             # Automated scheduling
└── requirements.txt
```

---

## Data Sources

| Source | Access | Data | Update Freq | Module |
|--------|--------|------|-------------|--------|
| Yahoo Finance | `yfinance` (no key) | Prices, financials | Daily | `yahoo_finance.py` |
| FRED | CSV download (no key) | Fed rates, CPI, unemployment, GDP | Monthly | `fred_data.py` |
| ECB SDMX API | REST (no key) | ECB rates, HICP inflation | Monthly | `ecb_data.py` |
| World Bank | JSON API (no key) | GDP, inflation, debt (annual) | Annual | `worldbank_data.py` |

---

## Excel Workbook Sheets

| Sheet | Contents |
|-------|----------|
| `RAW_PRICES` | Daily OHLCV prices for all tracked tickers (1 year) |
| `RAW_MACRO` | Raw FRED + ECB monthly indicators (5 years) |
| `CLEAN_PRICES` | Prices + daily returns + 21d/63d volatility (2 years) |
| `CLEAN_MACRO` | Cleaned monthly macro with MoM/YoY growth rates (10 years) |
| `FINANCIAL_STMTS` | Income statement, balance sheet, cash flow per ticker |
| `KPI_SUMMARY` | All computed KPIs in one table |
| `MONTHLY_REPORT` | Month-end snapshot: prices + macro (24 months) |
| `INSIGHTS` | Color-coded rule-based text insights |
| `WORLDBANK` | Annual global macro data by country |

---

## CLI Options

```bash
python main.py               # Full pipeline: fetch → clean → report
python main.py --no-fetch    # Use cached raw data (skip network calls)
python main.py --report-only # Rebuild Excel + insights from saved clean data
```

---

## Automation

**Python scheduler** (runs in foreground):
```bash
python scheduler.py
```

**Linux cron** (recommended for servers):
```bash
# Run at 07:00 Mon-Fri
0 7 * * 1-5 /path/to/venv/bin/python /path/to/main.py >> /path/to/logs/cron.log 2>&1
```

---

## Configuration

Edit `config/settings.py`:

```python
# Add/remove tickers
PRICE_TICKERS = ["AAPL", "MSFT", "GOOGL", ...]

# Add/remove FRED series
FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    ...
}

# Adjust insight thresholds
THRESHOLDS = {
    "inflation_high": 4.0,
    "yield_curve_inversion": 0.0,
    ...
}
```

---

## Source Limitations

- **Yahoo Finance**: Rate-limited; quarterly financials may lag 1 quarter. Delisted tickers handled gracefully.
- **FRED**: Some series revised retroactively. GDP is quarterly; yields are daily.
- **ECB SDMX**: Key format is strict (wrong keys = 404). Rate decision dates may not align with month-end.
- **World Bank**: Annual data only; 1-2 year publication lag. Not for high-frequency monitoring.
