from __future__ import annotations

from collections.abc import Generator, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from omnichunk.sizing.nws import get_nws_count

from .models import ASTNodeWindowItem
from .split import split_oversized_leaf


@dataclass(frozen=True)
class RangeNode:
    start: int
    end: int
    children: tuple[RangeNode, ...] = ()


def assign_windows_for_ranges(
    ranges: Sequence[tuple[int, int]],
    *,
    cumsum: Any,
    max_size: int,
    code: str,
) -> list[list[ASTNodeWindowItem]]:
    nodes = [RangeNode(start=s, end=e) for s, e in ranges if e > s]
    return list(greedy_assign_windows(nodes, code=code, cumsum=cumsum, max_size=max_size))


def assign_windows_for_nodes(
    nodes: Sequence[Any],
    *,
    cumsum: Any,
    max_size: int,
    code: str,
) -> list[list[ASTNodeWindowItem]]:
    """Assign windows for hierarchical nodes (e.g., AST root children)."""
    return list(greedy_assign_windows(nodes, code=code, cumsum=cumsum, max_size=max_size))


def greedy_assign_windows(
    nodes: Iterable[Any],
    *,
    code: str,
    cumsum: Any,
    max_size: int,
) -> Generator[list[ASTNodeWindowItem], None, None]:
    """Assign nodes into windows greedily using NWS size."""
    # Frames preserve recursive grouping semantics without Python recursion.
    frames: list[tuple[Any, list[ASTNodeWindowItem], int]] = [(iter(nodes), [], 0)]
    while frames:
        iterator, window, window_size = frames[-1]
        node = next(iterator, None)
        if node is None:
            if window:
                yield window
            frames.pop()
            continue
        start, end = _node_range(node)
        if end <= start:
            continue
        node_size = get_nws_count(cumsum, start, end)
        wrapped = ASTNodeWindowItem(node=node, start=start, end=end, size=node_size)
        if window_size + node_size <= max_size:
            window.append(wrapped)
            frames[-1] = (iterator, window, window_size + node_size)
        elif node_size > max_size:
            if window:
                yield window
            frames[-1] = (iterator, [], 0)
            children = tuple(_node_children(node))
            if children:
                frames.append((iter(children), [], 0))
            else:
                for part in split_oversized_leaf(
                    wrapped, code=code, cumsum=cumsum, max_size=max_size
                ):
                    yield [part]
        else:
            if window:
                yield window
            frames[-1] = (iterator, [wrapped], node_size)


def _node_range(node: Any) -> tuple[int, int]:
    if hasattr(node, "start") and hasattr(node, "end"):
        start = int(node.start)
        end = int(node.end)
        return start, end
    return int(getattr(node, "start_byte", 0)), int(getattr(node, "end_byte", 0))


def _node_children(node: Any) -> Iterable[Any]:
    if hasattr(node, "children"):
        return tuple(node.children or ())
    children = getattr(node, "named_children", None)
    if children is not None:
        return tuple(children)
    return ()
