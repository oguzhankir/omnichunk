"""Regression: indexed name-capture lookup matches naive full-list scan (determinism)."""

from __future__ import annotations

from typing import Any

from test_entity_extraction import _FakeNode

from omnichunk.context.entities import (
    _build_name_capture_index,
    _distance_to_ancestor,
    _find_query_name_capture,
)


def _find_query_name_capture_naive(entity_node: Any, name_nodes: list[Any]) -> Any | None:
    """Reference implementation (pre-index): scan all name_nodes per entity."""
    entity_start = int(getattr(entity_node, "start_byte", 0))
    entity_end = int(getattr(entity_node, "end_byte", entity_start))

    best_node: Any | None = None
    best_key: tuple[int, int, int] | None = None

    for name_node in name_nodes:
        name_start = int(getattr(name_node, "start_byte", 0))
        name_end = int(getattr(name_node, "end_byte", name_start))
        if name_start < entity_start or name_end > entity_end:
            continue

        distance = _distance_to_ancestor(name_node, entity_node)
        if distance is None:
            continue

        key = (distance, name_start - entity_start, name_end - name_start)
        if best_key is None or key < best_key:
            best_key = key
            best_node = name_node

    if best_node is not None:
        return best_node

    fallback_node: Any | None = None
    fallback_key: tuple[int, int, int] | None = None
    for name_node in name_nodes:
        name_start = int(getattr(name_node, "start_byte", 0))
        name_end = int(getattr(name_node, "end_byte", name_start))
        if name_start < entity_start or name_end > entity_end:
            continue
        key = (0, abs(name_start - entity_start), name_end - name_start)
        if fallback_key is None or key < fallback_key:
            fallback_key = key
            fallback_node = name_node

    return fallback_node


def test_find_query_name_capture_index_matches_naive() -> None:
    # Nested structure: outer entity contains inner; multiple name nodes at various depths.
    name_outer = _FakeNode("identifier", 10, 15)
    name_inner = _FakeNode("identifier", 30, 35)
    name_sibling = _FakeNode("identifier", 50, 55)
    inner = _FakeNode("inner", 25, 45, children=[name_inner])
    sibling = _FakeNode("sibling", 45, 60, children=[name_sibling])
    root = _FakeNode("root", 0, 100, children=[name_outer, inner, sibling])

    name_nodes = [name_outer, name_inner, name_sibling, name_inner]  # duplicate id last
    index = _build_name_capture_index(name_nodes)

    for entity in (root, inner, sibling):
        got = _find_query_name_capture(entity, index)
        want = _find_query_name_capture_naive(entity, name_nodes)
        assert got is want

    empty_index = _build_name_capture_index([])
    assert _find_query_name_capture(root, empty_index) is None
