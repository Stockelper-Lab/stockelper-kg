import logging

from neo4j import GraphDatabase
from neo4j.exceptions import ClientError, DatabaseError

from ..config import Neo4jConfig
from .cypher import generate_constraints

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self, config: Neo4jConfig):
        self.driver = GraphDatabase.driver(
            config.uri, auth=(config.user, config.password)
        )
        logger.info(f"Connected to Neo4j at {config.uri}")

    def close(self):
        self.driver.close()
        logger.info("Neo4j connection closed")

    def ensure_constraints(self):
        constraints = generate_constraints()
        if not constraints:
            return

        with self.driver.session() as session:
            for statement in constraints.rstrip(";").split(";\n"):
                if not statement.strip():
                    continue
                try:
                    session.run(statement)
                except (ClientError, DatabaseError) as exc:
                    if exc.code == "Neo.ClientError.Schema.IndexAlreadyExists":
                        continue
                    if exc.code == "Neo.DatabaseError.Schema.ConstraintCreationFailed":
                        if "NODE KEY" in str(exc) or "Node Key" in str(exc):
                            continue
                    raise

    def execute_query(self, query: str):
        with self.driver.session() as session:
            session.execute_write(lambda tx: tx.run(query))

    def execute_query_with_params(self, query: str, parameters: dict | None = None):
        """Execute a Cypher query with parameters (write transaction)."""
        with self.driver.session() as session:
            params = parameters or {}
            session.execute_write(lambda tx: tx.run(query, **params))

    def execute_queries(self, queries: list[str]):
        if not queries:
            return
        with self.driver.session() as session:
            session.execute_write(lambda tx: [tx.run(q) for q in queries])

    def delete_all_data(self):
        with self.driver.session() as session:
            session.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))
        logger.warning("All data deleted from Neo4j database")

    def get_node_count(self) -> int:
        with self.driver.session() as session:
            count = session.run(
                "MATCH (n) RETURN count(n) AS total_node_count"
            ).single()["total_node_count"]
            logger.info(f"Total nodes in database: {count}")
            return count

    def check_stock_exists(self, stock_code: str) -> bool:
        with self.driver.session() as session:
            return session.run(
                "MATCH (c:Company {stock_code: $stock_code}) RETURN count(c) > 0 AS exists",
                stock_code=stock_code,
            ).single()["exists"]

    def check_stock_date_exists(self, stock_code: str, date: str) -> bool:
        with self.driver.session() as session:
            return session.run(
                "MATCH (c:Company {stock_code: $stock_code})-[:HAS_STOCK_PRICE]->(sp:StockPrice)-[:RECORDED_ON]->(d:Date {date: $date}) RETURN count(sp) > 0 AS exists",
                stock_code=stock_code,
                date=date,
            ).single()["exists"]

    def get_processed_stocks(self) -> set:
        with self.driver.session() as session:
            return {
                r["stock_code"]
                for r in session.run(
                    "MATCH (c:Company) RETURN c.stock_code AS stock_code"
                )
            }

    def get_processed_dates_for_stock(self, stock_code: str) -> set:
        with self.driver.session() as session:
            return {
                r["date"]
                for r in session.run(
                    "MATCH (c:Company {stock_code: $stock_code})-[:HAS_STOCK_PRICE]->(:StockPrice)-[:RECORDED_ON]->(d:Date) RETURN d.date AS date",
                    stock_code=stock_code,
                )
            }
