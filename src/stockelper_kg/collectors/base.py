"""Base collector class."""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Base class for data collectors."""

    def __init__(self, sleep_seconds: float = 0.1):
        """Initialize collector.

        Args:
            sleep_seconds: Seconds to sleep between API calls
        """
        self.sleep_seconds = sleep_seconds
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def collect(self, *args, **kwargs) -> Any:
        """Collect data from source.

        Returns:
            Collected data
        """
        pass
