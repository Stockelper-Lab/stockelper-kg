from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class GraphNodeSpec:
    label: str
    key: str
    properties: Dict[str, Any]
    identity_keys: Tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphEdgeSpec:
    type: str
    source: str
    target: str


@dataclass(frozen=True)
class GraphPayload:
    nodes: Tuple[GraphNodeSpec, ...]
    edges: Tuple[GraphEdgeSpec, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphPayload:
        nodes = tuple(GraphNodeSpec(**n) for n in data.get("nodes", []))
        edges = tuple(GraphEdgeSpec(**e) for e in data.get("edges", []))
        if not nodes:
            raise ValueError("GraphPayload requires at least one node")
        return cls(nodes=nodes, edges=edges)


@dataclass
class GraphBuildContext:
    nodes: Dict[str, GraphNodeSpec] = field(default_factory=dict)
    edges: list[GraphEdgeSpec] = field(default_factory=list)

    def add_node(
        self,
        label: str,
        properties: Dict[str, Any],
        identity_keys: Tuple[str, ...] = (),
    ) -> GraphNodeSpec:
        props = clean_props(properties)
        if not props:
            raise ValueError(f"{label} node requires at least one property")

        key_props = _pick_identity_props(props, identity_keys)
        key = _make_key(label, key_props)
        existing = self.nodes.get(key)
        merged_props = {**existing.properties, **props} if existing else props
        identity = (
            existing.identity_keys
            if existing and existing.identity_keys
            else identity_keys if key_props and identity_keys else ()
        )
        node = GraphNodeSpec(label, key, merged_props, identity)
        self.nodes[key] = node
        return node

    def add_edge(self, edge_type: str, source: str, target: str) -> None:
        self.edges.append(GraphEdgeSpec(edge_type, source, target))

    def to_payload(self) -> GraphPayload:
        seen: set[tuple[str, str, str]] = set()
        deduped = []
        for edge in self.edges:
            key = (edge.type, edge.source, edge.target)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(edge)
        return GraphPayload(nodes=tuple(self.nodes.values()), edges=tuple(deduped))


def _make_key(label: str, props: Dict[str, Any]) -> str:
    digest = hashlib.sha1(
        json.dumps(props, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return f"{label}::{digest[:12]}"


def _pick_identity_props(
    props: Dict[str, Any], identity_keys: Tuple[str, ...]
) -> Dict[str, Any]:
    if not identity_keys:
        return props

    key_props = {
        k: props[k]
        for k in identity_keys
        if k in props and _has_value(props[k])
    }
    return key_props or props


def _has_value(val: Any) -> bool:
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, (list, tuple, set, dict)):
        return bool(val)
    return val is not None


def clean_props(props: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in props.items()
        if v is not None
        and (not isinstance(v, str) or v.strip())
        and not isinstance(v, dict)
    }
