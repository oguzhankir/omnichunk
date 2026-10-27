"""Mixed Markdown sections retain the identities of their constituent blocks."""

from __future__ import annotations

import pytest

from omnichunk import Chunker, EntityType
from omnichunk.parser.markdown_parser import parse_markdown


def test_mixed_section_classifies_each_block_instead_of_its_first_table() -> None:
    source = (
        "# Manual\n\nRead the introduction.\n\n"
        "| Setting | Value |\n| --- | --- |\n| retry | 3 |\n\n"
        "Follow the instructions.\n\n"
        "1. Open the file.\n2. Check the setting.\n\nKeep a backup.\n"
    )
    _, nodes = parse_markdown(source)
    assert [node.kind for node in nodes] == [
        EntityType.HEADING,
        EntityType.PARAGRAPH,
        EntityType.TABLE,
        EntityType.PARAGRAPH,
        EntityType.LIST,
        EntityType.PARAGRAPH,
    ]
    chunks = Chunker(
        max_chunk_size=300,
        min_chunk_size=200,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("manual.md", source)
    assert len(chunks) == 5
    assert "".join(chunk.text for chunk in chunks) == source
    assert [chunk.context.section_type for chunk in chunks[1:]] == [
        "table",
        "paragraph",
        "list",
        "paragraph",
    ]
    assert all(chunk.context.heading_hierarchy == ["Manual"] for chunk in chunks)


def test_table_without_blank_lines_does_not_consume_adjacent_prose() -> None:
    source = "Before the table.\n| A | B |\n| --- | --- |\n| one | two |\nAfter the table.\n"
    _, nodes = parse_markdown(source)
    assert [node.kind for node in nodes] == [
        EntityType.PARAGRAPH,
        EntityType.TABLE,
        EntityType.PARAGRAPH,
    ]
    assert "".join(node.text for node in nodes) == source


def test_list_indented_continuations_remain_with_the_list() -> None:
    source = "- First item\n  its continuation\n- Second item\n\nOrdinary prose.\n"
    _, nodes = parse_markdown(source)
    assert [node.kind for node in nodes] == [EntityType.LIST, EntityType.PARAGRAPH]
    assert nodes[0].text == "- First item\n  its continuation\n- Second item\n\n"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_mixed_blocks_keep_utf8_ranges_native_budget_and_stream_parity(newline: str) -> None:
    source = newline.join(
        [
            "# Rehber",
            "",
            "Önce belgeyi açın. 😀",
            "",
            "| Ad | Değer |",
            "| --- | --- |",
            "| süre | üç gün |",
            "",
            "- Kaynağı doğrulayın.",
            "- Sonucu kaydedin.",
            "",
            "Son paragraf.",
            "",
        ]
    )

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2 + (7 if "|" in text and "😀" in text else 0)

    chunker = Chunker(
        max_chunk_size=90,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk("rehber.md", source)
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    for chunk in chunks:
        assert raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8") == chunk.text
        assert count(chunk.contextualized_text) <= 90
    assert [chunk.text for chunk in chunker.stream("rehber.md", source)] == [
        chunk.text for chunk in chunks
    ]
