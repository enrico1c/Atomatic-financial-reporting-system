"""
Date utility helpers shared across modules.
"""

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def n_years_ago(n: int) -> str:
    return (datetime.now() - relativedelta(years=n)).strftime("%Y-%m-%d")


def first_of_month(dt: datetime = None) -> str:
    dt = dt or datetime.now()
    return dt.replace(day=1).strftime("%Y-%m-%d")


def last_month_range() -> tuple[str, str]:
    today = datetime.now()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev.strftime("%Y-%m-%d"), last_prev.strftime("%Y-%m-%d")


def safe_to_datetime(series):
    """Coerce a pandas Series to datetime, returning NaT on failure."""
    import pandas as pd
    return pd.to_datetime(series, errors="coerce")
