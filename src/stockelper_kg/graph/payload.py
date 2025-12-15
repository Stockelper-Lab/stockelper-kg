from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from ..utils.dates import build_date_properties, normalize_date
from .ontology import ONTOLOGY, EventDefinition
from .schema import (
    GraphBuildContext,
    GraphNodeSpec,
    GraphPayload,
    _has_value,
    clean_props,
)

_EVENT_DEFINITIONS = ONTOLOGY.event_map
_NODE_IDENTITIES = {
    label: defs.primary_keys[0]
    for label, defs in ONTOLOGY.node_map.items()
    if defs.primary_keys
}


def build_multi_event_payload(
    events_data: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> GraphPayload:
    if not events_data:
        raise ValueError("events_data cannot be empty")

    context = GraphBuildContext()
    doc_info = extract_document_info(metadata, events_data[0])
    shared_doc_node = (
        context.add_node("Document", doc_info, _identity_keys_for("Document"))
        if doc_info
        else None
    )

    for idx, event_data in enumerate(events_data, start=1):
        try:
            event_payload = build_graph_payload(
                event_data, metadata=None, shared_doc_node=shared_doc_node
            )
        except Exception as exc:
            event_type = event_data.get("event_type", "UNKNOWN")
            corp = event_data.get("corp_names") or event_data.get("corp_name")
            label = corp if isinstance(corp, str) else ", ".join(corp or [])
            raise ValueError(
                f"Failed to build payload for event #{idx} ({event_type} | {label}): {exc}"
            ) from exc
        for node in event_payload.nodes:
            context.add_node(
                node.label,
                node.properties,
                node.identity_keys or _identity_keys_for(node.label),
            )
        for edge in event_payload.edges:
            context.add_edge(edge.type, edge.source, edge.target)

    return context.to_payload()


def build_graph_payload(
    event_data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    shared_doc_node: GraphNodeSpec | None = None,
) -> GraphPayload:
    event_type = event_data.get("event_type")
    if not event_type:
        raise ValueError("event_type is required")
    definition = _EVENT_DEFINITIONS.get(event_type)
    if not definition:
        raise ValueError(f"Unknown event_type: {event_type}")

    slots: dict[str, Any] = {}
    for key in ("required_slots", "optional_slots"):
        data = event_data.get(key)
        if isinstance(data, dict):
            slots.update(data)

    sentiment_score = event_data.get("sentiment_score")
    if sentiment_score is not None:
        slots["sentiment_score"] = sentiment_score

    corp_names = _normalize_corp_names(event_data, slots)
    if not corp_names:
        raise ValueError("corp_name is required")
    slots["corp_names"] = corp_names
    slots["corp_name"] = corp_names[0]
    event_data["corp_names"] = corp_names
    event_data["corp_name"] = corp_names[0]

    # TODO: Behavior Change - auto-fill counterparty from corp_names when missing
    _autofill_counterparty(definition, slots, corp_names)

    missing = [s for s in definition.required_slots if not _has_value(slots.get(s))]
    if missing:
        missing_str = ", ".join(missing)
        corp_label = ", ".join(corp_names) if corp_names else "UNKNOWN"
        summary_snippet = (event_data.get("summary") or "").strip()
        context = f"event_type={event_type}, corp_names={corp_label}"
        if summary_snippet:
            context = f"{context}, summary={summary_snippet[:120]}"
        raise ValueError(f"Missing required slots: {missing_str} ({context})")

    if date := slots.get("date") or event_data.get("date"):
        if resolved_date := normalize_date(date):
            slots["date"] = resolved_date

    doc_info = extract_document_info(metadata, event_data) or (
        shared_doc_node.properties if shared_doc_node else None
    )
    slots["event_id"] = _generate_event_id(
        corp_names,
        event_type,
        slots.get("date"),
        event_data.get("summary", ""),
        doc_info,
        slots,
    )

    return _build_event_graph(
        corp_names,
        event_type,
        slots,
        event_data.get("summary", ""),
        doc_info,
        shared_doc_node,
    )


def build_stock_snapshot_payload(
    company: dict[str, Any],
    date: str,
    stock_price: dict[str, Any],
    financials: dict[str, Any] | None = None,
    indicators: dict[str, Any] | None = None,
) -> GraphPayload:
    context = GraphBuildContext()
    company_node = context.add_node("Company", company, _identity_keys_for("Company"))

    price_props = _normalize_stock_price({"traded_at": date, **stock_price})
    stock_node = context.add_node(
        "StockPrice", price_props, _identity_keys_for("StockPrice")
    )
    context.add_edge("HAS_STOCK_PRICE", company_node.key, stock_node.key)

    if price_date := _attach_typed_date_node(
        context, "PriceDate", date, company_node=company_node
    ):
        context.add_edge("RECORDED_ON", stock_node.key, price_date.key)

    if financials:
        fs_date_value = (
            financials.get("reported_date") or financials.get("date") or date
        )
        fs_props = {**financials, "date": fs_date_value}
        fs_node = context.add_node(
            "FinancialStatements", fs_props, _identity_keys_for("FinancialStatements")
        )
        context.add_edge("HAS_FINANCIAL_STATEMENTS", company_node.key, fs_node.key)
        if fs_date := _attach_typed_date_node(
            context, "FinancialDate", fs_date_value, company_node=company_node
        ):
            context.add_edge("REPORTED_ON", fs_node.key, fs_date.key)

    if indicators:
        indicator_date = indicators.get("as_of") or indicators.get("date") or date
        indicator_props = {**indicators, "date": indicator_date}
        indicator_node = context.add_node(
            "Indicator", indicator_props, _identity_keys_for("Indicator")
        )
        context.add_edge("HAS_INDICATOR", company_node.key, indicator_node.key)
        if ind_date := _attach_typed_date_node(
            context, "IndicatorDate", indicator_date, company_node=company_node
        ):
            context.add_edge("MEASURED_ON", indicator_node.key, ind_date.key)

    return context.to_payload()


def build_competitor_payload(
    source_company: dict[str, Any],
    target_company: dict[str, Any],
) -> GraphPayload:
    context = GraphBuildContext()
    source_node = context.add_node(
        "Company", source_company, _identity_keys_for("Company")
    )
    target_node = context.add_node(
        "Company", target_company, _identity_keys_for("Company")
    )
    context.add_edge("IS_COMPETITOR", source_node.key, target_node.key)
    context.add_edge("IS_COMPETITOR", target_node.key, source_node.key)
    return context.to_payload()


def extract_document_info(
    metadata: dict[str, Any] | None,
    event_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Extract document information from metadata or event data.

    Args:
        metadata: Metadata dictionary
        event_data: Optional event data dictionary

    Returns:
        Document info dictionary or None
    """
    candidates = [
        src
        for src in (
            metadata,
            metadata.get("document") if metadata else None,
            event_data.get("document") if event_data else None,
            event_data.get("metadata") if event_data else None,
        )
        if isinstance(src, dict)
    ]
    merged = {
        key: value
        for source in candidates
        for key, value in source.items()
        if value not in (None, "", [])
    }
    if not merged:
        return None

    cleaned = clean_props(merged)
    if not cleaned:
        return None

    if "document_id" not in cleaned:
        for key in ("rcept_no", "url", "title"):
            value = cleaned.get(key)
            if _has_value(value) and isinstance(value, str) and value.strip():
                cleaned["document_id"] = value.strip()
                break
    return cleaned


def _generate_event_id(
    corp_names: list[str],
    event_type: str | None,
    date: str | None,
    summary: str | None,
    doc_info: dict[str, Any] | None,
    slots: dict[str, Any] | None,
) -> str:
    participants = ",".join(sorted(set(corp_names))) if corp_names else None
    required_slot_fp = ""
    resolved_date = date
    if isinstance(slots, dict):
        definition = ONTOLOGY.event_map.get(event_type or "")
        required_keys = definition.required_slots if definition else ()
        required_values = {
            key: slots.get(key) for key in required_keys if _has_value(slots.get(key))
        }
        if required_values:
            required_slot_fp = _fingerprint(required_values)
            resolved_date = required_values.get("date") or resolved_date

    parts = [
        part
        for part in (
            event_type or "",
            participants or "",
            resolved_date or "",
            required_slot_fp,
        )
        if part
    ]
    if not parts:
        parts = [f"EVT_{uuid.uuid4().hex[:12].upper()}"]
    content = "::".join(parts)
    digest = hashlib.sha1(content.encode()).hexdigest()
    return f"EVT_{digest[:12].upper()}"


def _build_event_graph(
    corp_names: list[str],
    event_type: str,
    slots: dict[str, Any],
    summary: str,
    doc_info: dict[str, Any] | None,
    shared_doc_node: GraphNodeSpec | None = None,
) -> GraphPayload:
    context = GraphBuildContext()

    date_str = slots.get("date")
    stock_codes = slots.get("stock_codes")
    corp_codes = slots.get("corp_codes")

    event_props = {
        **{
            k: v
            for k, v in slots.items()
            if k not in ("date", "stock_codes", "corp_codes")
        },
        "type": event_type,
        "summary": summary.strip() if summary else "",
    }
    event_node = context.add_node("Event", event_props, _identity_keys_for("Event"))

    for idx, corp_name in enumerate(corp_names):
        company_node = context.add_node(
            "Company",
            {
                "corp_name": corp_name,
                "stock_nm": corp_name,
                "corp_code": _resolve_company_value(
                    corp_codes, slots.get("corp_code"), corp_name, idx, corp_names
                ),
                "stock_code": _resolve_company_value(
                    stock_codes, slots.get("stock_code"), corp_name, idx, corp_names
                ),
            },
            _identity_keys_for("Company"),
        )
        context.add_edge("INVOLVED_IN", company_node.key, event_node.key)

        if date_str:
            event_date = _attach_typed_date_node(
                context, "EventDate", date_str, company_node=company_node
            )
            if event_date:
                context.add_edge("OCCURRED_ON", event_node.key, event_date.key)

    doc_node = shared_doc_node
    if not doc_node and doc_info:
        doc_node = context.add_node(
            "Document", doc_info, _identity_keys_for("Document")
        )
    if doc_node:
        context.nodes[doc_node.key] = doc_node
        context.add_edge("REPORTED_BY", event_node.key, doc_node.key)

    return context.to_payload()


def _normalize_stock_price(props: dict[str, Any]) -> dict[str, Any]:
    props.setdefault("stck_prpr", props.get("stck_clpr"))
    props.setdefault("stck_clpr", props.get("stck_prpr"))
    return props


def _normalize_corp_names(
    event_data: dict[str, Any],
    slots: dict[str, Any],
) -> list[str]:
    names: list[str] = []
    for source in (
        event_data.get("corp_names"),
        slots.get("corp_names"),
        event_data.get("corp_name"),
        slots.get("corp_name"),
    ):
        if isinstance(source, list):
            names.extend(source)
        elif isinstance(source, str):
            names.append(source)
    return [
        name
        for name in dict.fromkeys(
            name.strip() for name in names if isinstance(name, str)
        )
        if name
    ]


def _autofill_counterparty(
    definition: EventDefinition, slots: dict[str, Any], corp_names: list[str]
) -> None:
    if "counterparty" not in definition.required_slots:
        return
    if _has_value(slots.get("counterparty")):
        return
    if len(corp_names) < 2:
        return

    counterparts = [name for name in corp_names[1:] if name]
    if not counterparts:
        return
    slots["counterparty"] = counterparts if len(counterparts) > 1 else counterparts[0]


def _attach_typed_date_node(
    context: GraphBuildContext,
    label: str,
    date_value: Any,
    company_node: GraphNodeSpec | None = None,
) -> GraphNodeSpec | None:
    date_props = build_date_properties(date_value)
    if not date_props:
        return None

    hub_date = context.add_node("Date", date_props, _identity_keys_for("Date"))
    if company_node:
        context.add_edge("ON_DATE", company_node.key, hub_date.key)

    typed_date = context.add_node(label, date_props, _identity_keys_for(label))
    context.add_edge("IS_DATE", typed_date.key, hub_date.key)
    return typed_date


def _resolve_company_value(
    mapping: Any,
    shared_value: Any,
    corp_name: str,
    position: int | None = None,
    corp_names: list[str] | None = None,
) -> Any:
    if isinstance(mapping, dict) and corp_name in mapping:
        return mapping.get(corp_name)
    if isinstance(mapping, (list, tuple)) and position is not None:
        return mapping[position] if position < len(mapping) else None
    if isinstance(mapping, (list, tuple)) and corp_names:
        try:
            idx = corp_names.index(corp_name)
        except ValueError:
            idx = None
        return mapping[idx] if idx is not None and idx < len(mapping) else None
    return shared_value


def _identity_keys_for(label: str) -> tuple[str, ...]:
    return _NODE_IDENTITIES.get(label, ())


def _fingerprint(value: Any) -> str:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        payload = str(value)
    return hashlib.sha1(payload.encode()).hexdigest()[:12]
