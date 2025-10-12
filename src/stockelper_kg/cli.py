"""Command-line interface for stockelper-kg."""

import argparse
import logging
from datetime import datetime

from tqdm import tqdm

from .collectors import DataOrchestrator, StreamingOrchestrator
from .config import Config
from .graph import GraphBuilder, Neo4jClient
from .utils import get_date_list, measure_time

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate knowledge graph of stock domain"
    )
    parser.add_argument(
        "--date_st",
        type=str,
        required=True,
        help="Start date (format: YYYYMMDD)",
    )
    parser.add_argument(
        "--date_fn",
        type=str,
        required=True,
        help="Finish date (format: YYYYMMDD)",
    )
    parser.add_argument(
        "--env",
        type=str,
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Use streaming mode with resume capability (recommended)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for streaming mode (default: 100)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Process all stocks even if they exist in database",
    )
    parser.add_argument(
        "--update-only",
        action="store_true",
        help="Only update existing stocks with new dates",
    )
    args = parser.parse_args()

    # Validate date format
    try:
        datetime.strptime(args.date_st, "%Y%m%d")
        datetime.strptime(args.date_fn, "%Y%m%d")
    except ValueError:
        parser.error("Follow date format (format: YYYYMMDD)")

    return args


@measure_time
def main(
    date_st: str,
    date_fn: str,
    env_path: str = ".env",
    streaming: bool = False,
    batch_size: int = 100,
    skip_existing: bool = True,
    update_only: bool = False,
):
    """Main execution function.

    Args:
        date_st: Start date in YYYYMMDD format
        date_fn: End date in YYYYMMDD format
        env_path: Path to .env file
        streaming: Use streaming mode with resume capability
        batch_size: Batch size for streaming mode
        skip_existing: Skip stocks that already exist in database
        update_only: Only update existing stocks with new dates
    """
    # Load configuration
    config = Config.from_env(env_path)

    # Generate date list
    date_list = get_date_list(date_st, date_fn)
    logger.info(f"Processing dates: {date_st} ~ {date_fn} ({len(date_list)} days)")

    # Initialize Neo4j client
    client = Neo4jClient(config.neo4j)
    client.ensure_constraints()

    if streaming:
        # Use streaming orchestrator
        logger.info("Using STREAMING mode with resume capability")
        orchestrator = StreamingOrchestrator(
            config=config,
            date_list=date_list,
            neo4j_client=client,
            env_path=env_path,
            batch_size=batch_size,
            skip_existing=skip_existing,
        )

        if update_only:
            # Update existing stocks only
            stats = orchestrator.update_existing_dates()
        else:
            # Full streaming collection
            stats = orchestrator.run_streaming()

        logger.info(f"\nFinal statistics: {stats}")

    else:
        # Use legacy batch mode
        logger.info("Using LEGACY batch mode (not recommended for large datasets)")
        orchestrator = DataOrchestrator(config, date_list, env_path)
        graph_df = orchestrator.run_all()

        builder = GraphBuilder(client)
        stock_codes = graph_df["stock_code"].unique()

        logger.info(f"Building graph for {len(stock_codes)} stocks...")
        for stock_code in tqdm(stock_codes, desc="Building graph"):
            builder.build_graph(graph_df, stock_code, date_list)

    # Get final node count
    client.get_node_count()
    client.close()

    logger.info("Graph database build completed successfully!")


def cli():
    """CLI entry point."""
    args = parse_args()
    main(
        date_st=args.date_st,
        date_fn=args.date_fn,
        env_path=args.env,
        streaming=args.streaming,
        batch_size=args.batch_size,
        skip_existing=not args.no_skip_existing,
        update_only=args.update_only,
    )


if __name__ == "__main__":
    cli()
