from __future__ import annotations

import hashlib
import uuid
from typing import Any

from ..utils.dates import build_date_properties, normalize_date
from .ontology import ONTOLOGY
from .schema import GraphBuildContext, GraphPayload, clean_props

_EVENT_DEFINITIONS = ONTOLOGY.event_map


def _has_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, (list, tuple, set, dict)):
        return bool(val)
    return True


def build_graph_payload(
    event_data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> GraphPayload:
    event_type = event_data.get("event_type")
    if not event_type:
        raise ValueError("event_type is required")
    definition = _EVENT_DEFINITIONS.get(event_type)
    if not definition:
        raise ValueError(f"Unknown event_type: {event_type}")

    slots = {}
    for key in ("required_slots", "optional_slots"):
        if isinstance(event_data.get(key), dict):
            slots.update(event_data[key])

    missing = [s for s in definition.required_slots if not _has_value(slots.get(s))]
    if missing:
        raise ValueError(f"Missing required slots: {', '.join(missing)}")

    corp_name = (event_data.get("corp_name") or slots.get("corp_name") or "").strip()
    if not corp_name:
        raise ValueError("corp_name is required")
    slots["corp_name"] = corp_name

    date = slots.get("date") or event_data.get("date")
    if date:
        from ..utils.dates import normalize_date

        resolved_date = normalize_date(date)
        if resolved_date:
            slots["date"] = resolved_date

    doc_info = _extract_document_info(metadata, event_data)
    slots["event_id"] = _generate_event_id(
        corp_name,
        event_type,
        slots.get("date"),
        event_data.get("summary", ""),
        doc_info,
    )

    return _build_event_graph(
        corp_name, event_type, slots, event_data.get("summary", ""), doc_info
    )


def build_stock_snapshot_payload(
    company: dict[str, Any],
    date: str,
    stock_price: dict[str, Any],
    financials: dict[str, Any] | None = None,
    indicators: dict[str, Any] | None = None,
) -> GraphPayload:
    context = GraphBuildContext()
    company_node = context.add_node("Company", company)

    price_props = _normalize_stock_price({"traded_at": date, **stock_price})
    stock_node = context.add_node("StockPrice", price_props)
    context.add_edge("HAS_STOCK_PRICE", company_node.key, stock_node.key)

    date_props = build_date_properties(date)
    if date_props:
        date_node = context.add_node("Date", date_props)
        context.add_edge("RECORDED_ON", stock_node.key, date_node.key)

    if financials:
        fs_node = context.add_node("FinancialStatements", financials)
        context.add_edge("HAS_FINANCIAL_STATEMENTS", company_node.key, fs_node.key)

    if indicators:
        indicator_node = context.add_node("Indicator", indicators)
        context.add_edge("HAS_INDICATOR", company_node.key, indicator_node.key)

    return context.to_payload()


def build_competitor_payload(
    source_company: dict[str, Any],
    target_company: dict[str, Any],
) -> GraphPayload:
    context = GraphBuildContext()
    source_node = context.add_node("Company", source_company)
    target_node = context.add_node("Company", target_company)
    context.add_edge("IS_COMPETITOR", source_node.key, target_node.key)
    context.add_edge("IS_COMPETITOR", target_node.key, source_node.key)
    return context.to_payload()


def _extract_document_info(
    metadata: dict[str, Any] | None,
    event_data: dict[str, Any],
) -> dict[str, Any] | None:
    sources: list[dict[str, Any]] = []
    if metadata:
        sources.append(metadata)
        if isinstance(metadata.get("document"), dict):
            sources.append(metadata["document"])
    for key in ("document", "metadata"):
        if isinstance(event_data.get(key), dict):
            sources.append(event_data[key])

    merged: dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if value not in (None, "", []):
                merged[key] = value

    if not merged:
        return None

    cleaned = clean_props(merged)
    if not cleaned:
        return None

    if "document_id" not in cleaned:
        for key in ("rcept_no", "url", "title"):
            if cleaned.get(key):
                cleaned["document_id"] = cleaned[key]
                break

    return cleaned


def _generate_event_id(
    corp_name: str | None,
    event_type: str | None,
    date: str | None,
    summary: str | None,
    doc_info: dict[str, Any] | None,
) -> str:
    if doc_info and doc_info.get("document_id"):
        content = f"{doc_info['document_id']}::{event_type or ''}"
    else:
        parts = [p for p in (corp_name, event_type, date, summary) if p]
        if not parts:
            return f"EVT_{uuid.uuid4().hex[:12].upper()}"
        content = "::".join(parts)
    digest = hashlib.sha1(content.encode()).hexdigest()
    return f"EVT_{digest[:12].upper()}"


def _build_event_graph(
    corp_name: str,
    event_type: str,
    slots: dict[str, Any],
    summary: str,
    doc_info: dict[str, Any] | None,
) -> GraphPayload:
    context = GraphBuildContext()

    company_node = context.add_node(
        "Company",
        {
            "corp_name": corp_name,
            "stock_nm": corp_name,
            "corp_code": slots.get("corp_code"),
            "stock_code": slots.get("stock_code"),
        },
    )

    event_props = {k: v for k, v in slots.items() if k != "date"}
    event_props["type"] = event_type
    event_props["summary"] = summary.strip() if summary else ""
    event_node = context.add_node("Event", event_props)
    context.add_edge("INVOLVED_IN", company_node.key, event_node.key)

    if date_str := slots.get("date"):
        date_props = build_date_properties(date_str)
        if date_props:
            date_node = context.add_node("Date", date_props)
            context.add_edge("OCCURRED_ON", event_node.key, date_node.key)

    if doc_info:
        doc_node = context.add_node("Document", doc_info)
        context.add_edge("REPORTED_BY", event_node.key, doc_node.key)

    return context.to_payload()


def _normalize_stock_price(props: dict[str, Any]) -> dict[str, Any]:
    props.setdefault("stck_prpr", props.get("stck_clpr"))
    props.setdefault("stck_clpr", props.get("stck_prpr"))
    return props
