"""Date utility functions."""

from datetime import datetime, timedelta
from typing import List


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
