"""Graph database builder."""

import logging
from typing import List

import pandas as pd

from .client import Neo4jClient
from .queries import create_competitor_query, create_stock_query

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds knowledge graph from collected data."""

    def __init__(self, client: Neo4jClient):
        """Initialize graph builder.

        Args:
            client: Neo4j client instance
        """
        self.client = client

    def build_stock_data(
        self, graph_df: pd.DataFrame, stock_code: str, dates: List[str]
    ) -> List[str]:
        """Build Cypher queries for stock data.

        Args:
            graph_df: DataFrame with all collected data
            stock_code: Stock code to build data for
            dates: List of dates to build data for

        Returns:
            List of Cypher queries
        """
        queries = []
        filter_df = graph_df[graph_df["stock_code"] == stock_code]

        if filter_df.empty:
            logger.warning(f"No data found for stock_code: {stock_code}")
            return queries

        company_dict = filter_df.iloc[0].to_dict()

        for date in dates:
            try:
                date_df = filter_df[filter_df["date"] == date]
                if date_df.empty:
                    logger.warning(
                        f"No data for {company_dict.get('stock_nm', stock_code)} "
                        f"({stock_code}) on date {date}"
                    )
                    continue

                stock_price_dict = date_df.iloc[0].to_dict()
                query = create_stock_query(date, company_dict, stock_price_dict)
                queries.append(query)
            except Exception as e:
                logger.error(
                    f"Error creating stock query for {stock_code} on {date}: {e}"
                )

        return queries

    def build_competitor_data(
        self, graph_df: pd.DataFrame, stock_code: str
    ) -> List[str]:
        """Build Cypher queries for competitor relationships.

        Args:
            graph_df: DataFrame with all collected data
            stock_code: Stock code to build competitor data for

        Returns:
            List of Cypher queries
        """
        queries = []

        try:
            src_df = graph_df[graph_df["stock_code"] == stock_code]
            if src_df.empty:
                return queries

            src_company_dict = src_df.iloc[0].to_dict()
            compete_code_list = src_df["compete_code_li"].values[0]

            if not compete_code_list:
                return queries

            for compete_stock_code in compete_code_list:
                # Skip self-reference
                if stock_code == compete_stock_code:
                    continue

                dst_df = graph_df[graph_df["stock_code"] == compete_stock_code]
                if dst_df.empty:
                    logger.warning(
                        f"Competitor {compete_stock_code} not found in data"
                    )
                    continue

                dst_company_dict = dst_df.iloc[0].to_dict()
                query = create_competitor_query(src_company_dict, dst_company_dict)
                queries.append(query)

        except Exception as e:
            logger.error(f"Error creating competitor queries for {stock_code}: {e}")

        return queries

    def build_graph(self, graph_df: pd.DataFrame, stock_code: str, dates: List[str]):
        """Build complete graph for a stock.

        Args:
            graph_df: DataFrame with all collected data
            stock_code: Stock code to build graph for
            dates: List of dates to build data for
        """
        try:
            queries = []

            # Build stock data queries
            stock_queries = self.build_stock_data(graph_df, stock_code, dates)
            queries.extend(stock_queries)

            # Build competitor queries
            competitor_queries = self.build_competitor_data(graph_df, stock_code)
            queries.extend(competitor_queries)

            # Execute all queries in single transaction
            if queries:
                self.client.execute_queries(queries)

        except Exception as e:
            logger.error(f"Error building graph for {stock_code}: {e}")
