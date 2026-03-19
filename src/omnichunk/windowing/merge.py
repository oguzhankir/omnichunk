from __future__ import annotations

from collections.abc import Iterable

from .models import ASTNodeWindowItem


def merge_adjacent_windows(
    windows: Iterable[list[ASTNodeWindowItem]],
    *,
    max_size: int,
    min_size: int,
) -> list[list[ASTNodeWindowItem]]:
    """Merge adjacent windows by max_size and enforce min_size softly."""
    merged: list[list[ASTNodeWindowItem]] = []

    for window in windows:
        if not window:
            continue

        if not merged:
            merged.append(list(window))
            continue

        prev = merged[-1]
        prev_size = sum(item.size for item in prev)
        curr_size = sum(item.size for item in window)

        if prev_size + curr_size <= max_size:
            prev.extend(window)
        else:
            merged.append(list(window))

    if len(merged) <= 1:
        return merged

    idx = 0
    while idx < len(merged):
        window = merged[idx]
        size = sum(item.size for item in window)
        if size >= min_size or len(merged) == 1:
            idx += 1
            continue

        if idx + 1 < len(merged):
            window.extend(merged[idx + 1])
            del merged[idx + 1]
            continue

        if idx > 0:
            merged[idx - 1].extend(window)
            del merged[idx]
            idx -= 1
            continue

        idx += 1

    return merged
