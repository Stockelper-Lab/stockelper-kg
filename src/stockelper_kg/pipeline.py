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
from .graph.event import classify_events
from .graph.ontology import ONTOLOGY
from .graph.payload import (
    build_graph_payload,
    _autofill_counterparty,
    _identity_keys_for,
    _normalize_corp_names,
)
from .graph.schema import _has_value
from .utils.dates import normalize_date

logger = logging.getLogger(__name__)


@dataclass
class EventResult:
    event_data: dict[str, Any]
    corp_names: list[str]
    stock_codes: dict[str, str]
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
        batch_mode: bool = True,
    ) -> list[dict[str, Any]]:
        results = self._analyze(event_text, metadata)
        if not results:
            logger.warning("No events extracted from text")
            return []

        shared_doc_node = self._create_shared_doc_node(metadata, results)

        if batch_mode and len(results) > 1:
            self._save_events_batch(results, metadata, shared_doc_node)
        else:
            for result in results:
                self._save_event(result.event_data, metadata, shared_doc_node)

        self._save_companies(results)

        return [result.event_data for result in results]

    def _create_collector(self, config: Config) -> EventCollector:
        return EventCollector(
            dart=DartCollector(config.dart_api_key, config.sleep_seconds),
            kis=KISCollector(
                config.kis, config.sleep_seconds, getattr(config, "env_path", ".env")
            ),
            krx=KRXCollector(config.sleep_seconds),
            competitors=MongoDBCollector(config.mongodb),
        )

    def _analyze(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> list[EventResult]:
        logger.info("Analyzing event...")
        events = classify_events(text)
        results: list[EventResult] = []

        for event_data in events:
            result = self._process_single_event(event_data, metadata)
            results.append(result)

        return results

    def _process_single_event(
        self, event_data: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> EventResult:
        slots = event_data.get("required_slots")
        if not isinstance(slots, dict):
            slots = {}
            event_data["required_slots"] = slots
        if not isinstance(event_data.get("optional_slots"), dict):
            event_data["optional_slots"] = {}

        corp_names = _normalize_corp_names(
            event_data.get("corp_names")
            if isinstance(event_data.get("corp_names"), list)
            else []
        )
        if not corp_names and metadata:
            meta = metadata.get("corp_names")
            if isinstance(meta, list):
                corp_names = [str(n).strip() for n in meta if str(n).strip()]

        if not corp_names:
            raise ValueError("corp_names is required")

        event_data["corp_names"] = slots["corp_names"] = corp_names

        date = slots.get("date") or event_data.get("date")
        if date and (normalized := normalize_date(date)):
            slots["date"] = event_data["date"] = normalized

        raw_codes = slots.get("stock_codes")
        raw_codes = raw_codes if isinstance(raw_codes, dict) else {}
        stock_codes: dict[str, str] = {}
        for corp_name in corp_names:
            code = (
                raw_codes.get(corp_name)
                or slots.get("stock_code")
                or self.collector.resolve(corp_name)
            )
            if code:
                stock_codes[corp_name] = code

        if stock_codes:
            slots.setdefault("stock_codes", {}).update(stock_codes)
            if len(stock_codes) == 1:
                slots["stock_code"] = next(iter(stock_codes.values()))

        definition = ONTOLOGY.event_map.get(event_data.get("event_type"))
        if not definition:
            raise ValueError(f"Unknown event_type: {event_data.get('event_type')}")

        _autofill_counterparty(definition, slots, corp_names)

        missing = [
            slot
            for slot in definition.required_slots
            if not _has_value(slots.get(slot))
        ]
        if missing:
            missing_str = ", ".join(missing)
            context = (
                f"event_type={event_data.get('event_type')}, "
                f"corp_names={', '.join(corp_names) if corp_names else 'UNKNOWN'}"
            )
            if summary_snippet := (event_data.get("summary") or "").strip():
                context = f"{context}, summary={summary_snippet[:120]}"
            raise ValueError(f"Missing required slots: {missing_str} ({context})")

        return EventResult(
            event_data=event_data,
            corp_names=corp_names,
            stock_codes=stock_codes,
            date=slots.get("date"),
        )

    def _save_events_batch(
        self,
        results: list[EventResult],
        metadata: dict[str, Any] | None,
        shared_doc_node=None,
    ) -> None:
        from .graph.payload import build_multi_event_payload

        events_data = [r.event_data for r in results]
        first_names: list[str] = []
        for result in results[:3]:
            corp_names = result.event_data.get("corp_names")
            if isinstance(corp_names, list) and corp_names:
                first_names.append(corp_names[0])
        corp_label = ", ".join(first_names)
        if len(results) > 3:
            corp_label += f" ... (+{len(results) - 3} more)"

        logger.info(f"[{corp_label}] Saving {len(results)} event(s) in batch...")
        payload = build_multi_event_payload(events_data, metadata=metadata)
        self.client.execute_query(payload_to_cypher(payload))

    def _save_event(
        self,
        event_data: dict[str, Any],
        metadata: dict[str, Any] | None,
        shared_doc_node=None,
    ) -> None:
        corp_names = event_data.get("corp_names")
        corp_label = (
            ", ".join(c for c in corp_names if c)
            if isinstance(corp_names, list)
            else "UNKNOWN"
        )
        logger.info(f"[{corp_label}] Saving event graph...")
        payload = build_graph_payload(
            event_data, metadata=metadata, shared_doc_node=shared_doc_node
        )
        self.client.execute_query(payload_to_cypher(payload))

    def _create_shared_doc_node(
        self,
        metadata: dict[str, Any] | None,
        results: list[EventResult],
    ):
        from .graph.payload import extract_document_info
        from .graph.schema import GraphBuildContext

        doc_info = extract_document_info(metadata)
        if not doc_info and results and results[0].event_data:
            doc_info = extract_document_info(metadata, results[0].event_data)
        if not doc_info:
            return None
        context = GraphBuildContext()
        return context.add_node("Document", doc_info, _identity_keys_for("Document"))

    def _save_companies(self, results: list[EventResult]) -> None:
        unique_companies = {}
        for result in results:
            if not result.date:
                continue
            for corp_name, stock_code in result.stock_codes.items():
                unique_companies.setdefault(stock_code, (result.date, corp_name))

        for stock_code, (date, corp_name) in unique_companies.items():
            self._save_company(stock_code, date, corp_name)

    def _save_company(
        self, stock_code: str, date: str, corp_name: str | None = None
    ) -> None:
        label = corp_name or stock_code
        logger.info(f"[{label}] Collecting company data...")
        try:
            df = self.collector.collect(stock_code, date)
            if df.empty:
                logger.warning(f"[{label}] No data collected")
                return

            self.graph_builder.build_graph(df, stock_code, [date])
            logger.info(f"[{label}] Graph updated")
        except Exception as e:
            logger.error(f"[{label}] Failed to update company graph: {e}")


def create_pipeline(config: Config) -> EventPipeline:
    return EventPipeline(config, Neo4jClient(config.neo4j))
