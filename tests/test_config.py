"""Tests for configuration module."""

import os
import pytest
from unittest.mock import patch

from stockelper_kg.config import Config


class TestConfig:
    """Test configuration loading."""

    @patch.dict(
        os.environ,
        {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "password",
            "KIS_APP_KEY": "test_key",
            "KIS_APP_SECRET": "test_secret",
            "DB_URI": "mongodb://localhost:27017",
            "DB_NAME": "test_db",
            "DB_COLLECTION_NAME": "test_collection",
            "OPEN_DART_API_KEY": "test_dart_key",
        },
    )
    def test_config_from_env(self):
        """Test configuration loading from environment variables."""
        config = Config.from_env()

        assert config.neo4j.uri == "bolt://localhost:7687"
        assert config.neo4j.user == "neo4j"
        assert config.neo4j.password == "password"
        assert config.kis.app_key == "test_key"
        assert config.kis.app_secret == "test_secret"
        assert config.mongodb.uri == "mongodb://localhost:27017"
        assert config.mongodb.database == "test_db"
        assert config.dart_api_key == "test_dart_key"

    @patch.dict(os.environ, {}, clear=True)
    def test_config_missing_required_env(self):
        """Test configuration with missing required environment variables."""
        with pytest.raises(ValueError, match="Required environment variable"):
            Config.from_env()
