from __future__ import annotations

import re
from dataclasses import dataclass, field

from omnichunk.types import ByteRange, EntityType, LineRange


@dataclass
class ProseNode:
    kind: EntityType
    text: str
    byte_range: ByteRange
    line_range: LineRange
    heading_hierarchy: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Section:
    heading: str
    level: int
    content: str
    byte_range: ByteRange
    line_range: LineRange
    children: list[Section] = field(default_factory=list)


_FENCE_RE = re.compile(r"(?m)^```([\w+-]*)\s*$")
_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_TABLE_RE = re.compile(r"(?m)^\|.+\|\s*$")
_LIST_RE = re.compile(r"(?m)^\s*[-*+]\s+.+$")
_FRONTMATTER_RE = re.compile(r"\A---\n([\s\S]*?)\n---\n", re.MULTILINE)


def parse_markdown(content: str) -> tuple[list[Section], list[ProseNode]]:
    if not content:
        return [], []

    nodes: list[ProseNode] = []
    sections = _build_section_tree(content)

    front = _FRONTMATTER_RE.match(content)
    if front:
        start = front.start()
        end = front.end()
        nodes.append(
            ProseNode(
                kind=EntityType.FRONTMATTER,
                text=content[start:end],
                byte_range=ByteRange(start, end),
                line_range=_line_range(content, start, end),
            )
        )

    fence_ranges = _collect_fences(content)
    heading_ranges = _collect_headings(content)

    boundary_points = {0, len(content)}
    for s, e, _ in fence_ranges:
        boundary_points.add(s)
        boundary_points.add(e)
    for s, e, _ in heading_ranges:
        boundary_points.add(s)
        boundary_points.add(e)

    sorted_points = sorted(boundary_points)
    for left, right in zip(sorted_points, sorted_points[1:], strict=False):
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
        kind = EntityType.PARAGRAPH
        if _TABLE_RE.search(segment):
            kind = EntityType.TABLE
        elif _LIST_RE.search(segment):
            kind = EntityType.LIST

        nodes.append(
            ProseNode(
                kind=kind,
                text=segment,
                byte_range=ByteRange(left, right),
                line_range=_line_range(content, left, right),
                heading_hierarchy=hierarchy,
            )
        )

    nodes.sort(key=lambda n: n.byte_range.start)
    return sections, nodes


def _collect_fences(content: str) -> list[tuple[int, int, str]]:
    matches = list(_FENCE_RE.finditer(content))
    out: list[tuple[int, int, str]] = []
    idx = 0
    while idx + 1 < len(matches):
        start = matches[idx].start()
        lang = (matches[idx].group(1) or "").strip().lower()
        end = matches[idx + 1].end()
        out.append((start, end, lang))
        idx += 2
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


def _build_section_tree(content: str) -> list[Section]:
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
            if node.byte_range.start <= pos < node.byte_range.end:
                next_chain = chain + [node.heading]
                path[:] = next_chain
                if walk(node.children, next_chain):
                    return True
                return True
        return False

    walk(sections, [])
    return path


def _line_range(content: str, start: int, end: int) -> LineRange:
    line_start = content.count("\n", 0, start)
    line_end = content.count("\n", 0, max(start, end))
    return LineRange(start=line_start, end=max(line_start, line_end))
