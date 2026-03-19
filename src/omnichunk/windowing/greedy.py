from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generator, Iterable, Sequence

import numpy as np

from omnichunk.sizing.nws import get_nws_count

from .models import ASTNodeWindowItem

from .split import split_oversized_leaf


@dataclass(frozen=True)
class RangeNode:
    start: int
    end: int
    children: tuple["RangeNode", ...] = ()


def assign_windows_for_ranges(
    ranges: Sequence[tuple[int, int]],
    *,
    cumsum: np.ndarray,
    max_size: int,
    code: str,
) -> list[list[ASTNodeWindowItem]]:
    nodes = [RangeNode(start=s, end=e) for s, e in ranges if e > s]
    return list(greedy_assign_windows(nodes, code=code, cumsum=cumsum, max_size=max_size))


def greedy_assign_windows(
    nodes: Iterable[Any],
    *,
    code: str,
    cumsum: np.ndarray,
    max_size: int,
) -> Generator[list[ASTNodeWindowItem], None, None]:
    """Assign nodes into windows greedily using NWS size."""
    current_window: list[ASTNodeWindowItem] = []
    current_size = 0

    for node in nodes:
        start, end = _node_range(node)
        if end <= start:
            continue

        node_size = get_nws_count(cumsum, start, end)
        wrapped = ASTNodeWindowItem(node=node, start=start, end=end, size=node_size)

        if current_size + node_size <= max_size:
            current_window.append(wrapped)
            current_size += node_size
            continue

        if node_size > max_size:
            if current_window:
                yield current_window
                current_window = []
                current_size = 0

            children = list(_node_children(node))
            if children:
                yield from greedy_assign_windows(children, code=code, cumsum=cumsum, max_size=max_size)
                continue

            for split_item in split_oversized_leaf(
                wrapped,
                code=code,
                cumsum=cumsum,
                max_size=max_size,
            ):
                yield [split_item]
            continue

        if current_window:
            yield current_window

        current_window = [wrapped]
        current_size = node_size

    if current_window:
        yield current_window


def _node_range(node: Any) -> tuple[int, int]:
    if hasattr(node, "start") and hasattr(node, "end"):
        start = int(getattr(node, "start"))
        end = int(getattr(node, "end"))
        return start, end
    return int(getattr(node, "start_byte", 0)), int(getattr(node, "end_byte", 0))


def _node_children(node: Any) -> Iterable[Any]:
    if hasattr(node, "children"):
        return tuple(getattr(node, "children") or ())
    children = getattr(node, "named_children", None)
    if children is not None:
        return tuple(children)
    return ()
