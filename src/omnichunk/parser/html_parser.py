from __future__ import annotations

import re
from dataclasses import dataclass, field

from omnichunk.types import ByteRange, LineRange


@dataclass
class HtmlNode:
    tag: str
    byte_range: ByteRange
    line_range: LineRange
    path: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    is_custom_element: bool = False


_TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9:_-]*)(\s[^>]*)?>|</([a-zA-Z][a-zA-Z0-9:_-]*)\s*>")

_ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def _is_custom_element(tag: str) -> bool:
    """Custom elements per the HTML spec contain at least one hyphen."""
    return "-" in tag and not tag.startswith("-")


def _extract_html_metadata(attrs_text: str | None) -> dict[str, str]:
    """Surface aria-label, type, data-* on structural elements."""
    if not attrs_text:
        return {}
    out: dict[str, str] = {}
    for match in _ATTR_RE.finditer(attrs_text):
        name = match.group(1).lower()
        value = match.group(2) or match.group(3) or match.group(4) or ""
        if (
            name == "type"
            or name == "aria-label"
            or name.startswith("data-")
            or name == "is"
            or name == "slot"
        ):
            out[name] = value
    return out


def parse_html_structure(content: str) -> list[HtmlNode]:
    if not content:
        return []

    nodes: list[HtmlNode] = []
    stack: list[tuple[str, int, list[str], dict[str, str]]] = []

    for match in _TAG_RE.finditer(content):
        open_tag = match.group(1)
        attrs_raw = match.group(2)
        close_tag = match.group(3)

        if open_tag:
            tag = open_tag.lower()
            meta = _extract_html_metadata(attrs_raw)
            path = [entry[0] for entry in stack] + [tag]
            stack.append((tag, match.start(), path, meta))
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
                        metadata=meta,
                        is_custom_element=_is_custom_element(tag),
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
                    metadata=open_entry[3] if len(open_entry) > 3 else {},
                    is_custom_element=_is_custom_element(tag),
                )
            )

    nodes.sort(key=lambda n: (n.byte_range.start, -(n.byte_range.end - n.byte_range.start)))
    return nodes


def _line_range(content: str, start: int, end: int) -> LineRange:
    line_start = content.count("\n", 0, start)
    line_end = content.count("\n", 0, max(start, end))
    return LineRange(start=line_start, end=max(line_start, line_end))
