"""Legacy batch data collection orchestrator."""

import logging
from typing import List

import pandas as pd

from ..config import Config
from .dart import DartCollector
from .kis import KISCollector
from .krx import KRXCollector
from .mongodb import MongoDBCollector

logger = logging.getLogger(__name__)


class DataOrchestrator:
    """Orchestrates batch data collection (legacy mode).

    This class collects all data for all stocks in batch mode,
    then returns a merged DataFrame for graph building.
    """

    def __init__(self, config: Config, date_list: List[str], env_path: str = ".env"):
        """Initialize data orchestrator.

        Args:
            config: Application configuration
            date_list: List of dates to collect data for
            env_path: Path to .env file for token updates
        """
        self.config = config
        self.date_list = date_list
        self.env_path = env_path

        # Initialize collectors
        self.krx_collector = KRXCollector(config.sleep_seconds)
        self.kis_collector = KISCollector(config.kis, config.sleep_seconds, env_path)
        self.dart_collector = DartCollector(config.dart_api_key, config.sleep_seconds)
        self.mongodb_collector = MongoDBCollector(config.mongodb)

    def run_all(self) -> pd.DataFrame:
        """Collect all data for all stocks and return merged DataFrame.

        Returns:
            Merged DataFrame with all stock data
        """
        logger.info("[orchestrator] Start batch data collection (legacy mode)")

        # Step 1: Collect static data (company info and competitors)
        logger.info("[1/4] Collecting static data (company + competitors)")
        company_df_krx = self.krx_collector.collect()
        logger.info(
            "[1/4] Collected company info from KRX: %d companies", len(company_df_krx)
        )

        competitor_df = self.mongodb_collector.collect()
        logger.info("[1/4] Collected competitor data from MongoDB")

        # Merge company and competitor data
        static_df = pd.merge(company_df_krx, competitor_df, on="stock_code", how="left")
        static_df["compete_code_li"] = static_df["compete_code_li"].apply(
            lambda x: x if isinstance(x, list) else []
        )

        # Step 2: Get all stock codes
        all_stock_codes = static_df["stock_code"].tolist()
        logger.info("[orchestrator] Total stocks to process: %d", len(all_stock_codes))

        # Step 3: Collect KIS data (company info + price) for all stocks
        logger.info("[2/4] Collecting KIS data (company info + price)")
        company_df_kis, price_df = self.kis_collector.collect(
            all_stock_codes, self.date_list
        )
        logger.info(
            "[2/4] Collected KIS company data: %d companies", len(company_df_kis)
        )

        # Step 4: Collect financial statements for all stocks
        logger.info("[3/4] Collecting financial statements from DART")
        fs_df = self.dart_collector.collect(all_stock_codes, self.date_list[0])
        logger.info("[3/4] Collected financial statements: %d companies", len(fs_df))

        # Step 5: Merge all data
        logger.info("[4/4] Merging all data")
        result = pd.merge(static_df, company_df_kis, on="stock_code", how="left")
        result = pd.merge(result, price_df, on="stock_code", how="left")
        result = pd.merge(result, fs_df, on="stock_code", how="left")

        logger.info(
            "[orchestrator] Batch data collection completed, final rows: %d",
            len(result),
        )

        return result
