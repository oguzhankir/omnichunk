"""Graph analytics over a :class:`ChunkGraph`: centrality, communities, export.

Pure-Python, dependency-free. These routines treat the chunk-to-chunk graph
(chunks connected when they share entities) as an undirected weighted graph.
They are intended for small graphs (< ~500 chunks); for larger graphs export
to networkx via :func:`to_networkx_dict` and use its optimized algorithms.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .types import ChunkGraph

_LARGE_GRAPH_THRESHOLD = 500


def _adjacency(graph: ChunkGraph) -> dict[int, dict[int, float]]:
    """Undirected weighted adjacency: ``adj[a][b] == edge weight``."""
    adj: dict[int, dict[int, float]] = {i: {} for i in range(graph.chunk_count)}
    for edge in graph.edges:
        a, b = edge.chunk_a, edge.chunk_b
        if a not in adj:
            adj[a] = {}
        if b not in adj:
            adj[b] = {}
        adj[a][b] = edge.weight
        adj[b][a] = edge.weight
    return adj


def compute_centrality(graph: ChunkGraph) -> dict[int, float]:
    """Betweenness centrality per chunk index via Brandes' algorithm.

    Higher values mark chunks that lie on many shortest information paths
    between other chunks — the structural "hubs" of the document. Computed on
    the unweighted shortest-path structure (edges as hops) and normalized for
    an undirected graph. Returns ``{}`` for an empty graph.
    """
    n = graph.chunk_count
    if n == 0:
        return {}
    adj = _adjacency(graph)
    betweenness: dict[int, float] = {v: 0.0 for v in range(n)}

    for s in range(n):
        stack: list[int] = []
        preds: dict[int, list[int]] = {w: [] for w in range(n)}
        sigma: dict[int, float] = dict.fromkeys(range(n), 0.0)
        sigma[s] = 1.0
        dist: dict[int, int] = dict.fromkeys(range(n), -1)
        dist[s] = 0
        queue: deque[int] = deque([s])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in sorted(adj[v]):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)

        delta: dict[int, float] = dict.fromkeys(range(n), 0.0)
        while stack:
            w = stack.pop()
            for v in preds[w]:
                if sigma[w] > 0:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                betweenness[w] += delta[w]

    # Undirected: each shortest path counted in both directions.
    for v in betweenness:
        betweenness[v] /= 2.0
    return betweenness


def find_communities(graph: ChunkGraph) -> list[list[int]]:
    """Detect communities via deterministic weighted label propagation.

    Each chunk starts in its own community and repeatedly adopts the label
    with the greatest summed edge weight among its neighbors (ties broken by
    the smallest label). Returns a list of communities, each a sorted list of
    chunk indices; the list is ordered by each community's smallest member.
    """
    n = graph.chunk_count
    if n == 0:
        return []
    adj = _adjacency(graph)
    labels = list(range(n))

    # Deterministic, bounded iteration -> guaranteed termination.
    for _ in range(100):
        changed = False
        for v in range(n):
            neighbors = adj[v]
            if not neighbors:
                continue
            weight_by_label: dict[int, float] = defaultdict(float)
            for nb, w in neighbors.items():
                weight_by_label[labels[nb]] += w
            # Max weight; tie-break on smallest label for determinism.
            best_label = min(
                weight_by_label,
                key=lambda lbl: (-weight_by_label[lbl], lbl),
            )
            if labels[v] != best_label:
                labels[v] = best_label
                changed = True
        if not changed:
            break

    groups: dict[int, list[int]] = defaultdict(list)
    for v in range(n):
        groups[labels[v]].append(v)
    communities = [sorted(members) for members in groups.values()]
    communities.sort(key=lambda members: members[0])
    return communities


def to_networkx_dict(graph: ChunkGraph) -> dict[str, Any]:
    """Export the weighted chunk graph as a networkx node-link dict.

    The returned dict is compatible with ``networkx.node_link_graph`` (keys
    ``nodes`` and ``links``) and tagged ``{"format": "networkx_dict"}`` so
    downstream tooling can detect it::

        import networkx as nx
        G = nx.node_link_graph(to_networkx_dict(graph))
    """
    return {
        "format": "networkx_dict",
        "directed": False,
        "multigraph": False,
        "graph": {"chunk_count": graph.chunk_count},
        "nodes": [{"id": i} for i in range(graph.chunk_count)],
        "links": [
            {
                "source": e.chunk_a,
                "target": e.chunk_b,
                "weight": e.weight,
                "shared": list(e.shared_entities),
            }
            for e in graph.edges
        ],
    }
