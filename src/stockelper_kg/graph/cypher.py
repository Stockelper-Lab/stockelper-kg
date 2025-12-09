from __future__ import annotations

from typing import Any

from .ontology import ONTOLOGY
from .schema import GraphNodeSpec, GraphPayload


def payload_to_cypher(payload: GraphPayload) -> str:
    alias_map = {node.key: f"n{idx}" for idx, node in enumerate(payload.nodes)}
    statements = []

    for node in payload.nodes:
        alias = alias_map[node.key]
        identity_keys = _get_identity_keys(node.label, node.properties)
        identity_props = {k: node.properties[k] for k in identity_keys if k in node.properties} or dict(node.properties)
        merge_props = ", ".join(f"{k}: {_format_value(v)}" for k, v in sorted(identity_props.items()))
        statements.append(f"MERGE ({alias}:{node.label} {{{merge_props}}})")

        remaining = {k: v for k, v in node.properties.items() if k not in identity_props}
        if remaining:
            set_props = ", ".join(f"{k}: {_format_value(v)}" for k, v in sorted(remaining.items()))
            statements.append(f"SET {alias} += {{{set_props}}}")

    for edge in payload.edges:
        src = alias_map.get(edge.source)
        tgt = alias_map.get(edge.target)
        if not src or not tgt:
            raise ValueError(
                f"Edge {edge.type} references unknown node: {edge.source} -> {edge.target}"
            )
        statements.append(f"MERGE ({src})-[:{edge.type}]->({tgt})")

    return "\n".join(statements)


def _get_identity_keys(label: str, props: dict[str, Any]) -> tuple[str, ...]:
    definition = ONTOLOGY.node_map.get(label)
    if definition and definition.primary_keys:
        for key_tuple in definition.primary_keys:
            if all(_has_value(props.get(k)) for k in key_tuple):
                return key_tuple
    return ()


def _has_value(val: Any) -> bool:
    return bool(val.strip()) if isinstance(val, str) else val is not None


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return f"[{', '.join(_format_value(v) for v in value)}]"
    if isinstance(value, dict):
        inner = ", ".join(f"{k}: {_format_value(v)}" for k, v in value.items())
        return f"{{{inner}}}"
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def generate_constraints() -> str:
    statements = []
    for label, definition in ONTOLOGY.node_map.items():
        if not definition.primary_keys:
            continue
        primary = definition.primary_keys[0]
        if len(primary) == 1:
            statements.append(
                f"CREATE CONSTRAINT {label.lower()}_{primary[0]} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{primary[0]} IS UNIQUE"
            )
        else:
            for prop in primary:
                statements.append(
                    f"CREATE INDEX {label.lower()}_{prop}_idx IF NOT EXISTS "
                    f"FOR (n:{label}) ON (n.{prop})"
                )
    return ";\n".join(statements) + ";" if statements else ""
