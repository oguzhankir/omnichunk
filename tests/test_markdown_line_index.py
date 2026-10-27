"""Every Markdown block reuses one source line index instead of rescanning prefixes."""

from __future__ import annotations

import pytest

from omnichunk.parser import markdown_parser


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_shared_line_index_matches_range_coordinates_for_all_node_kinds(monkeypatch, newline):
    source = (
        "---\nowner: Ada\n---\n# Başlık 😀\n\nÖnce açıklama.\n\n"
        "| Ad | Değer |\n| --- | --- |\n| süre | üç |\n\n"
        "- Madde.\n\n  Açıklama.\n\n```text\nİçerik\n```\n\n"
        "## Alt başlık\n\nSon açıklama.\n"
    ).replace("\n", newline)
    original = markdown_parser._line_range
    indexes = []

    def capture(content, start, end, *, line_starts=None):
        assert line_starts is not None
        indexes.append(line_starts)
        result = original(content, start, end, line_starts=line_starts)
        assert result.start == source.count("\n", 0, start)
        assert result.end == source.count("\n", 0, max(start, end))
        return result

    monkeypatch.setattr(markdown_parser, "_line_range", capture)
    sections, nodes = markdown_parser.parse_markdown(source)
    assert sections and nodes
    assert len(indexes) >= len(nodes) + len(sections)
    assert len({id(index) for index in indexes}) == 1
    for node in nodes:
        assert source[node.byte_range.start : node.byte_range.end] == node.text


def test_many_paragraphs_do_not_call_prefix_count():
    class NoPrefixScans(str):
        def count(self, substring, *args):
            assert substring != "\n", "Repeated prefix line counting makes parsing quadratic"
            return super().count(substring, *args)

    source = NoPrefixScans(("Önce kaynakları doğrulayın. 😀\n\n") * 1000)
    _, nodes = markdown_parser.parse_markdown(source)
    assert len(nodes) == 1000
    assert "".join(node.text for node in nodes) == source
