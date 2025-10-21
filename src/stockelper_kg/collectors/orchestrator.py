"""Data collection orchestrator."""

import logging

import pandas as pd

from ..config import Config
from ..utils import measure_time
from .dart import DartCollector
from .kis import KISCollector
from .krx import KRXCollector
from .mongodb import MongoDBCollector

logger = logging.getLogger(__name__)


class DataOrchestrator:
    """Orchestrates data collection from multiple sources."""

    def __init__(self, config: Config, date_list: list, env_path: str = ".env"):
        """Initialize data orchestrator.

        Args:
            config: Application configuration
            date_list: List of dates to collect data for
            env_path: Path to .env file for token updates
        """
        self.config = config
        self.date_list = date_list
        self.krx_collector = KRXCollector(config.sleep_seconds)
        self.kis_collector = KISCollector(config.kis, config.sleep_seconds, env_path)
        self.dart_collector = DartCollector(config.dart_api_key, config.sleep_seconds)
        self.mongodb_collector = MongoDBCollector(config.mongodb)

        self.company_df = None
        self.price_df = None
        self.competitor_df = None
        self.fs_df = None
        self.total_df = None

    @measure_time
    def collect_company_info(self):
        """Collect company information from KRX and KIS."""
        logger.info("[1. Collecting company info...]")
        company_df_krx = self.krx_collector.collect()
        stock_codes = company_df_krx["stock_code"].tolist()

        company_df_kis, _ = self.kis_collector.collect(stock_codes, [])
        self.company_df = pd.merge(
            company_df_krx, company_df_kis, how="left", on="stock_code"
        )

    @measure_time
    def collect_price_info(self):
        """Collect price and indicator information."""
        logger.info("[2. Collecting price info...]")
        stock_codes = self.company_df["stock_code"].tolist()
        _, self.price_df = self.kis_collector.collect(stock_codes, self.date_list)

    @measure_time
    def collect_competitor_info(self):
        """Collect competitor information from MongoDB."""
        logger.info("[3. Collecting competitor info...]")
        self.competitor_df = self.mongodb_collector.collect()

        stock_codes = self.company_df["stock_code"].tolist()
        existing_stock_codes = (
            set(self.competitor_df["stock_code"])
            if not self.competitor_df.empty
            else set()
        )

        missing_stock_codes = set(stock_codes) - existing_stock_codes
        for stock_code in missing_stock_codes:
            missing_row = pd.DataFrame(
                {"stock_code": [stock_code], "compete_code_li": [[]]}
            )
            self.competitor_df = pd.concat(
                [self.competitor_df, missing_row], ignore_index=True
            )

    @measure_time
    def collect_financial_statements(self):
        """Collect financial statement information."""
        logger.info("[4. Collecting financial statements...]")
        stock_codes = self.company_df["stock_code"].tolist()
        date = self.date_list[0]
        self.fs_df = self.dart_collector.collect(stock_codes, date)

    def create_total_df(self) -> pd.DataFrame:
        """Merge all collected data into single DataFrame.

        Returns:
            Combined DataFrame with all data
        """
        logger.info("[5. Creating total DataFrame...]")
        self.total_df = pd.merge(self.company_df, self.price_df, on="stock_code", how="left")
        self.total_df = pd.merge(self.total_df, self.competitor_df, on="stock_code", how="left")
        self.total_df = pd.merge(self.total_df, self.fs_df, on="stock_code", how="left")
        return self.total_df

    @measure_time
    def run_all(self) -> pd.DataFrame:
        """Run all data collection steps.

        Returns:
            Combined DataFrame with all collected data
        """
        self.collect_company_info()
        self.collect_price_info()
        self.collect_competitor_info()
        self.collect_financial_statements()
        return self.create_total_df()
