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
def get_fx_rate(currency: str, reference_date: date) -> float | None:
    """Fetch the closing FX rate from Riksbanken for the end of the previous month.

    Args:
        currency: Currency code (e.g. "EUR", "USD")
        reference_date: The transaction date — rate will be fetched for
                        the last business day of the previous month.

    Returns:
        The exchange rate (SEK per 1 unit of foreign currency), or None on failure.
    """
    series_id = CURRENCY_SERIES.get(currency.upper())
    if not series_id:
        return None

    month_end = _previous_month_end(reference_date)
    target_date = _last_business_day(month_end)

    # Try up to 5 business days back in case of holidays
    for _ in range(5):
        url = f"{BASE_URL}/Observations/{series_id}/{target_date.isoformat()}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    return float(data[0]["value"])
                if isinstance(data, dict) and "value" in data:
                    return float(data["value"])
        except (requests.RequestException, ValueError, KeyError):
            pass
        target_date -= timedelta(days=1)
        target_date = _last_business_day(target_date)

    return None
