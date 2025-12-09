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

    def add_node(self, label: str, properties: Dict[str, Any]) -> GraphNodeSpec:
        props = clean_props(properties)
        if not props:
            raise ValueError(f"{label} node requires at least one property")
        key = _make_key(label, props)
        node = GraphNodeSpec(label, key, props)
        if existing := self.nodes.get(key):
            merged = {**existing.properties, **props}
            node = GraphNodeSpec(node.label, key, merged)
        self.nodes[node.key] = node
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


def clean_props(props: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in props.items()
        if v is not None and (not isinstance(v, str) or v.strip())
    }
