"""Entity–chunk graph: neighbors, entity_chunks, and dictionary round-trip.

This inspects extracted entities and shared-entity links. It is a building block
for retrieval, not a full GraphRAG pipeline or semantic relationship extractor.
"""

from __future__ import annotations

from omnichunk import Chunker, build_chunk_graph
from omnichunk.graph import ChunkGraph


def main() -> None:
    code = "def alpha():\n    return 1\n\ndef beta():\n    alpha()\n\ndef gamma():\n    alpha()\n"
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks = chunker.chunk("repo.py", code)
    graph = build_chunk_graph(chunks, min_entity_occurrences=1)

    print(
        f"entities (nodes): {len(graph.nodes)} edges: {len(graph.edges)} "
        f"chunk_count={graph.chunk_count}"
    )

    if "alpha" in graph.nodes:
        print(f"entity_chunks('alpha'): {graph.entity_chunks('alpha')}")

    n0 = graph.chunk_neighbors(0)
    print(f"chunk_neighbors(0): {n0}")

    data = graph.to_dict()
    back = ChunkGraph.from_dict(data)
    assert back.chunk_count == graph.chunk_count
    print("ChunkGraph.from_dict round-trip OK")


if __name__ == "__main__":
    main()
