from __future__ import annotations

from omnichunk import Chunker, build_chunk_graph
from omnichunk.graph import ChunkGraph


def test_build_chunk_graph_basic() -> None:
    code = (
        "def alpha():\n    return 1\n\n"
        "def beta():\n    alpha()\n\n"
        "def gamma():\n    alpha()\n"
    )
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    graph = build_chunk_graph(chunks, min_entity_occurrences=1)
    assert isinstance(graph, ChunkGraph)
    assert graph.chunk_count == len(chunks)
    assert graph.nodes


def test_build_chunk_graph_cross_chunk_entity() -> None:
    code = "def shared():\n    pass\n" + "\n" * 3 + "def caller():\n    shared()\n"
    chunker = Chunker(max_chunk_size=40, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    graph = build_chunk_graph(chunks, min_entity_occurrences=1)
    all_chunk_lists = [list(n.chunk_indices) for n in graph.nodes.values()]
    multi_chunk_entities = [cl for cl in all_chunk_lists if len(cl) >= 2]
    if multi_chunk_entities:
        assert graph.edges


def test_chunk_neighbors_symmetric() -> None:
    code = "def f():\n    pass\n" * 6
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    graph = build_chunk_graph(chunks, min_entity_occurrences=1)
    for edge in graph.edges:
        assert edge.chunk_b in graph.chunk_neighbors(edge.chunk_a)
        assert edge.chunk_a in graph.chunk_neighbors(edge.chunk_b)


def test_chunk_graph_to_dict_round_trip() -> None:
    code = "def foo():\n    pass\n" * 3
    chunker = Chunker(max_chunk_size=40, size_unit="chars")
    chunks = chunker.chunk("x.py", code)
    graph = build_chunk_graph(chunks, min_entity_occurrences=1)
    data = graph.to_dict()
    restored = ChunkGraph.from_dict(data)
    assert restored.chunk_count == graph.chunk_count
    assert set(restored.nodes) == set(graph.nodes)


def test_build_chunk_graph_empty() -> None:
    graph = build_chunk_graph([])
    assert graph.chunk_count == 0
    assert not graph.nodes
    assert not graph.edges


def test_entity_chunks_unknown_entity_returns_empty() -> None:
    graph = build_chunk_graph([])
    assert graph.entity_chunks("nonexistent") == []


def test_chunk_neighbors_no_edges_returns_empty() -> None:
    graph = build_chunk_graph([])
    assert graph.chunk_neighbors(0) == []


def test_build_chunk_graph_min_occurrences_filters() -> None:
    code = "def unique_only():\n    pass\n"
    chunker = Chunker(max_chunk_size=40, size_unit="chars")
    chunks = chunker.chunk("x.py", code)
    graph = build_chunk_graph(chunks, min_entity_occurrences=2)
    assert "unique_only" not in graph.nodes
