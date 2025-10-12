"""Configuration management for Stockelper KG."""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Neo4jConfig:
    """Neo4j database configuration."""

    uri: str
    user: str
    password: str


@dataclass
class KISConfig:
    """Korea Investment & Securities API configuration."""

    app_key: str
    app_secret: str
    access_token: Optional[str] = None
    access_number: Optional[str] = None
    account_number: Optional[str] = None
    account_code: Optional[str] = None
    virtual: bool = True


@dataclass
class MongoDBConfig:
    """MongoDB configuration."""

    uri: str
    database: str
    collection: str


@dataclass
class Config:
    """Application configuration."""

    neo4j: Neo4jConfig
    kis: KISConfig
    mongodb: MongoDBConfig
    dart_api_key: str
    sleep_seconds: float = 0.1

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "Config":
        """Load configuration from environment variables.

        Args:
            env_path: Path to .env file

        Returns:
            Config instance

        Raises:
            ValueError: If required environment variables are missing
        """
        load_dotenv(dotenv_path=env_path)

        # Neo4j
        neo4j = Neo4jConfig(
            uri=cls._get_required_env("NEO4J_URI"),
            user=cls._get_required_env("NEO4J_USER"),
            password=cls._get_required_env("NEO4J_PASSWORD"),
        )

        # KIS
        kis = KISConfig(
            app_key=cls._get_required_env("KIS_APP_KEY"),
            app_secret=cls._get_required_env("KIS_APP_SECRET"),
            access_token=os.getenv("KIS_ACCESS_TOKEN"),
            access_number=os.getenv("KIS_ACCESS_NUMBER"),
            account_number=os.getenv("KIS_ACCOUNT_NUMBER"),
            account_code=os.getenv("KIS_ACCOUNT_CODE"),
            virtual=os.getenv("KIS_VIRTUAL", "true").lower() == "true",
        )

        # MongoDB
        mongodb = MongoDBConfig(
            uri=cls._get_required_env("DB_URI"),
            database=cls._get_required_env("DB_NAME"),
            collection=cls._get_required_env("DB_COLLECTION_NAME"),
        )

        # DART
        dart_api_key = cls._get_required_env("OPEN_DART_API_KEY")

        return cls(
            neo4j=neo4j,
            kis=kis,
            mongodb=mongodb,
            dart_api_key=dart_api_key,
        )

    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get required environment variable.

        Args:
            key: Environment variable name

        Returns:
            Environment variable value

        Raises:
            ValueError: If environment variable is not set
        """
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
