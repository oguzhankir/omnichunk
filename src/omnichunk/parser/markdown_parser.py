from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any

from omnichunk.types import ByteRange, EntityType, LineRange


@dataclass
class ProseNode:
    """Internal parser node: ``byte_range`` historically contains character offsets.

    The prose engine converts these to UTF-8 byte ranges only when emitting public
    Chunk and EntityInfo objects. Keep string slicing in this parser in characters.
    """

    kind: EntityType
    text: str
    byte_range: ByteRange
    line_range: LineRange
    heading_hierarchy: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_CALLOUT_RE = re.compile(
    r"(?m)^\s*>\s*\[!(?P<kind>[a-zA-Z]+)\]",
)


def _parse_yaml_frontmatter(raw: str) -> dict[str, str]:
    """Parse minimal YAML front matter (top-level key: value lines only).

    Designed to avoid a hard PyYAML dependency. Lists and nested objects
    are returned as their raw string value; the caller may post-process.
    """
    out: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def _detect_callout_kind(text: str) -> str | None:
    """Detect a GFM / Obsidian callout marker at the start of a blockquote."""
    m = _CALLOUT_RE.search(text)
    if not m:
        return None
    return m.group("kind").lower()


@dataclass
class Section:
    heading: str
    level: int
    content: str
    byte_range: ByteRange
    line_range: LineRange
    children: list[Section] = field(default_factory=list)


_FENCE_RE = re.compile(r"(?m)^[ \t]{0,3}(`{3,}|~{3,})([^\r\n]*)(?:\r?\n|$)")
_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_TABLE_RE = re.compile(r"(?m)^\|.+\|\s*$")
_LIST_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S")
_FRONTMATTER_RE = re.compile(r"\A---\n([\s\S]*?)\n---\n", re.MULTILINE)


def parse_markdown(content: str) -> tuple[list[Section], list[ProseNode]]:
    if not content:
        return [], []

    nodes: list[ProseNode] = []
    fence_ranges = _collect_fences(content)
    fence_starts = [start for start, _, _ in fence_ranges]
    heading_matches = []
    for match in _HEADING_RE.finditer(content):
        fence_index = bisect_right(fence_starts, match.start()) - 1
        if fence_index >= 0 and match.start() < fence_ranges[fence_index][1]:
            continue
        heading_matches.append(match)
    sections = _build_section_tree(content, heading_matches)

    front = _FRONTMATTER_RE.match(content)
    if front:
        start = front.start()
        end = front.end()
        body = front.group(1)
        parsed = _parse_yaml_frontmatter(body)
        nodes.append(
            ProseNode(
                kind=EntityType.FRONTMATTER,
                text=content[start:end],
                byte_range=ByteRange(start, end),
                line_range=_line_range(content, start, end),
                metadata={"front_matter": parsed},
            )
        )

    heading_ranges = [(m.start(), m.end(), m.group(1)) for m in heading_matches]

    boundary_points = {0, len(content)}
    for s, e, _ in fence_ranges:
        boundary_points.add(s)
        boundary_points.add(e)
    for s, e, _ in heading_ranges:
        boundary_points.add(s)
        boundary_points.add(e)

    sorted_points = sorted(boundary_points)
    for left, right in zip(sorted_points, sorted_points[1:]):
        if right <= left:
            continue
        segment = content[left:right]
        if not segment.strip():
            continue

        fence = _match_range(left, right, fence_ranges)
        heading = _match_range(left, right, heading_ranges)

        if fence is not None:
            kind = EntityType.CODE_BLOCK
            hierarchy = _heading_hierarchy_at_pos(sections, left)
            nodes.append(
                ProseNode(
                    kind=kind,
                    text=segment,
                    byte_range=ByteRange(left, right),
                    line_range=_line_range(content, left, right),
                    heading_hierarchy=hierarchy,
                    metadata={"language": fence[2]},
                )
            )
            continue

        if heading is not None:
            level = len(heading[2])
            hierarchy = _heading_hierarchy_at_pos(sections, left)
            nodes.append(
                ProseNode(
                    kind=EntityType.HEADING,
                    text=segment,
                    byte_range=ByteRange(left, right),
                    line_range=_line_range(content, left, right),
                    heading_hierarchy=hierarchy,
                    metadata={"level": str(level)},
                )
            )
            continue

        hierarchy = _heading_hierarchy_at_pos(sections, left)
        nodes.extend(_body_nodes(content, left, right, hierarchy))

    nodes.sort(key=lambda n: n.byte_range.start)
    return sections, nodes


def _body_nodes(content: str, start: int, end: int, hierarchy: list[str]) -> list[ProseNode]:
    """Keep tables and lists separate from the prose surrounding them.

    Classifying a complete section from one matching line would label unrelated
    paragraphs as tables/lists and bypass their structural boundaries. Keep
    source trivia attached to its preceding block so ranges remain contiguous.
    """
    out: list[ProseNode] = []
    block_start = start
    cursor = start
    kind: EntityType | None = None

    def emit(block_end: int) -> None:
        nonlocal block_start, kind
        text = content[block_start:block_end]
        if text.strip():
            metadata: dict[str, Any] = {}
            callout = _detect_callout_kind(text)
            if callout is not None:
                metadata["callout"] = callout
            out.append(
                ProseNode(
                    kind=kind or EntityType.PARAGRAPH,
                    text=text,
                    byte_range=ByteRange(block_start, block_end),
                    line_range=_line_range(content, block_start, block_end),
                    heading_hierarchy=list(hierarchy),
                    metadata=metadata,
                )
            )
            block_start = block_end
            kind = None

    for line in content[start:end].splitlines(keepends=True):
        line_end = cursor + len(line)
        if not line.strip():
            emit(line_end)
            cursor = line_end
            continue
        if _TABLE_RE.fullmatch(line.rstrip("\r\n")):
            line_kind = EntityType.TABLE
        elif _LIST_RE.match(line):
            line_kind = EntityType.LIST
        elif kind == EntityType.LIST and line.startswith((" ", "\t")):
            # Indented continuation lines belong to the current list item.
            line_kind = EntityType.LIST
        else:
            line_kind = EntityType.PARAGRAPH
        if kind is not None and line_kind != kind:
            emit(cursor)
        kind = line_kind
        cursor = line_end
    emit(end)
    return out


def _collect_fences(content: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    opening: re.Match[str] | None = None
    for match in _FENCE_RE.finditer(content):
        fence, info = match.group(1), match.group(2)
        if opening is None:
            if fence[0] == "`" and "`" in info:
                continue
            opening = match
        elif (
            fence[0] == opening.group(1)[0]
            and len(fence) >= len(opening.group(1))
            and not info.strip()
        ):
            language = opening.group(2).strip().split(maxsplit=1)
            out.append((opening.start(), match.end(), language[0].lower() if language else ""))
            opening = None
    if opening is not None:
        language = opening.group(2).strip().split(maxsplit=1)
        out.append((opening.start(), len(content), language[0].lower() if language else ""))
    return out


def _collect_headings(content: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(1)) for m in _HEADING_RE.finditer(content)]


def _match_range(
    start: int,
    end: int,
    ranges: list[tuple[int, int, str]],
) -> tuple[int, int, str] | None:
    for r in ranges:
        if r[0] <= start and r[1] >= end:
            return r
    return None


def _build_section_tree(content: str, headings: list[re.Match[str]] | None = None) -> list[Section]:
    if headings is None:
        headings = list(_HEADING_RE.finditer(content))
    if not headings:
        return []

    sections: list[Section] = []
    stack: list[Section] = []

    for idx, match in enumerate(headings):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.start()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(content)
        section = Section(
            heading=title,
            level=level,
            content=content[start:end],
            byte_range=ByteRange(start, end),
            line_range=_line_range(content, start, end),
        )

        while stack and stack[-1].level >= level:
            stack.pop()

        if not stack:
            sections.append(section)
        else:
            stack[-1].children.append(section)

        stack.append(section)

    return sections


def _heading_hierarchy_at_pos(sections: list[Section], pos: int) -> list[str]:
    path: list[str] = []

    def walk(nodes: list[Section], chain: list[str]) -> bool:
        for node in nodes:
            next_chain = chain + [node.heading]
            # Section spans describe their direct body up to the next heading;
            # descendants have their own disjoint spans within the tree.
            if walk(node.children, next_chain):
                return True
            if node.byte_range.start <= pos < node.byte_range.end:
                path[:] = next_chain
                return True
        return False

    walk(sections, [])
    return path


def _line_range(content: str, start: int, end: int) -> LineRange:
    line_start = content.count("\n", 0, start)
    line_end = content.count("\n", 0, max(start, end))
    return LineRange(start=line_start, end=max(line_start, line_end))
