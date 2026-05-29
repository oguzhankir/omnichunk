from __future__ import annotations

from omnichunk import (
    build_chunk_graph,
    compute_centrality,
    find_communities,
    to_networkx_dict,
)
from omnichunk.graph.types import ChunkEdge, ChunkGraph
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ContentType,
    EntityInfo,
    EntityType,
    LineRange,
)


def _chunk(index: int, entity_names: list[str]) -> Chunk:
    entities = [
        EntityInfo(name=name, type=EntityType.FUNCTION) for name in entity_names
    ]
    return Chunk(
        text=f"chunk {index}",
        contextualized_text=f"chunk {index}",
        byte_range=ByteRange(0, 1),
        line_range=LineRange(0, 0),
        index=index,
        total_chunks=-1,
        context=ChunkContext(content_type=ContentType.CODE, entities=entities),
    )


def _graph(chunk_count: int, edges: list[tuple[int, int, float]]) -> ChunkGraph:
    return ChunkGraph(
        nodes={},
        edges=[ChunkEdge(a, b, (), w) for a, b, w in edges],
        chunk_count=chunk_count,
    )


# --- (1) Jaccard edge weights ------------------------------------------------


def test_jaccard_edge_weight_known_sets() -> None:
    # A = {x, y}, B = {x, z} -> shared {x}, union {x, y, z} -> 1/3.
    a = _chunk(0, ["x", "y"])
    b = _chunk(1, ["x", "z"])
    graph = build_chunk_graph([a, b])
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.shared_entities == ("x",)
    assert abs(edge.weight - (1.0 / 3.0)) < 1e-9


def test_jaccard_identical_entity_sets_weight_one() -> None:
    a = _chunk(0, ["x", "y"])
    b = _chunk(1, ["x", "y"])
    graph = build_chunk_graph([a, b])
    assert graph.edges[0].weight == 1.0


def test_edge_weights_in_unit_interval() -> None:
    chunks = [
        _chunk(0, ["a", "b", "c"]),
        _chunk(1, ["b", "c", "d"]),
        _chunk(2, ["c", "d", "e"]),
    ]
    graph = build_chunk_graph(chunks)
    assert graph.edges
    for e in graph.edges:
        assert 0.0 <= e.weight <= 1.0


# --- (2) Betweenness centrality ---------------------------------------------


def test_centrality_empty_graph() -> None:
    assert compute_centrality(ChunkGraph(chunk_count=0)) == {}


def test_centrality_returns_float_dict() -> None:
    graph = _graph(3, [(0, 1, 1.0), (1, 2, 1.0)])
    cent = compute_centrality(graph)
    assert set(cent) == {0, 1, 2}
    assert all(isinstance(v, float) for v in cent.values())


def test_centrality_path_middle_is_central() -> None:
    # Path 0-1-2: only node 1 sits on the 0<->2 shortest path.
    graph = _graph(3, [(0, 1, 1.0), (1, 2, 1.0)])
    cent = compute_centrality(graph)
    assert cent[1] > cent[0]
    assert cent[1] > cent[2]
    assert cent[0] == 0.0
    assert cent[2] == 0.0


def test_centrality_star_center_highest() -> None:
    # Star: 0 connected to 1, 2, 3.
    graph = _graph(4, [(0, 1, 1.0), (0, 2, 1.0), (0, 3, 1.0)])
    cent = compute_centrality(graph)
    assert cent[0] == max(cent.values())
    assert cent[0] > 0.0


# --- (3) Communities (label propagation) ------------------------------------


def test_two_disconnected_triangles_two_communities() -> None:
    edges = [
        (0, 1, 1.0), (1, 2, 1.0), (0, 2, 1.0),
        (3, 4, 1.0), (4, 5, 1.0), (3, 5, 1.0),
    ]
    graph = _graph(6, edges)
    communities = find_communities(graph)
    assert communities == [[0, 1, 2], [3, 4, 5]]


def test_communities_singleton_for_isolated_node() -> None:
    graph = _graph(3, [(0, 1, 1.0)])
    communities = find_communities(graph)
    # Node 2 has no edges -> stays in its own community.
    assert [2] in communities


def test_communities_empty_graph() -> None:
    assert find_communities(ChunkGraph(chunk_count=0)) == []


# --- (4) networkx export -----------------------------------------------------


def test_to_networkx_dict_structure() -> None:
    graph = _graph(3, [(0, 1, 0.5), (1, 2, 0.25)])
    nx = to_networkx_dict(graph)
    assert nx["format"] == "networkx_dict"
    assert nx["directed"] is False
    assert [n["id"] for n in nx["nodes"]] == [0, 1, 2]
    links = {(link["source"], link["target"]): link["weight"] for link in nx["links"]}
    assert links[(0, 1)] == 0.5
    assert links[(1, 2)] == 0.25


def test_to_networkx_dict_roundtrips_via_build() -> None:
    a = _chunk(0, ["shared", "alpha"])
    b = _chunk(1, ["shared", "beta"])
    graph = build_chunk_graph([a, b])
    nx = to_networkx_dict(graph)
    assert nx["links"]
    assert nx["links"][0]["shared"] == ["shared"]
