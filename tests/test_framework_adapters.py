"""Native framework contracts, including actual ingestion cache behavior."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from omnichunk.integrations._common import split_source

OPTIONS = {
    "max_chunk_size": 48,
    "min_chunk_size": 0,
    "context_mode": "none",
    "coverage_policy": "lossless",
}
TEXT = "İlk açıklama burada.\n\n" + "資料は元の範囲を保持する。" * 5


def langchain_types():
    pytest.importorskip("langchain_text_splitters")
    from langchain_core.documents import Document

    from omnichunk.integrations.langchain import OmniChunkTextSplitter

    return Document, OmniChunkTextSplitter


def llama_types():
    pytest.importorskip("llama_index.core")
    from llama_index.core.schema import Document

    from omnichunk.integrations.llamaindex import OmniChunkNodeParser

    return Document, OmniChunkNodeParser


def test_langchain_native_identity_metadata_source_and_async():
    Document, Splitter = langchain_types()
    metadata = {
        "acl": {"readers": ["alice"]},
        "source_id": "logical-source",
        "filepath": "guide.md",
    }
    original = deepcopy(metadata)
    source = Document(id="native-source", page_content=TEXT, metadata=metadata)
    splitter = Splitter(options=OPTIONS)
    chunks = splitter.split_documents([source])
    assert "".join(chunk.page_content for chunk in chunks) == TEXT
    assert [c.id for c in chunks] == [c.id for c in splitter.split_documents([source])]
    assert list(splitter.transform_documents([source])) == chunks
    assert list(asyncio.run(splitter.atransform_documents([source]))) == chunks
    for chunk in chunks:
        snapshot = chunk.metadata["omnichunk"]["chunk"]
        assert snapshot["source"]["source_id"] == "logical-source"
        span = snapshot["byte_range"]
        assert TEXT.encode()[span["start"] : span["end"]].decode() == chunk.page_content
        assert chunk.metadata["acl"] == original["acl"]
    chunks[0].metadata["acl"]["readers"].append("bob")
    assert source.metadata == original
    assert chunks[1].metadata["acl"] == original["acl"]
    with pytest.raises(ValueError, match="already be chunked"):
        splitter.split_documents(chunks)


def test_langchain_text_api_metadata_validation_and_context_once():
    Document, Splitter = langchain_types()
    splitter = Splitter(
        options={"max_chunk_size": 200, "context_mode": "full"}, use_contextualized_text=True
    )
    chunks = splitter.create_documents(["hello", "second"], [{"source": "a"}, {"source": "b"}])
    assert chunks[0].metadata["omnichunk"]["chunk"]["source"]["source_id"] == "a"
    assert chunks[0].page_content == chunks[0].metadata["omnichunk"]["chunk"]["contextualized_text"]
    assert splitter.split_text("hello") == [chunks[0].page_content]
    assert chunks[0].id != chunks[1].id
    with pytest.raises(ValueError, match="equal lengths"):
        splitter.create_documents(["one"], [])
    empty = Splitter(options=OPTIONS).create_documents([])
    assert empty == []
    assert Splitter(options=OPTIONS).split_documents([Document(page_content="")]) == []


@pytest.mark.parametrize("kind", ["langchain", "llamaindex"])
def test_native_hierarchy_ids_links_and_source_ranges(kind):
    if kind == "langchain":
        Document, Splitter = langchain_types()
        nodes = Splitter(options=OPTIONS, levels=[32, 96]).split_documents(
            [Document(id="source", page_content=TEXT, metadata={"acl": ["group"]})]
        )
    else:
        Document, Parser = llama_types()
        nodes = Parser(options=OPTIONS, levels=[32, 96])(
            [Document(id_="source", text=TEXT, metadata={"acl": ["group"]})]
        )
    ids = {node.id if kind == "langchain" else node.node_id for node in nodes}
    assert len(ids) == len(nodes)
    assert {node.metadata["omnichunk"]["level"] for node in nodes} == {0, 1}
    for node in nodes:
        metadata = node.metadata["omnichunk"]
        assert metadata["parent_id"] is None or metadata["parent_id"] in ids
        assert set(metadata["child_ids"]) <= ids
        if kind == "llamaindex":
            from llama_index.core.schema import NodeRelationship

            assert node.ref_doc_id == "source"
            if metadata["parent_id"]:
                assert node.parent_node.node_id == metadata["parent_id"]
            if metadata["child_ids"]:
                assert [n.node_id for n in node.child_nodes] == metadata["child_ids"]
            for direction in [NodeRelationship.PREVIOUS, NodeRelationship.NEXT]:
                adjacent = node.relationships.get(direction)
                if adjacent:
                    assert adjacent.node_id.endswith(f":level:{metadata['level']}")


def test_llama_exact_offsets_metadata_rendering_and_async():
    Document, Parser = llama_types()
    from llama_index.core.schema import MetadataMode

    parser = Parser(options=OPTIONS)
    source = Document(id_="native", text=TEXT, metadata={"acl": ["reader"], "source_id": "logical"})
    nodes = parser.get_nodes_from_documents([source])
    assert [n.to_dict() for n in asyncio.run(parser.acall([source]))] == [
        n.to_dict() for n in nodes
    ]
    assert [n.text for n in nodes] == [n.text for n in parser([source])]
    assert "".join(n.text for n in nodes) == TEXT
    for i, node in enumerate(nodes):
        assert TEXT[node.start_char_idx : node.end_char_idx] == node.text
        assert node.ref_doc_id == "native"
        assert node.metadata["acl"] == ["reader"]
        assert node.get_content(metadata_mode=MetadataMode.EMBED) == node.text
        assert node.get_content(metadata_mode=MetadataMode.LLM) == node.text
        if i:
            assert node.prev_node.node_id == nodes[i - 1].node_id
        if i + 1 < len(nodes):
            assert node.next_node.node_id == nodes[i + 1].node_id
    nodes[0].source_node.metadata["acl"].append("other")
    assert source.metadata["acl"] == ["reader"]
    assert nodes[1].source_node.metadata["acl"] == ["reader"]
    with pytest.raises(ValueError, match="already be chunked"):
        parser(nodes)


def test_llama_context_not_duplicated_and_optional_links_metadata():
    Document, Parser = llama_types()
    from llama_index.core.schema import MetadataMode

    parser = Parser(
        options={"max_chunk_size": 500},
        use_contextualized_text=True,
        include_metadata=False,
        include_prev_next_rel=False,
    )
    nodes = parser([Document(id_="source", text="Hello world", metadata={"private": "kept out"})])
    assert set(nodes[0].metadata) == {"omnichunk"}
    assert nodes[0].get_content(metadata_mode=MetadataMode.EMBED) == nodes[0].text
    assert nodes[0].text == nodes[0].metadata["omnichunk"]["chunk"]["contextualized_text"]
    assert nodes[0].prev_node is None and nodes[0].next_node is None


def test_llama_native_ingestion_cache_and_serialization():
    Document, Parser = llama_types()
    from llama_index.core.ingestion import IngestionCache, IngestionPipeline

    parser = Parser(options=OPTIONS)
    restored = Parser.from_dict(parser.to_dict())
    assert restored.options == parser.options
    assert restored.class_name() == "OmniChunkNodeParser"
    cache = IngestionCache()
    pipeline = IngestionPipeline(transformations=[parser], cache=cache)
    document = Document(id_="source", text=TEXT, metadata={"acl": ["reader"]})
    first = pipeline.run(documents=[document])
    second = pipeline.run(documents=[document])
    assert [n.to_dict() for n in first] == [n.to_dict() for n in second]
    changed = IngestionPipeline(
        transformations=[Parser(options={**OPTIONS, "max_chunk_size": 96})], cache=cache
    )
    assert len(changed.run(documents=[document])) < len(first)
    # ACL changes must invalidate cached output even when source text is equal.
    document.metadata["acl"] = ["other"]
    assert all(n.metadata["acl"] == ["other"] for n in pipeline.run(documents=[document]))
    with pytest.raises(ValueError, match="JSON serializable"):
        Parser(options={"tokenizer": len})
    with pytest.raises(ValueError, match="JSON serializable"):
        Parser(options={"max_chunk_size": float("nan")})
    with pytest.raises(ValueError, match="stable node IDs"):
        Parser(id_func=lambda *_: "custom")
    parser.options["tokenizer"] = len
    with pytest.raises(ValueError, match="JSON serializable"):
        parser.to_dict()


@pytest.mark.parametrize(
    "metadata,options,message",
    [
        ({"omnichunk": {}}, {}, "Reserved"),
        ({"source_id": ["bad"]}, {}, "identity"),
        ({"filepath": 2}, {}, "filepath"),
        ({}, {"source_id": "shared"}, "each document"),
    ],
)
def test_shared_metadata_validation(metadata, options, message):
    with pytest.raises(ValueError, match=message):
        split_source("text", metadata, None, options=options, filepath="doc.txt", levels=None)


def test_shared_inline_identity_is_deterministic_and_path_can_supply_identity():
    def split(text, metadata):
        return split_source(text, metadata, None, options=OPTIONS, filepath="doc.txt", levels=None)

    first = split("text", {})[0]
    assert first.node_id == split("text", {})[0].node_id
    assert first.chunk.source.source_id.startswith("inline:")
    assert split("text", {"filepath": "guide.txt"})[0].chunk.source.source_id == "guide.txt"
