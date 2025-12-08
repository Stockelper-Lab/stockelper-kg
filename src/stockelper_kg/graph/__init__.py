"""Neo4j graph database modules with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "Neo4jClient",
    "GraphBuilder",
    "GraphPayload",
    "GraphNodeSpec",
    "GraphEdgeSpec",
    "build_graph_payload",
    "build_stock_snapshot_payload",
    "build_competitor_payload",
    "payload_to_cypher",
    "generate_constraints",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve submodules to avoid importing heavy dependencies."""
    if name == "GraphBuilder":
        from .builder import GraphBuilder

        return GraphBuilder

    if name == "Neo4jClient":
        from .client import Neo4jClient

        return Neo4jClient

    if name in (
        "GraphPayload",
        "GraphNodeSpec",
        "GraphEdgeSpec",
        "build_graph_payload",
        "build_stock_snapshot_payload",
        "build_competitor_payload",
    ):
        from . import payload

        return getattr(payload, name)

    if name == "payload_to_cypher":
        from .cypher import payload_to_cypher

        return payload_to_cypher

    if name == "generate_constraints":
        from .cypher import generate_constraints

        return generate_constraints

    raise AttributeError(f"module 'stockelper_kg.graph' has no attribute '{name}'")
