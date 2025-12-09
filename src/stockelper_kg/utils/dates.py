"""Date utility functions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


def normalize_date(value: Any) -> Optional[str]:
    """Normalize input to YYYY-MM-DD string format.

    Handles YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD strings, and other common formats.
    Returns None if normalization fails or input is empty.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 8:
        return None

    try:
        return datetime.strptime(digits, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def build_date_properties(value: Any) -> Optional[Dict[str, Any]]:
    """Build canonical Date node properties from flexible input.

    - Accepts strings like YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD, etc.
    - Returns a mapping that always includes:
        - "date": YYYY-MM-DD
        - "formatted_date": YYYY-MM-DD
        - "year", "month", "day": integers
    - Returns None if the input cannot be normalised to a valid date.
    """
    canonical = normalize_date(value)
    if not canonical:
        return None

    try:
        dt = datetime.strptime(canonical, "%Y-%m-%d")
    except ValueError:
        # Guard against impossible dates that slipped through normalize_date
        return None

    return {
        "date": canonical,
        "formatted_date": canonical,
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
    }


def get_date_list(date_st: str, date_fn: str) -> List[str]:
    """Generate list of dates between start and end date.

    Args:
        date_st: Start date in YYYYMMDD format
        date_fn: End date in YYYYMMDD format

    Returns:
        List of dates in YYYYMMDD format

    Raises:
        ValueError: If date format is invalid
    """
    start_date = datetime.strptime(date_st, "%Y%m%d")
    end_date = datetime.strptime(date_fn, "%Y%m%d")

    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date.strftime("%Y%m%d"))
        current_date += timedelta(days=1)

    return date_list
