from __future__ import annotations

from dataclasses import dataclass, field
import re

from omnichunk.types import ByteRange, LineRange


@dataclass
class HtmlNode:
    tag: str
    byte_range: ByteRange
    line_range: LineRange
    path: list[str] = field(default_factory=list)


_TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9:_-]*)(\s[^>]*)?>|</([a-zA-Z][a-zA-Z0-9:_-]*)\s*>")


def parse_html_structure(content: str) -> list[HtmlNode]:
    if not content:
        return []

    nodes: list[HtmlNode] = []
    stack: list[tuple[str, int, list[str]]] = []

    for match in _TAG_RE.finditer(content):
        open_tag = match.group(1)
        close_tag = match.group(3)

        if open_tag:
            tag = open_tag.lower()
            path = [entry[0] for entry in stack] + [tag]
            stack.append((tag, match.start(), path))
            is_self_close = content[match.start() : match.end()].rstrip().endswith("/>")
            if is_self_close:
                start = match.start()
                end = match.end()
                nodes.append(
                    HtmlNode(
                        tag=tag,
                        byte_range=ByteRange(start, end),
                        line_range=_line_range(content, start, end),
                        path=path,
                    )
                )
                stack.pop()
            continue

        if close_tag:
            tag = close_tag.lower()
            idx = len(stack) - 1
            while idx >= 0 and stack[idx][0] != tag:
                idx -= 1
            if idx < 0:
                continue
            open_entry = stack[idx]
            del stack[idx:]
            start = open_entry[1]
            end = match.end()
            nodes.append(
                HtmlNode(
                    tag=tag,
                    byte_range=ByteRange(start, end),
                    line_range=_line_range(content, start, end),
                    path=open_entry[2],
                )
            )

    nodes.sort(key=lambda n: (n.byte_range.start, -(n.byte_range.end - n.byte_range.start)))
    return nodes


def _line_range(content: str, start: int, end: int) -> LineRange:
    line_start = content.count("\n", 0, start)
    line_end = content.count("\n", 0, max(start, end))
    return LineRange(start=line_start, end=max(line_start, line_end))
