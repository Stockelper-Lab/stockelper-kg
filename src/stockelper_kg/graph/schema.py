"""Graph data structures and construction primitives.

This module defines the low-level building blocks for the Knowledge Graph.
Identity/uniqueness is handled by Neo4j constraints, not client-side logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Tuple


@dataclass(frozen=True)
class GraphNodeSpec:
    """Node specification for graph operations."""

    label: str
    key: str
    properties: Dict[str, Any]
    identity_keys: Tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphEdgeSpec:
    """Edge specification for graph operations."""

    type: str
    source: str
    target: str


@dataclass(frozen=True)
class GraphPayload:
    """Immutable collection of nodes and edges."""

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
    """Mutable container used while assembling a payload."""

    nodes: Dict[str, GraphNodeSpec] = field(default_factory=dict)
    edges: list[GraphEdgeSpec] = field(default_factory=list)

    def add_node(self, label: str, properties: Dict[str, Any]) -> GraphNodeSpec:
        """Create and add a node to the context. Returns the node spec."""
        props = clean_props(properties)
        if not props:
            raise ValueError(f"{label} node requires at least one property")

        key = _make_key(label, props)
        node = GraphNodeSpec(label=label, key=key, properties=props)
        return self._upsert(node)

    def _upsert(self, node: GraphNodeSpec) -> GraphNodeSpec:
        """Add node, merging properties if key already exists."""
        if existing := self.nodes.get(node.key):
            merged = {**existing.properties, **node.properties}
            node = GraphNodeSpec(node.label, node.key, merged)
        self.nodes[node.key] = node
        return node

    def add_edge(self, edge_type: str, source: str, target: str) -> None:
        """Add a directed edge between two node keys."""
        self.edges.append(GraphEdgeSpec(edge_type, source, target))

    def to_payload(self) -> GraphPayload:
        """Finalize the context into an immutable payload."""
        return GraphPayload(
            nodes=tuple(self.nodes.values()),
            edges=tuple(_dedup_edges(self.edges)),
        )


def _make_key(label: str, props: Dict[str, Any]) -> str:
    """Generate internal key for edge connections within a payload.

    This key is NOT used for Neo4j identity - that's handled by constraints.
    Uses content hash for simplicity and determinism.
    """
    digest = hashlib.sha1(
        json.dumps(props, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return f"{label}::{digest[:12]}"


def clean_props(props: Dict[str, Any]) -> Dict[str, Any]:
    """Remove empty values and strip strings."""
    return {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in props.items()
        if v is not None and (not isinstance(v, str) or v.strip())
    }


def _dedup_edges(edges: Iterable[GraphEdgeSpec]) -> Iterable[GraphEdgeSpec]:
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (edge.type, edge.source, edge.target)
        if key not in seen:
            seen.add(key)
            yield edge
