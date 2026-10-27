"""Loose list items retain ownership of their continuation paragraphs."""

from __future__ import annotations

import pytest

from omnichunk import Chunker, EntityType
from omnichunk.parser.markdown_parser import parse_markdown


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("marker", ["- ", "1. ", "10) "])
@pytest.mark.parametrize("base_indent", ["", "  "])
@pytest.mark.parametrize("policy", ["preserve", "pack"])
def test_loose_lists_keep_nested_and_continuation_paragraphs(newline, marker, base_indent, policy):
    continuation = " " * (len(base_indent) + len(marker))
    loose = (
        base_indent
        + marker
        + "İlk madde 😀.\n\n"
        + continuation
        + "İlk maddenin açıklaması.\n\n"
        + continuation
        + "- İç madde.\n\n"
        + continuation
        + "Ek açıklama.\n\n"
        + base_indent
        + marker
        + "İkinci madde.\n\n"
    ).replace("\n", newline)
    following = (base_indent + "Bağımsız paragraf.\n").replace("\n", newline)
    source = loose + following
    _, nodes = parse_markdown(source)
    assert [node.kind for node in nodes] == [EntityType.LIST, EntityType.PARAGRAPH]
    assert [node.text for node in nodes] == [loose, following]
    chunker = Chunker(
        max_chunk_size=1000,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        markdown_paragraph_policy=policy,
    )
    chunks = chunker.chunk("rehber.md", source)
    assert [c.text for c in chunks] == [loose, following]
    assert [c.context.section_type for c in chunks] == ["list", "paragraph"]
    assert [c.text for c in chunker.stream("rehber.md", source)] == [c.text for c in chunks]
    for c in chunks:
        assert source.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text


def test_tab_continuation_and_trailing_blank_lines_belong_to_list():
    source = "- First item\n\n\tAdditional detail.\n\n- Second item\n\n\n"
    _, nodes = parse_markdown(source)
    assert len(nodes) == 1 and nodes[0].kind == EntityType.LIST
    assert nodes[0].text == source


def test_dedented_indented_prose_is_not_a_list_continuation():
    source = "  - First item\n\n   Dedented paragraph.\n"
    _, nodes = parse_markdown(source)
    assert [node.kind for node in nodes] == [EntityType.LIST, EntityType.PARAGRAPH]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("policy", ["preserve", "pack"])
def test_loose_list_fallback_keeps_source_budget_heading_and_list_metadata(newline, policy):
    source = (
        "# Rehber\n\n- İlk madde 😀.\n\n  Uzun açıklama. "
        + "İşlemi doğrulayın. " * 12
        + "\n\n- Son madde.\n\nSon paragraf.\n"
    ).replace("\n", newline)

    def count(text):
        return len(text.encode()) + 2 + (7 if "😀" in text and "doğrulayın" in text else 0)

    chunker = Chunker(
        max_chunk_size=85,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
        markdown_paragraph_policy=policy,
    )
    chunks = chunker.chunk("rehber.md", source)
    assert "".join(c.text for c in chunks) == source
    assert all(c.context.heading_hierarchy == ["Rehber"] for c in chunks)
    assert all(c.context.section_type == "list" for c in chunks if "doğrulayın" in c.text)
    assert chunks[-1].context.section_type == "paragraph"
    for c in chunks:
        assert count(c.contextualized_text) <= 85
        assert source.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text
    assert [c.text for c in chunker.stream("rehber.md", source)] == [c.text for c in chunks]
