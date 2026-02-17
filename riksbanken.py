"""Riksbanken SWEA API client for fetching FX rates."""

from datetime import date, timedelta
import requests
import streamlit as st

BASE_URL = "https://api.riksbank.se/swea/v1"

CURRENCY_SERIES = {
    "EUR": "SEKEURPMI",
    "USD": "SEKUSDPMI",
    "GBP": "SEKGBPPMI",
    "NOK": "SEKNOKPMI",
    "DKK": "SEKDKKPMI",
    "CHF": "SEKCHFPMI",
    "JPY": "SEKJPYPMI",
    "CAD": "SEKCADPMI",
    "AUD": "SEKAUDPMI",
    "NZD": "SEKNZDPMI",
    "PLN": "SEKPLNPMI",
    "CZK": "SEKCZKPMI",
    "HUF": "SEKHUFPMI",
    "TRY": "SEKTRYPMI",
    "CNY": "SEKCNYPMI",
    "HKD": "SEKHKDPMI",
    "SGD": "SEKSGDPMI",
    "THB": "SEKTHBPMI",
    "KRW": "SEKKRWPMI",
    "INR": "SEKINRPMI",
}


def get_available_currencies() -> list[str]:
    return sorted(CURRENCY_SERIES.keys())


def _last_business_day(d: date) -> date:
    """Find the last business day on or before the given date."""
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d -= timedelta(days=1)
    return d


def _previous_month_end(reference_date: date) -> date:
    """Get the last day of the previous month."""
    first_of_month = reference_date.replace(day=1)
    return first_of_month - timedelta(days=1)


@st.cache_data(ttl=3600, show_spinner=False)
def get_fx_rate(currency: str, reference_date: date) -> tuple[float | None, date | None]:
    """Fetch the closing FX rate from Riksbanken for the end of the previous month.

    The API returns rates starting FROM the query date forward, so we query
    from a few days before month-end and pick the last rate on or before
    the actual month-end date.

    Args:
        currency: Currency code (e.g. "EUR", "USD")
        reference_date: The transaction date — rate will be fetched for
                        the last available rate of the previous month.

    Returns:
        Tuple of (rate, rate_date) or (None, None) on failure.
    """
    series_id = CURRENCY_SERIES.get(currency.upper())
    if not series_id:
        return None, None

    month_end = _previous_month_end(reference_date)
    # Query from 10 days before month-end to ensure we capture the last trading day
    query_from = month_end - timedelta(days=10)

    url = f"{BASE_URL}/Observations/{series_id}/{query_from.isoformat()}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                # Find the last observation on or before month-end
                best = None
                for obs in data:
                    obs_date = date.fromisoformat(obs["date"])
                    if obs_date <= month_end:
                        best = obs
                    else:
                        break  # dates are sorted ascending, no need to continue
                if best:
                    return float(best["value"]), date.fromisoformat(best["date"])
    except (requests.RequestException, ValueError, KeyError):
        pass

    return None, None
