from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from omnichunk.types import Chunk

from .types import ChunkEdge, ChunkGraph, EntityNode


def build_chunk_graph(
    chunks: Sequence[Chunk],
    *,
    min_entity_occurrences: int = 2,
    ignore_types: frozenset[str] = frozenset({"import", "export"}),
) -> ChunkGraph:
    n = len(chunks)
    if n == 0:
        return ChunkGraph(chunk_count=0)

    chunk_entities: list[set[str]] = [set() for _ in range(n)]
    inverted: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    entity_type_for: dict[str, str] = {}

    for idx, ch in enumerate(chunks):
        for ent in ch.context.entities:
            tval = ent.type.value
            if tval in ignore_types:
                continue
            name = ent.name
            chunk_entities[idx].add(name)
            inverted[name].append((idx, ent.is_partial))
            entity_type_for.setdefault(name, tval)

    nodes: dict[str, EntityNode] = {}
    for name, occ in sorted(inverted.items()):
        chunk_indices = tuple(sorted({i for i, _ in occ}))
        if len(chunk_indices) < min_entity_occurrences:
            continue
        partial_in = tuple(sorted({i for i, p in occ if p}))
        nodes[name] = EntityNode(
            name=name,
            entity_type=entity_type_for.get(name, ""),
            chunk_indices=chunk_indices,
            is_partial_in=partial_in,
        )

    pair_keys: set[tuple[int, int]] = set()
    for node in nodes.values():
        cis = list(node.chunk_indices)
        for i in range(len(cis)):
            for j in range(i + 1, len(cis)):
                a, b = cis[i], cis[j]
                if a > b:
                    a, b = b, a
                pair_keys.add((a, b))

    edges: list[ChunkEdge] = []
    for a, b in sorted(pair_keys):
        union = chunk_entities[a] | chunk_entities[b]
        inter = chunk_entities[a] & chunk_entities[b]
        if not inter:
            continue
        shared_names = tuple(sorted(inter))
        weight = len(shared_names) / len(union) if union else 0.0
        edges.append(
            ChunkEdge(
                chunk_a=a,
                chunk_b=b,
                shared_entities=shared_names,
                weight=weight,
            )
        )

    return ChunkGraph(nodes=nodes, edges=edges, chunk_count=n)
