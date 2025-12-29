"""Streaming data collection orchestrator with resume capability."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import List, Optional, Set, Tuple

import pandas as pd
from tqdm import tqdm

from ..config import Config
from ..graph import GraphBuilder, Neo4jClient
from ..utils import measure_time
from .dart import DartCollector
from .kis import KISCollector, KISTokenManager
from .krx import KRXCollector
from .mongodb import MongoDBCollector

logger = logging.getLogger(__name__)


class StreamingOrchestrator:
    """Orchestrates streaming data collection with resume capability."""

    def __init__(
        self,
        config: Config,
        date_list: List[str],
        neo4j_client: Neo4jClient,
        env_path: str = ".env",
        skip_existing: bool = True,
        max_workers: Optional[int] = None,
    ):
        """Initialize streaming orchestrator.

        Args:
            config: Application configuration
            date_list: List of dates to collect data for
            neo4j_client: Neo4j client for graph operations
            env_path: Path to .env file for token updates
            skip_existing: Skip stocks that already exist in database
            max_workers: Maximum number of parallel workers. If None, processes
                        sequentially. Recommended: 2-4 to avoid API rate limits.
        """
        self.config = config
        self.date_list = date_list
        self.neo4j_client = neo4j_client
        self.skip_existing = skip_existing
        self.max_workers = max_workers
        self.env_path = env_path

        self.kis_token_manager = KISTokenManager(config.kis, env_path)
        self.kis_collector = KISCollector(
            config.kis, config.sleep_seconds, env_path, token_manager=self.kis_token_manager
        )
        # Initialize collectors (shared for sequential processing)
        self.krx_collector = KRXCollector(config.sleep_seconds)
        self.dart_collector = DartCollector(config.dart_api_key, config.sleep_seconds)
        self.mongodb_collector = MongoDBCollector(config.mongodb)

        # Initialize graph builder
        self.graph_builder = GraphBuilder(neo4j_client)

        # Track processed stocks (thread-safe)
        self.processed_stocks: Set[str] = set()
        self.failed_stocks: Set[str] = set()
        self._lock = Lock()
        self._thread_local = threading.local()

    def _get_thread_collectors(self) -> Tuple[KISCollector, DartCollector]:
        """Get or create thread-local collectors.

        Returns:
            Tuple of (KISCollector, DartCollector)
        """
        if not hasattr(self._thread_local, "kis_collector"):
            self._thread_local.kis_collector = KISCollector(
                self.config.kis,
                self.config.sleep_seconds,
                self.env_path,
                token_manager=self.kis_token_manager,
            )
        if not hasattr(self._thread_local, "dart_collector"):
            self._thread_local.dart_collector = DartCollector(
                self.config.dart_api_key, self.config.sleep_seconds
            )
        return self._thread_local.kis_collector, self._thread_local.dart_collector

    def get_stocks_to_process(self, all_stock_codes: List[str]) -> List[str]:
        """Get list of stocks that need to be processed.

        Args:
            all_stock_codes: All available stock codes

        Returns:
            List of stock codes to process
        """
        if not self.skip_existing:
            return all_stock_codes

        # Get already processed stocks from Neo4j
        existing_stocks = self.neo4j_client.get_processed_stocks()
        logger.info(f"Found {len(existing_stocks)} stocks already in database")

        # Filter out existing stocks
        stocks_to_process = [
            code for code in all_stock_codes if code not in existing_stocks
        ]
        logger.info(
            f"Will process {len(stocks_to_process)} stocks "
            f"(skipping {len(existing_stocks)} existing)"
        )

        return stocks_to_process

    def collect_static_data(self) -> pd.DataFrame:
        """Collect static data (company info and competitors).

        Returns:
            DataFrame with company and competitor information
        """
        logger.info("[1. Collecting static data (company + competitors)...]")

        # Get company info from KRX
        company_df_krx = self.krx_collector.collect()
        logger.info(f"Collected {len(company_df_krx)} companies from KRX")

        # Get competitor info from MongoDB
        competitor_df = self.mongodb_collector.collect()
        logger.info(f"Collected {len(competitor_df)} competitor records from MongoDB")
        if not competitor_df.empty:
            logger.debug(f"Competitor DF sample:\n{competitor_df.head(1)}")

        # Merge company and competitor data
        static_df = pd.merge(company_df_krx, competitor_df, on="stock_code", how="left")

        merged_count = static_df["compete_code_li"].notna().sum()
        logger.info(f"Merged competitor data for {merged_count} companies")

        # Fill missing competitor data
        static_df["compete_code_li"] = static_df["compete_code_li"].apply(
            lambda x: x if isinstance(x, list) else []
        )

        return static_df

    def _process_single_stock(
        self, stock_code: str, static_df: pd.DataFrame
    ) -> Tuple[bool, str]:
        """Process a single stock.

        Args:
            stock_code: Stock code to process
            static_df: DataFrame with static company data

        Returns:
            Tuple of (success: bool, stock_code: str)
        """
        try:
            # Check if already processed (double check)
            if self.skip_existing and self.neo4j_client.check_stock_exists(stock_code):
                logger.debug(f"[{stock_code}] Already exists, skipping")
                return True, stock_code

            # Get static data for this stock
            stock_static = static_df[static_df["stock_code"] == stock_code]
            if stock_static.empty:
                logger.warning(f"[{stock_code}] No static data found")
                with self._lock:
                    self.failed_stocks.add(stock_code)
                return False, stock_code

            # Get thread-local collectors (reused per thread)
            kis_collector, dart_collector = self._get_thread_collectors()

            # Collect KIS data (company info + price)
            company_df_kis, price_df = kis_collector.collect(
                [stock_code], self.date_list
            )

            # Collect financial statements
            fs_df = dart_collector.collect([stock_code], self.date_list[0])

            # Merge all data
            stock_data = self._merge_stock_data(
                stock_static, company_df_kis, price_df, fs_df
            )

            if stock_data.empty:
                logger.warning(f"[{stock_code}] Failed to merge data")
                with self._lock:
                    self.failed_stocks.add(stock_code)
                return False, stock_code

            # Build and upload to Neo4j
            self.graph_builder.build_graph(stock_data, stock_code, self.date_list)

            with self._lock:
                self.processed_stocks.add(stock_code)

            logger.debug(f"[streaming][{stock_code}] Successfully processed")
            return True, stock_code

        except Exception as e:
            logger.error(f"[{stock_code}] Error processing: {e}")
            with self._lock:
                self.failed_stocks.add(stock_code)
            return False, stock_code

    def _merge_stock_data(
        self,
        static_df: pd.DataFrame,
        company_df_kis: pd.DataFrame,
        price_df: pd.DataFrame,
        fs_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Merge all data for a stock.

        Args:
            static_df: Static company data
            company_df_kis: KIS company data
            price_df: Price data
            fs_df: Financial statement data

        Returns:
            Merged DataFrame
        """
        # Merge KIS company data
        result = pd.merge(static_df, company_df_kis, on="stock_code", how="left")

        # Merge price data
        result = pd.merge(result, price_df, on="stock_code", how="left")

        # Merge financial statements
        result = pd.merge(result, fs_df, on="stock_code", how="left")

        return result

    @measure_time
    def run_streaming(self) -> dict:
        """Run streaming data collection and upload.

        Returns:
            Dictionary with processing statistics
        """
        logger.info(
            "[streaming] Starting data collection with resume capability "
            "(skip_existing=%s, max_workers=%s)",
            self.skip_existing,
            self.max_workers,
        )

        # Step 1: Collect static data
        static_df = self.collect_static_data()
        all_stock_codes = static_df["stock_code"].tolist()

        # Step 2: Get stocks to process (skip existing if enabled)
        stocks_to_process = self.get_stocks_to_process(all_stock_codes)

        if not stocks_to_process:
            logger.info("No stocks to process. All stocks are up to date.")
            return {
                "total_stocks": len(all_stock_codes),
                "processed": 0,
                "skipped": len(all_stock_codes),
                "failed": 0,
            }

        # Step 3: Process all stocks
        total_success = 0
        total_failed = 0

        logger.info(
            "[streaming] Processing %d stocks (Parallel: %s)",
            len(stocks_to_process),
            self.max_workers is not None,
        )

        if self.max_workers is None or self.max_workers <= 1:
            # Sequential processing
            for stock_code in tqdm(stocks_to_process, desc="Processing"):
                success, _ = self._process_single_stock(stock_code, static_df)
                if success:
                    total_success += 1
                else:
                    total_failed += 1
        else:
            # Parallel processing with single ThreadPool
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_stock = {
                    executor.submit(
                        self._process_single_stock, stock_code, static_df
                    ): stock_code
                    for stock_code in stocks_to_process
                }

                for future in tqdm(
                    as_completed(future_to_stock),
                    total=len(stocks_to_process),
                    desc="Processing",
                ):
                    success, _ = future.result()
                    if success:
                        total_success += 1
                    else:
                        total_failed += 1

        # Step 4: Summary
        logger.info("[streaming] Streaming collection completed")
        logger.info("[streaming] Total stocks: %d", len(all_stock_codes))
        logger.info("[streaming] Processed: %d", total_success)
        logger.info(
            "[streaming] Skipped (existing): %d",
            len(all_stock_codes) - len(stocks_to_process),
        )
        logger.info("[streaming] Failed: %d", total_failed)

        if self.failed_stocks:
            logger.warning(
                "[streaming] Failed stocks (sample): %s",
                sorted(self.failed_stocks)[:10],
            )

        return {
            "total_stocks": len(all_stock_codes),
            "processed": total_success,
            "skipped": len(all_stock_codes) - len(stocks_to_process),
            "failed": total_failed,
            "failed_stocks": list(self.failed_stocks),
        }

    def update_existing_dates(self, stock_codes: Optional[List[str]] = None) -> dict:
        """Update price data for existing stocks with new dates.

        Args:
            stock_codes: Optional list of specific stocks to update.
                        If None, updates all existing stocks.

        Returns:
            Dictionary with update statistics
        """
        logger.info(
            "[streaming] Updating existing stocks with new dates "
            "(provided_codes=%s)",
            stock_codes is not None,
        )

        # Get stocks to update
        if stock_codes is None:
            stock_codes = list(self.neo4j_client.get_processed_stocks())
            logger.info(
                "[streaming] Found %d existing stocks to update", len(stock_codes)
            )

        total_updated = 0
        total_failed = 0

        for stock_code in tqdm(stock_codes, desc="Updating stocks"):
            try:
                # Get already processed dates
                existing_dates = self.neo4j_client.get_processed_dates_for_stock(
                    stock_code
                )

                # Find new dates to process
                new_dates = [d for d in self.date_list if d not in existing_dates]

                if not new_dates:
                    logger.debug(
                        "[streaming][%s] All dates already processed", stock_code
                    )
                    continue

                logger.info(
                    "[streaming][%s] Updating %d new dates: %s",
                    stock_code,
                    len(new_dates),
                    new_dates,
                )

                # Collect price data for new dates only
                _, price_df = self.kis_collector.collect([stock_code], new_dates)

                if price_df.empty:
                    logger.warning(
                        "[streaming][%s] No price data collected", stock_code
                    )
                    total_failed += 1
                    continue

                # Get static data (already in DB, but needed for graph building)
                static_df = self.collect_static_data()
                stock_static = static_df[static_df["stock_code"] == stock_code]

                # Build graph for new dates only
                self.graph_builder.build_graph(
                    pd.merge(stock_static, price_df, on="stock_code"),
                    stock_code,
                    new_dates,
                )

                total_updated += 1
                logger.info("[streaming][%s] Successfully updated", stock_code)

            except Exception as e:
                logger.error("[streaming][%s] Error updating: %s", stock_code, e)
                total_failed += 1
                continue

        logger.info(
            "[streaming] Update completed (updated=%d, failed=%d)",
            total_updated,
            total_failed,
        )

        return {"updated": total_updated, "failed": total_failed}
