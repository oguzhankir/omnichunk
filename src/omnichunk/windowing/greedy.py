from __future__ import annotations

from collections.abc import Generator, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from omnichunk.sizing.nws import get_nws_count

from .models import ASTNodeWindowItem, SourceBudget
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
    budget: SourceBudget | None = None,
    split_oversized: bool = True,
) -> list[list[ASTNodeWindowItem]]:
    nodes = [RangeNode(start=s, end=e) for s, e in ranges if e > s]
    return list(
        greedy_assign_windows(
            nodes,
            code=code,
            cumsum=cumsum,
            max_size=max_size,
            budget=budget,
            split_oversized=split_oversized,
        )
    )


def assign_windows_for_nodes(
    nodes: Sequence[Any],
    *,
    cumsum: Any,
    max_size: int,
    code: str,
    budget: SourceBudget | None = None,
    split_oversized: bool = True,
) -> list[list[ASTNodeWindowItem]]:
    """Assign windows for hierarchical nodes (e.g., AST root children)."""
    return list(
        greedy_assign_windows(
            nodes,
            code=code,
            cumsum=cumsum,
            max_size=max_size,
            budget=budget,
            split_oversized=split_oversized,
        )
    )


def greedy_assign_windows(
    nodes: Iterable[Any],
    *,
    code: str,
    cumsum: Any,
    max_size: int,
    budget: SourceBudget | None = None,
    split_oversized: bool = True,
) -> Generator[list[ASTNodeWindowItem], None, None]:
    """Group nodes using a configured source budget or legacy NWS byte counts."""
    if budget is not None:
        yield from _measured_windows(nodes, budget, max_size, split_oversized)
        return
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


def _nodes_with_ends(nodes: Iterable[Any], end: int) -> Iterable[tuple[Any, int]]:
    """Attach inter-node and trailing source trivia to the preceding sibling."""
    iterator = iter(nodes)
    previous = next(iterator, None)
    if previous is None:
        return
    for node in iterator:
        yield previous, max(_node_range(previous)[1], _node_range(node)[0])
        previous = node
    yield previous, end


def _measured_windows(
    nodes: Iterable[Any], budget: SourceBudget, max_size: int, split_oversized: bool
) -> Generator[list[ASTNodeWindowItem], None, None]:
    total = len(budget.index.raw_bytes)
    whole_size = budget.count(0, total)
    if whole_size <= max_size:
        if total:
            yield [ASTNodeWindowItem(None, 0, total, whole_size)]
        return
    # One cursor owns every source byte, including whitespace and punctuation
    # omitted by named AST children. Explicit frames avoid recursion limits.
    frames = [iter(_nodes_with_ends(nodes, total))]
    cursor = 0
    window: list[ASTNodeWindowItem] = []
    while frames:
        entry = next(frames[-1], None)
        if entry is None:
            frames.pop()
            continue
        node, end = entry
        if end <= cursor:
            continue
        size = budget.count(cursor, end)
        wrapped = ASTNodeWindowItem(node, cursor, end, size)
        if budget.count(window[0].start if window else cursor, end) <= max_size:
            window.append(wrapped)
            cursor = end
            continue
        children = tuple(_node_children(node))
        body_block = str(getattr(node, "type", "")) in {
            "block",
            "statement_block",
            "compound_statement",
            "class_body",
            "declaration_list",
        }
        if split_oversized and children and len(frames) > 1 and (size > max_size or body_block):
            # A declaration header should share its remaining budget with the
            # first fitting statement of an oversized body. Descending does not
            # itself require flushing the pending source prefix.
            frames.append(iter(_nodes_with_ends(children, end)))
            continue
        if window:
            yield window
            window = []
        if size <= max_size or not split_oversized:
            window = [wrapped]
            cursor = end
            continue
        if children:
            frames.append(iter(_nodes_with_ends(children, end)))
        else:
            for part in split_oversized_leaf(
                wrapped, code=budget.text, cumsum=None, max_size=max_size, budget=budget
            ):
                yield [part]
            cursor = end
    if window:
        yield window


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
