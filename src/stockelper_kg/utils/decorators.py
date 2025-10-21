"""Utility decorators."""

import logging
import time
from datetime import datetime
from functools import wraps
from typing import Callable, TypeVar, cast

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


def measure_time(func: F) -> F:
    """Measure and log function execution time.

    Args:
        func: Function to measure

    Returns:
        Wrapped function
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.info("-" * 70)
        logger.info(
            f"Start time: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}"
        )

        result = func(*args, **kwargs)

        end_time = time.time()
        elapsed = end_time - start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)

        logger.info(
            f"End time: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.info(f"Total Time: {hours:02d}:{minutes:02d}:{seconds:02d}")
        return result

    return cast(F, wrapper)
