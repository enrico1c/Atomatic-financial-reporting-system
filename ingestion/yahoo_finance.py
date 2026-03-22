"""
Yahoo Finance ingestion via yfinance.
No API key required.

Fetches:
  - Historical daily prices (OHLCV)
  - Income statement (annual + quarterly)
  - Balance sheet (annual + quarterly)
  - Cash flow statement (annual + quarterly)
  - Key statistics / info

Limitations:
  - Rate limiting applies; avoid hammering in tight loops
  - Quarterly data may have a 1-quarter lag
  - Delisted tickers raise errors (handled gracefully)
"""

from datetime import datetime
import pandas as pd
import yfinance as yf

from config.settings import PRICE_TICKERS, STATEMENT_TICKERS, PRICE_HISTORY_YEARS
from ingestion.base_ingestion import BaseIngestion
from utils.date_utils import n_years_ago, today


class YahooFinanceIngestion(BaseIngestion):
    def __init__(self, price_tickers: list[str] | None = None, statement_tickers: list[str] | None = None):
        super().__init__("yahoo")
        self.price_tickers = price_tickers if price_tickers is not None else PRICE_TICKERS
        self.statement_tickers = statement_tickers if statement_tickers is not None else STATEMENT_TICKERS

    # ── Public ─────────────────────────────────────────────────────────────────
    def fetch(self) -> dict[str, pd.DataFrame]:
        results = {}

        # Prices
        prices = self._fetch_prices()
        if not prices.empty:
            self.save_raw(prices, "prices")
            self._stamp("prices")
            results["prices"] = prices

        # Financial statements per ticker
        for ticker in self.statement_tickers:
            stmts = self._fetch_statements(ticker)
            for stmt_name, df in stmts.items():
                if df is not None and not df.empty:
                    key = f"{ticker}_{stmt_name}"
                    self.save_raw(df, key)
                    self._stamp(key)
                    results[key] = df

        return results

    # ── Prices ─────────────────────────────────────────────────────────────────
    def _fetch_prices(self) -> pd.DataFrame:
        start = n_years_ago(PRICE_HISTORY_YEARS)
        end = today()
        self.logger.info(f"Fetching prices for {self.price_tickers} from {start} to {end}")
        try:
            df = yf.download(
                self.price_tickers,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            # Flatten multi-level columns → ticker_field
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = ["_".join(c).strip() for c in df.columns]
            df.index.name = "date"
            return df
        except Exception as e:
            self.logger.error(f"Price fetch failed: {e}")
            return pd.DataFrame()

    # ── Financial statements ────────────────────────────────────────────────────
    def _fetch_statements(self, ticker: str) -> dict[str, pd.DataFrame | None]:
        self.logger.info(f"Fetching financial statements for {ticker}")
        t = yf.Ticker(ticker)
        stmts = {}
        try:
            stmts["income_annual"]     = self._transpose_stmt(t.financials)
            stmts["income_quarterly"]  = self._transpose_stmt(t.quarterly_financials)
            stmts["balance_annual"]    = self._transpose_stmt(t.balance_sheet)
            stmts["balance_quarterly"] = self._transpose_stmt(t.quarterly_balance_sheet)
            stmts["cashflow_annual"]   = self._transpose_stmt(t.cashflow)
            stmts["cashflow_quarterly"]= self._transpose_stmt(t.quarterly_cashflow)
        except Exception as e:
            self.logger.error(f"Statement fetch for {ticker} failed: {e}")
        return stmts

    def _transpose_stmt(self, df: pd.DataFrame | None) -> pd.DataFrame | None:
        """yfinance returns statements with dates as columns; transpose so dates are rows."""
        if df is None or df.empty:
            return None
        df = df.T.copy()
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df.columns = [str(c) for c in df.columns]
        return df

    # ── Load cached ────────────────────────────────────────────────────────────
    def load_all(self) -> dict[str, pd.DataFrame]:
        """Load everything from disk without re-fetching."""
        out = {}
        for f in self.raw_dir.glob("*.csv"):
            name = f.stem
            out[name] = self.load_raw(name)
        return out
