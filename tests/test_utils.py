"""Tests for utility functions."""

import pytest
from datetime import datetime

from stockelper_kg.utils import get_date_list


class TestDateUtils:
    """Test date utility functions."""

    def test_get_date_list_single_day(self):
        """Test date list generation for single day."""
        result = get_date_list("20250101", "20250101")
        assert result == ["20250101"]

    def test_get_date_list_multiple_days(self):
        """Test date list generation for multiple days."""
        result = get_date_list("20250101", "20250103")
        assert result == ["20250101", "20250102", "20250103"]

    def test_get_date_list_invalid_format(self):
        """Test date list generation with invalid format."""
        with pytest.raises(ValueError):
            get_date_list("2025-01-01", "2025-01-03")

    def test_get_date_list_reverse_order(self):
        """Test date list generation with reverse order."""
        result = get_date_list("20250103", "20250101")
        assert result == []
