"""
Fetch market data from Yahoo Finance and write data/market.json.

Run by GitHub Actions every 5 minutes during market hours.
The dashboard loads this file directly (same origin, no CORS proxy needed).

Output format mirrors the Yahoo Finance v7/v8 API so the existing
frontend parsing code works without changes.
"""

import json
import datetime
import os
import sys

import yfinance as yf

EQUITY = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'JPM', 'GS', 'BAC', 'XOM', 'SPY', 'QQQ']
MACRO  = ['^TNX', '^IRX', '^VIX', 'GC=F', 'CL=F', 'EURUSD=X', '^GSPC', 'DX-Y.NYB']
ALL    = EQUITY + MACRO
CHART_SYMS = ['SPY', 'QQQ']   # intraday charts pre-fetched for the market panel

OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'market.json')


def fetch_quotes(symbols: list[str]) -> list[dict]:
    """Return a list of quote dicts in Yahoo Finance v7 shape."""
    results = []
    try:
        # yf.download gives us OHLCV; fast_info gives price/prev_close quickly
        tickers = yf.Tickers(' '.join(symbols))
    except Exception as e:
        print(f"Tickers init error: {e}", file=sys.stderr)
        return results

    for sym in symbols:
        try:
            fi = tickers.tickers[sym].fast_info
            price = fi.last_price
            prev  = fi.previous_close
            if price is None:
                continue
            change     = (price - prev) if prev else 0.0
            change_pct = (change / prev * 100) if prev else 0.0
            results.append({
                'symbol':                    sym,
                'regularMarketPrice':        round(float(price), 4),
                'regularMarketChange':       round(float(change), 4),
                'regularMarketChangePercent': round(float(change_pct), 4),
            })
        except Exception as e:
            print(f"Quote warning [{sym}]: {e}", file=sys.stderr)

    return results


def fetch_chart(sym: str) -> dict | None:
    """Return a chart payload in Yahoo Finance v8 shape."""
    try:
        hist = yf.Ticker(sym).history(period='1d', interval='1m', auto_adjust=True)
        if hist.empty:
            return None
        timestamps = [int(ts.timestamp()) for ts in hist.index]
        closes     = [round(float(c), 4) if c == c else None for c in hist['Close']]
        return {
            'chart': {
                'result': [{
                    'timestamp': timestamps,
                    'indicators': {'quote': [{'close': closes}]},
                }]
            }
        }
    except Exception as e:
        print(f"Chart warning [{sym}]: {e}", file=sys.stderr)
        return None


def main() -> None:
    print(f"Fetching {len(ALL)} symbols…")
    quotes = fetch_quotes(ALL)
    print(f"  Got {len(quotes)} quotes")

    charts: dict[str, dict] = {}
    for sym in CHART_SYMS:
        c = fetch_chart(sym)
        if c:
            charts[sym] = c
            bars = len(c['chart']['result'][0]['timestamp'])
            print(f"  Chart {sym}: {bars} bars")

    payload = {
        'updated':       datetime.datetime.utcnow().isoformat(),
        'quoteResponse': {'result': quotes},
        'charts':        charts,
    }

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT)), exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))

    print(f"Wrote {OUTPUT}")


if __name__ == '__main__':
    main()
