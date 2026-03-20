from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntityNode:
    """A named entity that appears in one or more chunks."""

    name: str
    entity_type: str
    chunk_indices: tuple[int, ...]
    is_partial_in: tuple[int, ...]


@dataclass(frozen=True)
class ChunkEdge:
    """A directed edge: chunk_a and chunk_b share at least one entity."""

    chunk_a: int
    chunk_b: int
    shared_entities: tuple[str, ...]
    weight: float


@dataclass
class ChunkGraph:
    """Entity-chunk relationship graph built from a list of chunks."""

    nodes: dict[str, EntityNode] = field(default_factory=dict)
    edges: list[ChunkEdge] = field(default_factory=list)
    chunk_count: int = 0

    def entity_chunks(self, entity_name: str) -> list[int]:
        node = self.nodes.get(entity_name)
        return list(node.chunk_indices) if node else []

    def chunk_neighbors(self, chunk_index: int) -> list[int]:
        neighbors: set[int] = set()
        for edge in self.edges:
            if edge.chunk_a == chunk_index:
                neighbors.add(edge.chunk_b)
            elif edge.chunk_b == chunk_index:
                neighbors.add(edge.chunk_a)
        return sorted(neighbors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_count": self.chunk_count,
            "nodes": {
                name: {
                    "type": node.entity_type,
                    "chunks": list(node.chunk_indices),
                    "partial_in": list(node.is_partial_in),
                }
                for name, node in self.nodes.items()
            },
            "edges": [
                {
                    "chunk_a": e.chunk_a,
                    "chunk_b": e.chunk_b,
                    "shared": list(e.shared_entities),
                    "weight": e.weight,
                }
                for e in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChunkGraph:
        nodes: dict[str, EntityNode] = {}
        raw_nodes = data.get("nodes") or {}
        for name, payload in raw_nodes.items():
            nodes[name] = EntityNode(
                name=name,
                entity_type=str(payload.get("type", "")),
                chunk_indices=tuple(int(x) for x in payload.get("chunks", [])),
                is_partial_in=tuple(int(x) for x in payload.get("partial_in", [])),
            )
        edges: list[ChunkEdge] = []
        for e in data.get("edges") or []:
            edges.append(
                ChunkEdge(
                    chunk_a=int(e["chunk_a"]),
                    chunk_b=int(e["chunk_b"]),
                    shared_entities=tuple(str(x) for x in e.get("shared", [])),
                    weight=float(e.get("weight", 0.0)),
                )
            )
        edges.sort(key=lambda x: (x.chunk_a, x.chunk_b))
        return cls(
            nodes=nodes,
            edges=edges,
            chunk_count=int(data.get("chunk_count", 0)),
        )
