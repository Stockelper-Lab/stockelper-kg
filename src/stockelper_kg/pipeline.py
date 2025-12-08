from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .collectors.dart import DartCollector
from .collectors.event import EventCollector
from .collectors.kis import KISCollector
from .collectors.krx import KRXCollector
from .collectors.mongodb import MongoDBCollector
from .config import Config
from .graph import GraphBuilder, Neo4jClient
from .graph.cypher import payload_to_cypher
from .graph.event import classify_event
from .graph.payload import build_graph_payload
from .utils.dates import normalize_date

logger = logging.getLogger(__name__)


@dataclass
class EventResult:
    event_data: dict[str, Any]
    stock_code: str | None = None
    date: str | None = None


class EventPipeline:
    def __init__(
        self,
        config: Config,
        neo4j_client: Neo4jClient,
        collector: EventCollector | None = None,
    ):
        self.client = neo4j_client
        self.graph_builder = GraphBuilder(neo4j_client)
        self.collector = collector or self._create_collector(config)

    def process(
        self,
        event_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self._analyze(event_text)
        self._save_event(result.event_data, metadata)

        if result.stock_code and result.date:
            self._save_company(result.stock_code, result.date)

        return result.event_data

    def _create_collector(self, config: Config) -> EventCollector:
        return EventCollector(
            dart=DartCollector(config.dart_api_key, config.sleep_seconds),
            kis=KISCollector(
                config.kis, config.sleep_seconds, getattr(config, "env_path", ".env")
            ),
            krx=KRXCollector(config.sleep_seconds),
            competitors=MongoDBCollector(config.mongodb),
        )

    def _analyze(self, text: str) -> EventResult:
        logger.info("Analyzing event...")
        event_data = classify_event(text)

        slots = event_data.get("required_slots", {})
        if not isinstance(slots, dict):
            slots = {}
            event_data["required_slots"] = slots

        corp_name = event_data.get("corp_name", "").strip()
        if not corp_name:
            raise ValueError("corp_name is required")
        slots["corp_name"] = corp_name

        raw_date = slots.get("date") or event_data.get("date")
        if raw_date:
            canonical_date = normalize_date(raw_date)
            if canonical_date:
                slots["date"] = canonical_date
                event_data["date"] = canonical_date

        stock_code = slots.get("stock_code")
        if not stock_code:
            stock_code = self.collector.resolve(corp_name)
        if stock_code:
            slots["stock_code"] = stock_code

        return EventResult(
            event_data=event_data,
            stock_code=stock_code,
            date=slots.get("date"),
        )

    def _save_event(
        self,
        event_data: dict[str, Any],
        metadata: dict[str, Any] | None,
    ) -> None:
        slots = event_data.get("required_slots", {})
        if not isinstance(slots, dict):
            slots = {}
            event_data["required_slots"] = slots

        corp_name = event_data.get("corp_name", "").strip()
        if not corp_name and metadata:
            corp_name = (metadata.get("corp_name") or "").strip()
        if not corp_name:
            raise ValueError("corp_name is required")
        slots["corp_name"] = corp_name

        logger.info("[%s] Saving event graph...", corp_name)
        payload = build_graph_payload(event_data, metadata=metadata)
        cypher = payload_to_cypher(payload)
        self.client.execute_query(cypher)

    def _save_company(self, stock_code: str, date: str) -> None:
        logger.info("[%s] Collecting company data...", stock_code)
        try:
            df = self.collector.collect(stock_code, date)
            if df.empty:
                logger.warning("[%s] No data collected", stock_code)
                return

            self.graph_builder.build_graph(df, stock_code, [date])
            logger.info("[%s] Graph updated", stock_code)
        except Exception as e:
            logger.error("[%s] Failed to update company graph: %s", stock_code, e)


def create_pipeline(config: Config) -> EventPipeline:
    return EventPipeline(config, Neo4jClient(config.neo4j))
