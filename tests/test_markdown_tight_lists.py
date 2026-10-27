"""Tight-list lazy continuations retain ownership without swallowing new blocks."""

from __future__ import annotations

import pytest

from omnichunk import Chunker, EntityType
from omnichunk.parser.markdown_parser import parse_markdown


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("marker", ["- ", "1. ", "1) "])
@pytest.mark.parametrize("policy", ["preserve", "pack"])
def test_tight_list_lazy_unindented_continuations_keep_list_metadata(newline, marker, policy):
    listing = (
        marker + "First item 😀.\nLazy continuation of item.\n" + marker + "Second item.\n\n"
    ).replace("\n", newline)
    following = "Independent paragraph.\n".replace("\n", newline)
    source = listing + following
    _, nodes = parse_markdown(source)
    assert [n.kind for n in nodes] == [EntityType.LIST, EntityType.PARAGRAPH]
    assert [n.text for n in nodes] == [listing, following]
    chunker = Chunker(
        max_chunk_size=500,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        markdown_paragraph_policy=policy,
    )
    chunks = chunker.chunk("list.md", source)
    assert [c.text for c in chunks] == [listing, following]
    assert [c.context.section_type for c in chunks] == ["list", "paragraph"]
    assert [c.text for c in chunker.stream("list.md", source)] == [c.text for c in chunks]
    for c in chunks:
        assert source.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text
        assert len(c.contextualized_text) <= 500


def test_loose_continuation_paragraph_can_itself_continue_lazily():
    source = "- First item\n\n  Additional paragraph.\nLazy continuation.\n- Second item\n"
    _, nodes = parse_markdown(source)
    assert len(nodes) == 1 and nodes[0].kind == EntityType.LIST
    assert nodes[0].text == source


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("marker", ["- ", "1. "])
@pytest.mark.parametrize("fence", ["```", "~~~"])
@pytest.mark.parametrize("policy", ["preserve", "pack"])
def test_list_continuation_keeps_ownership_after_nested_fence(newline, marker, fence, policy):
    indent = " " * len(marker)
    source = (
        f"{marker}First item 😀\n\n{indent}{fence}text\n"
        f"{indent}Example\n{indent}{fence}\n\n"
        f"{indent}More detail.\n\n{marker}Second item\n"
    ).replace("\n", newline)
    _, nodes = parse_markdown(source)
    assert [n.kind for n in nodes] == [EntityType.LIST, EntityType.CODE_BLOCK, EntityType.LIST]
    assert "More detail." in nodes[-1].text and "Second item" in nodes[-1].text
    chunker = Chunker(
        max_chunk_size=500,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        markdown_paragraph_policy=policy,
    )
    chunks = chunker.chunk("list.md", source)
    assert "".join(c.text for c in chunks) == source
    detail = next(c for c in chunks if "More detail." in c.text)
    assert detail.context.section_type == "list" and "Second item" in detail.text
    raw = source.encode()
    for c in chunks:
        assert raw[c.byte_range.start : c.byte_range.end].decode() == c.text
        assert len(c.contextualized_text) <= 500
    assert [c.text for c in chunker.stream("list.md", source)] == [c.text for c in chunks]


@pytest.mark.parametrize(
    "interruption",
    [
        "```text\nExample\n```\n\n  More detail.\n",
        "  ```text\n  Example\n  ```\nMore detail.\n",
        "  ```text\n  Example\n  ```\n# Outside\n\n  More detail.\n",
    ],
)
def test_list_context_does_not_leak_past_independent_blocks(interruption):
    _, nodes = parse_markdown("- First item\n\n" + interruption + "\n- Second item\n")
    detail = next(n for n in nodes if "More detail." in n.text)
    assert detail.kind == EntityType.PARAGRAPH
    assert nodes[-1].kind == EntityType.LIST


def test_list_context_survives_consecutive_nested_fences():
    source = "- Item\n\n  ```\n  First\n  ```\n\n  ~~~\n  Second\n  ~~~\n\n  Detail\n"
    _, nodes = parse_markdown(source)
    assert [n.kind for n in nodes] == [
        EntityType.LIST,
        EntityType.CODE_BLOCK,
        EntityType.CODE_BLOCK,
        EntityType.LIST,
    ]


@pytest.mark.parametrize(
    "interruption,kind",
    [
        ("# Heading\n\nBody.\n", EntityType.HEADING),
        ("```text\nFenced content.\n```\n", EntityType.CODE_BLOCK),
        ("| A | B |\n| --- | --- |\n| x | y |\n", EntityType.TABLE),
        ("> Separate quote.\n", EntityType.PARAGRAPH),
        ("---\n", EntityType.PARAGRAPH),
    ],
)
def test_independent_block_interrupts_tight_list(interruption, kind):
    source = "- First item\nLazy continuation.\n" + interruption
    _, nodes = parse_markdown(source)
    assert nodes[0].kind == EntityType.LIST
    assert nodes[0].text == "- First item\nLazy continuation.\n"
    assert nodes[1].kind == kind


@pytest.mark.parametrize("policy", ["preserve", "pack"])
def test_tight_list_fragments_keep_utf8_source_budget_heading_and_stream_parity(policy):
    source = (
        "# Rehber\r\n\r\n- İlk madde 😀.\r\n"
        + ("İşlemi doğrulayın. " * 15)
        + "\r\n- Son madde.\r\n"
    )

    def count(text):
        return len(text.encode()) + 2 + (11 if "😀" in text and "doğrulayın" in text else 0)

    chunker = Chunker(
        max_chunk_size=80,
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
    for c in chunks:
        assert source.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text
        assert count(c.contextualized_text) <= 80
    assert [c.text for c in chunker.stream("rehber.md", source)] == [c.text for c in chunks]
