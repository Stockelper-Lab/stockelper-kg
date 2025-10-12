"""Neo4j database client."""

import logging
from typing import List

from neo4j import GraphDatabase

from ..config import Neo4jConfig

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j database client for knowledge graph operations."""

    def __init__(self, config: Neo4jConfig):
        """Initialize Neo4j client.

        Args:
            config: Neo4j configuration
        """
        self.config = config
        self.driver = GraphDatabase.driver(
            config.uri, auth=(config.user, config.password)
        )
        logger.info(f"Connected to Neo4j at {config.uri}")

    def close(self):
        """Close database connection."""
        self.driver.close()
        logger.info("Neo4j connection closed")

    def ensure_constraints(self):
        """Create database constraints if they don't exist."""
        with self.driver.session() as session:
            session.execute_write(self._create_constraints)
        logger.info("Database constraints ensured")

    @staticmethod
    def _create_constraints(tx):
        """Create unique constraints on nodes.

        Args:
            tx: Neo4j transaction
        """
        tx.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) "
            "REQUIRE c.stock_code IS UNIQUE"
        )
        tx.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Stock) "
            "REQUIRE s.stock_code IS UNIQUE"
        )
        tx.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Date) " "REQUIRE d.date IS UNIQUE"
        )

    def execute_query(self, cypher_query: str):
        """Execute a single Cypher query.

        Args:
            cypher_query: Cypher query string
        """
        with self.driver.session() as session:
            session.execute_write(self._run_query, cypher_query)

    @staticmethod
    def _run_query(tx, query: str):
        """Run a Cypher query in transaction.

        Args:
            tx: Neo4j transaction
            query: Cypher query string
        """
        tx.run(query)

    def execute_queries(self, queries: List[str]):
        """Execute multiple Cypher queries in a single transaction.

        Args:
            queries: List of Cypher query strings
        """
        if not queries:
            return

        with self.driver.session() as session:
            session.execute_write(self._run_queries, queries)

    @staticmethod
    def _run_queries(tx, queries: List[str]):
        """Run multiple Cypher queries in transaction.

        Args:
            tx: Neo4j transaction
            queries: List of Cypher query strings
        """
        for query in queries:
            tx.run(query)

    def delete_all_data(self):
        """Delete all nodes and relationships from database."""
        with self.driver.session() as session:
            session.execute_write(self._delete_all)
        logger.warning("All data deleted from Neo4j database")

    @staticmethod
    def _delete_all(tx):
        """Delete all nodes and relationships.

        Args:
            tx: Neo4j transaction
        """
        tx.run("MATCH (n) DETACH DELETE n")

    def get_node_count(self) -> int:
        """Get total number of nodes in database.

        Returns:
            Total node count
        """
        query = "MATCH (n) RETURN count(n) AS total_node_count"
        with self.driver.session() as session:
            result = session.run(query)
            count = result.single()["total_node_count"]
            logger.info(f"Total nodes in database: {count}")
            return count

    def check_stock_exists(self, stock_code: str) -> bool:
        """Check if stock data already exists in database.

        Args:
            stock_code: Stock code to check

        Returns:
            True if stock exists, False otherwise
        """
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        RETURN count(c) > 0 AS exists
        """
        with self.driver.session() as session:
            result = session.run(query, stock_code=stock_code)
            return result.single()["exists"]

    def check_stock_date_exists(self, stock_code: str, date: str) -> bool:
        """Check if stock data for specific date already exists.

        Args:
            stock_code: Stock code to check
            date: Date in YYYYMMDD format

        Returns:
            True if data exists for this date, False otherwise
        """
        query = """
        MATCH (c:Company {stock_code: $stock_code})-[:HAS_STOCK_PRICE]->(sp:StockPrice)-[:RECORDED_ON]->(d:Date {date: $date})
        RETURN count(sp) > 0 AS exists
        """
        with self.driver.session() as session:
            result = session.run(query, stock_code=stock_code, date=date)
            return result.single()["exists"]

    def get_processed_stocks(self) -> set:
        """Get set of all stock codes that have been processed.

        Returns:
            Set of stock codes
        """
        query = "MATCH (c:Company) RETURN c.stock_code AS stock_code"
        with self.driver.session() as session:
            result = session.run(query)
            return {record["stock_code"] for record in result}

    def get_processed_dates_for_stock(self, stock_code: str) -> set:
        """Get set of dates that have been processed for a stock.

        Args:
            stock_code: Stock code to check

        Returns:
            Set of dates in YYYYMMDD format
        """
        query = """
        MATCH (c:Company {stock_code: $stock_code})-[:HAS_STOCK_PRICE]->(:StockPrice)-[:RECORDED_ON]->(d:Date)
        RETURN d.date AS date
        """
        with self.driver.session() as session:
            result = session.run(query, stock_code=stock_code)
            return {record["date"] for record in result}
