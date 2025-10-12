"""Streaming data collection orchestrator with resume capability."""

import logging
from typing import List, Optional, Set

import pandas as pd
from tqdm import tqdm

from ..config import Config
from ..graph import GraphBuilder, Neo4jClient
from ..utils import measure_time
from .dart import DartCollector
from .kis import KISCollector
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
        batch_size: int = 100,
        skip_existing: bool = True,
    ):
        """Initialize streaming orchestrator.

        Args:
            config: Application configuration
            date_list: List of dates to collect data for
            neo4j_client: Neo4j client for graph operations
            env_path: Path to .env file for token updates
            batch_size: Number of stocks to process in each batch
            skip_existing: Skip stocks that already exist in database
        """
        self.config = config
        self.date_list = date_list
        self.neo4j_client = neo4j_client
        self.batch_size = batch_size
        self.skip_existing = skip_existing

        # Initialize collectors
        self.krx_collector = KRXCollector(config.sleep_seconds)
        self.kis_collector = KISCollector(config.kis, config.sleep_seconds, env_path)
        self.dart_collector = DartCollector(config.dart_api_key, config.sleep_seconds)
        self.mongodb_collector = MongoDBCollector(config.mongodb)

        # Initialize graph builder
        self.graph_builder = GraphBuilder(neo4j_client)

        # Track processed stocks
        self.processed_stocks: Set[str] = set()
        self.failed_stocks: Set[str] = set()

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
        logger.info(f"Collected competitor data from MongoDB")

        # Merge company and competitor data
        static_df = pd.merge(
            company_df_krx, competitor_df, on="stock_code", how="left"
        )

        # Fill missing competitor data
        static_df["compete_code_li"] = static_df["compete_code_li"].apply(
            lambda x: x if isinstance(x, list) else []
        )

        return static_df

    def process_stock_batch(
        self, stock_codes: List[str], static_df: pd.DataFrame
    ) -> tuple:
        """Process a batch of stocks.

        Args:
            stock_codes: List of stock codes to process
            static_df: DataFrame with static company data

        Returns:
            Tuple of (success_count, failed_count)
        """
        success_count = 0
        failed_count = 0

        for stock_code in tqdm(stock_codes, desc="Processing batch"):
            try:
                # Check if already processed (double check)
                if self.skip_existing and self.neo4j_client.check_stock_exists(
                    stock_code
                ):
                    logger.debug(f"[{stock_code}] Already exists, skipping")
                    continue

                # Get static data for this stock
                stock_static = static_df[static_df["stock_code"] == stock_code]
                if stock_static.empty:
                    logger.warning(f"[{stock_code}] No static data found")
                    failed_count += 1
                    self.failed_stocks.add(stock_code)
                    continue

                # Collect KIS data (company info + price)
                company_df_kis, price_df = self.kis_collector.collect(
                    [stock_code], self.date_list
                )

                # Collect financial statements
                fs_df = self.dart_collector.collect([stock_code], self.date_list[0])

                # Merge all data
                stock_data = self._merge_stock_data(
                    stock_static, company_df_kis, price_df, fs_df
                )

                if stock_data.empty:
                    logger.warning(f"[{stock_code}] Failed to merge data")
                    failed_count += 1
                    self.failed_stocks.add(stock_code)
                    continue

                # Build and upload to Neo4j
                self.graph_builder.build_graph(stock_data, stock_code, self.date_list)

                self.processed_stocks.add(stock_code)
                success_count += 1

                logger.info(
                    f"[{stock_code}] Successfully processed "
                    f"({success_count}/{len(stock_codes)})"
                )

            except Exception as e:
                logger.error(f"[{stock_code}] Error processing: {e}")
                failed_count += 1
                self.failed_stocks.add(stock_code)
                continue

        return success_count, failed_count

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
        logger.info("=" * 70)
        logger.info("Starting streaming data collection with resume capability")
        logger.info("=" * 70)

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

        # Step 3: Process in batches
        total_success = 0
        total_failed = 0

        for i in range(0, len(stocks_to_process), self.batch_size):
            batch = stocks_to_process[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (len(stocks_to_process) + self.batch_size - 1) // self.batch_size

            logger.info(f"\n{'=' * 70}")
            logger.info(
                f"Processing batch {batch_num}/{total_batches} "
                f"({len(batch)} stocks)"
            )
            logger.info(f"{'=' * 70}")

            success, failed = self.process_stock_batch(batch, static_df)
            total_success += success
            total_failed += failed

            logger.info(
                f"Batch {batch_num} complete: "
                f"{success} success, {failed} failed"
            )

        # Step 4: Summary
        logger.info(f"\n{'=' * 70}")
        logger.info("Streaming collection completed!")
        logger.info(f"{'=' * 70}")
        logger.info(f"Total stocks: {len(all_stock_codes)}")
        logger.info(f"Processed: {total_success}")
        logger.info(f"Skipped (existing): {len(all_stock_codes) - len(stocks_to_process)}")
        logger.info(f"Failed: {total_failed}")

        if self.failed_stocks:
            logger.warning(f"Failed stocks: {sorted(self.failed_stocks)[:10]}...")

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
        logger.info("=" * 70)
        logger.info("Updating existing stocks with new dates")
        logger.info("=" * 70)

        # Get stocks to update
        if stock_codes is None:
            stock_codes = list(self.neo4j_client.get_processed_stocks())
            logger.info(f"Found {len(stock_codes)} existing stocks to update")

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
                    logger.debug(f"[{stock_code}] All dates already processed")
                    continue

                logger.info(
                    f"[{stock_code}] Updating {len(new_dates)} new dates: {new_dates}"
                )

                # Collect price data for new dates only
                _, price_df = self.kis_collector.collect([stock_code], new_dates)

                if price_df.empty:
                    logger.warning(f"[{stock_code}] No price data collected")
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
                logger.info(f"[{stock_code}] Successfully updated")

            except Exception as e:
                logger.error(f"[{stock_code}] Error updating: {e}")
                total_failed += 1
                continue

        logger.info(f"\n{'=' * 70}")
        logger.info("Update completed!")
        logger.info(f"Updated: {total_updated}, Failed: {total_failed}")
        logger.info(f"{'=' * 70}")

        return {"updated": total_updated, "failed": total_failed}
