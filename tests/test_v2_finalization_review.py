"""Adversarial review of the shared v2 contracts through observable behavior."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from omnichunk import Chunker
from omnichunk.config import configuration_fingerprint
from omnichunk.finalize import finalize_chunks
from omnichunk.plugins import PluginRegistry
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkOptions,
    EntityInfo,
    EntityType,
    LineRange,
)


def candidate(text: str, *, context: ChunkContext | None = None, start: int = 0) -> Chunk:
    return Chunk(
        text,
        text,
        ByteRange(start, start + len(text.encode())),
        LineRange(0, 0),
        0,
        1,
        context or ChunkContext(filepath="review.txt"),
    )


def test_oversized_candidate_keeps_overlap_on_every_subdivision() -> None:
    text = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    options = ChunkOptions(
        max_chunk_size=10,
        min_chunk_size=0,
        overlap=2,
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = list(finalize_chunks("review.txt", text, [candidate(text)], options))
    assert len(chunks) > 2
    assert all(len(chunk.text) <= 10 for chunk in chunks)
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end - right.byte_range.start == 2
        assert left.text[-2:] == right.text[:2]


def test_lossless_unicode_split_and_overlap_covers_every_byte() -> None:
    text = "başlık\r\n😀中e\u0301\u2003\n\n" * 8
    chunker = Chunker(
        max_chunk_size=9,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        overlap=2,
    )
    chunks = chunker.chunk("unicode.txt", text)
    raw = text.encode()
    covered = set()
    for chunk in chunks:
        assert raw[chunk.byte_range.start : chunk.byte_range.end].decode() == chunk.text
        assert len(chunk.text) <= 9
        covered.update(range(chunk.byte_range.start, chunk.byte_range.end))
    assert covered == set(range(len(raw)))
    assert chunker.chunk_with_manifest("unicode.txt", text).skipped_ranges == ()


def test_existing_partial_entity_marker_survives_finalization() -> None:
    text = "def part():\n  pass\n"
    entity = EntityInfo(
        name="part",
        type=EntityType.FUNCTION,
        byte_range=ByteRange(0, len(text.encode())),
        is_partial=True,
    )
    context = ChunkContext(filepath="review.py", entities=[entity])
    options = ChunkOptions(max_chunk_size=100, min_chunk_size=0, context_mode="none")
    chunks = list(finalize_chunks("review.py", text, [candidate(text, context=context)], options))
    assert chunks[0].context.entities[0].is_partial is True


def test_split_entity_references_stay_source_based_and_partial() -> None:
    text = "def function():\n" + "    statement = 1\n" * 6
    entity = EntityInfo(
        name="function", type=EntityType.FUNCTION, byte_range=ByteRange(0, len(text.encode()))
    )
    context = ChunkContext(filepath="review.py", entities=[entity])
    options = ChunkOptions(max_chunk_size=30, min_chunk_size=0, context_mode="none")
    chunks = list(finalize_chunks("review.py", text, [candidate(text, context=context)], options))
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.context.entities[0].byte_range == entity.byte_range
        assert chunk.context.entities[0].is_partial


def test_lossless_file_preserves_crlf_bytes(tmp_path: Path) -> None:
    raw = b"first line\r\n\r\nsecond line\r\n"
    path = tmp_path / "source.txt"
    path.write_bytes(raw)
    chunker = Chunker(context_mode="none", coverage_policy="lossless")
    assert b"".join(chunk.text.encode() for chunk in chunker.chunk_file(str(path))) == raw
    assert b"".join(chunk.text.encode() for chunk in chunker.stream_file(str(path))) == raw


def test_registry_iterator_close_releases_retained_upstream() -> None:
    closed = []

    def upstream():
        try:
            yield 1
            yield 2
        finally:
            closed.append(True)

    retained = upstream()
    iterator = PluginRegistry().iterate(retained)
    assert next(iterator) == 1
    iterator.close()
    try:
        assert closed == [True]
    finally:
        retained.close()


def test_public_stream_close_releases_retained_engine(monkeypatch) -> None:
    from omnichunk.types import ContentType

    closed = []
    text = "first second"

    def upstream():
        try:
            yield candidate("first ")
            yield candidate("second", start=6)
        finally:
            closed.append(True)

    retained = upstream()
    monkeypatch.setattr(
        "omnichunk.chunker.route_content_stream", lambda *args: (ContentType.PROSE, retained)
    )
    stream = Chunker(context_mode="none").stream("review.txt", text)
    assert next(stream).text == "first "
    stream.close()
    try:
        assert closed == [True]
    finally:
        retained.close()


def test_tokenizer_provider_fingerprint_distinguishes_model_configuration() -> None:
    class Encoder:
        def __init__(self, name: str, tokens_per_character: int):
            self.name = name
            self.tokens_per_character = tokens_per_character

        def encode(self, text: str, **kwargs):
            return [1] * len(text) * self.tokens_per_character

    small = Chunker(size_unit="tokens", tokenizer=Encoder("model-a", 1))
    large = Chunker(size_unit="tokens", tokenizer=Encoder("model-b", 2))
    assert small.config_fingerprint() != large.config_fingerprint()


def test_plugin_registry_revision_participates_in_fingerprint() -> None:
    registry = PluginRegistry(revision="parser-v1")
    chunker = Chunker(registry=registry)
    first = chunker.config_fingerprint()
    registry.revision = "parser-v2"
    assert chunker.config_fingerprint() != first


def test_embedding_cache_capacity_override_is_effective() -> None:
    def embed(texts):
        return np.ones((len(texts), 2))

    chunker = Chunker(semantic_embed_cache_size=100)
    chunker.semantic_chunk("review.txt", "Alpha. Bravo. Charlie. Delta.", embed_fn=embed)
    assert chunker.semantic_cache_stats()["size"] > 1
    chunker.semantic_chunk(
        "review.txt", "Alpha. Bravo. Charlie. Delta.", embed_fn=embed, semantic_embed_cache_size=1
    )
    assert chunker.semantic_cache_stats()["size"] <= 1


@pytest.mark.parametrize(
    "options",
    [
        {"include_imports": "false"},
        {"filter_imports": "false"},
        {"include_notebook_outputs": "false"},
        {"semantic_threshold": True},
        {"semantic_cache_namespace": []},
        {"semantic_model_revision": {}},
        {"semantic_preprocessing": []},
        {"source_id": []},
    ],
)
def test_invalid_option_types_rejected_before_processing(options: dict) -> None:
    with pytest.raises((TypeError, ValueError)):
        Chunker(**options)


def test_context_only_overlap_is_not_silently_ignored() -> None:
    with pytest.raises(ValueError, match="overlap"):
        Chunker(context_mode="none", overlap_lines=1)


def test_explicit_provider_revision_changes_fingerprint() -> None:
    options = ChunkOptions(semantic_model_revision="v1")
    assert configuration_fingerprint(options) != configuration_fingerprint(
        replace(options, semantic_model_revision="v2")
    )


def test_minimal_import_and_plain_chunking_without_optional_stacks() -> None:
    program = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        optional = {'numpy', 'scipy', 'tree_sitter', 'tiktoken', 'transformers'}
        if fullname.split('.')[0] in optional or fullname.startswith('tree_sitter_'):
            raise ModuleNotFoundError(fullname, name=fullname.split('.')[0])
sys.meta_path.insert(0, BlockOptional())
from omnichunk import Chunker
chunker = Chunker(context_mode='none', coverage_policy='lossless')
chunks = chunker.chunk('document.txt', 'Hello source.\\n')
assert ''.join(chunk.text for chunk in chunks) == 'Hello source.\\n'
"""
    completed = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_async_consumer_close_stops_producer_and_cleans_up(monkeypatch) -> None:
    closed = []

    def stream(self, filepath, content, **options):
        try:
            for _ in range(1000):
                yield candidate("source")
        finally:
            closed.append(True)

    monkeypatch.setattr(Chunker, "stream", stream)

    async def consume():
        result = Chunker().astream("review.txt", "source", buffer_size=1)
        await anext(result)
        await asyncio.wait_for(result.aclose(), timeout=2)

    asyncio.run(consume())
    assert closed == [True]


def test_public_semantic_splitter_uses_final_payload_contract_without_internal_options() -> None:
    from omnichunk.semantic import SemanticSplitter

    splitter = SemanticSplitter(embed_fn=lambda texts: np.ones((len(texts), 2)), window=1)
    options = ChunkOptions(
        max_chunk_size=8,
        min_chunk_size=0,
        coverage_policy="lossless",
        context_mode="none",
        overlap=2,
    )
    text = "First sentence. Second sentence."
    chunks = splitter.split("document.txt", text, options)
    assert chunks
    assert all(chunk.source is not None and chunk.config_fingerprint for chunk in chunks)
    assert all(chunk.metadata["budget"]["size"] <= 8 for chunk in chunks)
    assert all(chunk.total_chunks == len(chunks) for chunk in chunks)


def test_public_semantic_splitter_lossless_whitespace_without_embeddings() -> None:
    from omnichunk.semantic import SemanticSplitter

    def unnecessary_embed(texts):
        raise AssertionError("Whitespace should not require embeddings")

    chunks = SemanticSplitter(unnecessary_embed).split(
        "document.txt", " \n\t", ChunkOptions(coverage_policy="lossless", context_mode="none")
    )
    assert "".join(chunk.text for chunk in chunks) == " \n\t"


def test_nonmonotonic_tokenizer_can_fit_complete_multichar_tokens() -> None:
    # A subword tokenizer may count more tokens in a partial word than the
    # complete word: count(prefix) is not guaranteed to be monotonic.
    def count(text):
        return 1 if text in {"ab", "cd", "ef"} else len(text) * 2

    options = ChunkOptions(
        max_chunk_size=1,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    )
    text = "abcdef"
    chunks = list(finalize_chunks("review.txt", text, [candidate(text)], options))
    assert "".join(chunk.text for chunk in chunks) == text
    assert all(count(chunk.text) <= 1 for chunk in chunks)


def test_boundary_preference_is_remeasured_for_nonmonotonic_tokenizer() -> None:
    def count(text):
        if text == "ab\ncd":
            return 1
        if text == "ab\n":
            return 6
        return len(text)

    options = ChunkOptions(
        max_chunk_size=5,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    )
    text = "ab\ncdefghi"
    chunks = list(finalize_chunks("review.txt", text, [candidate(text)], options))
    assert "".join(chunk.text for chunk in chunks) == text
    assert all(count(chunk.text) <= 5 for chunk in chunks)


def test_hierarchical_tokenizer_override_is_forwarded() -> None:
    chunker = Chunker(context_mode="none")
    result = chunker.hierarchical_chunk(
        "document.txt",
        "alpha beta gamma delta epsilon",
        levels=[4, 8],
        size_unit="tokens",
        tokenizer=lambda text: len(text),
    )
    assert result.nodes
    assert all(node.chunk.token_count <= [4, 8][node.level] for node in result.nodes)


def test_hierarchical_chunking_uses_instance_parser_registry() -> None:
    calls = []
    registry = PluginRegistry(revision="custom-parser")

    def parser(filepath, content):
        calls.append(filepath)
        return None

    registry.register_parser("python", parser)
    chunker = Chunker(registry=registry, context_mode="none")
    chunker.hierarchical_chunk("document.py", "def function():\n    return 1\n", levels=[10, 40])
    assert calls


@pytest.mark.parametrize("which", ["parser", "formatter"])
def test_global_compatibility_registry_rejects_invalid_providers(monkeypatch, which) -> None:
    import omnichunk.plugins as plugins

    monkeypatch.setattr(plugins, "_PARSER_REGISTRY", {})
    monkeypatch.setattr(plugins, "_FORMATTER_REGISTRY", {})
    register = plugins.register_parser if which == "parser" else plugins.register_formatter
    with pytest.raises(ValueError, match="callable"):
        register("review", None)


@pytest.mark.parametrize(
    "options",
    [
        {"source_id": "  "},
        {"tokenizer": object()},
        {"tokenizer": " "},
        {"semantic_embed_fn": "model"},
        {"language": "unsupported"},
        {"content_type": "prose"},
        {"overlap": float("nan")},
        {"overlap": True},
        {"max_chunk_size": 10, "min_chunk_size": 0, "overlap": 10},
        {"overlap": 2, "overlap_lines": 1},
        {"preserve_decorators": False},
        {"preserve_comments": False},
        {"include_header_in_sections": False},
        {"semantic": True},
        {"semantic_sentence_splitter": []},
        {"semantic_threshold": 1.1},
        {"algorithm_version": "unknown"},
    ],
)
def test_invalid_configuration_fails_at_construction(options) -> None:
    with pytest.raises((ValueError, TypeError)):
        Chunker(**options)


def test_provider_identity_tracks_nested_configuration_without_runtime_objects() -> None:
    from enum import Enum

    class Mode(Enum):
        STRICT = "strict"

    class Counter:
        def __init__(self, options):
            self.options = options
            self.runtime = object()
            self.invalid_dictionary = {1: "opaque"}
            self.invalid_list = [object()]
            self.cycle = []
            self.cycle.append(self.cycle)
            self._session_id = object()

        def __call__(self, text):
            return len(text)

    first = Counter({"weights": (1, 0.5), "mode": Mode.STRICT, "limit": float("inf")})
    equivalent = Counter({"limit": float("inf"), "mode": Mode.STRICT, "weights": [1, 0.5]})
    options = ChunkOptions(size_unit="tokens", tokenizer=first)
    original = configuration_fingerprint(options)
    assert original == configuration_fingerprint(replace(options, tokenizer=equivalent))
    first.options["weights"] = (1, 0.75)
    assert original != configuration_fingerprint(options)


def test_explicit_provider_fingerprint_excludes_transient_state_but_tracks_revision() -> None:
    class Counter:
        fingerprint = "model:revision-1"

        def __init__(self):
            self.calls = 0

        def __call__(self, text):
            self.calls += 1
            return len(text)

    counter = Counter()
    chunker = Chunker(size_unit="tokens", tokenizer=counter)
    initial = chunker.config_fingerprint()
    chunker.chunk("document.txt", "Alpha. Bravo.")
    assert counter.calls > 0
    assert initial == chunker.config_fingerprint()
    counter.fingerprint = "model:revision-2"
    assert initial != chunker.config_fingerprint()


def test_registry_formatter_scope_restores_after_failure_and_cleanup(monkeypatch) -> None:
    import omnichunk.plugins as plugins

    global_formatter = lambda chunks: "global"  # noqa: E731
    local_formatter = lambda chunks: "local"  # noqa: E731
    monkeypatch.setattr(plugins, "_FORMATTER_REGISTRY", {"review": global_formatter})
    registry = PluginRegistry()
    registry.register_formatter("  review  ", local_formatter)
    observations = []

    def failing_provider():
        try:
            observations.append(plugins.get_formatter("review"))
            yield "first"
            raise RuntimeError("provider failed")
        finally:
            observations.append(plugins.get_formatter("review"))

    scoped = registry.iterate(failing_provider())
    assert next(scoped) == "first"
    assert plugins.get_formatter("review") is global_formatter
    with pytest.raises(RuntimeError, match="provider failed"):
        next(scoped)
    assert observations == [local_formatter, local_formatter]
    assert plugins.get_formatter("review") is global_formatter


@pytest.mark.parametrize("which", ["parser", "formatter"])
def test_instance_registry_rejects_invalid_providers(which) -> None:
    registry = PluginRegistry()
    register = registry.register_parser if which == "parser" else registry.register_formatter
    with pytest.raises(ValueError, match="callable"):
        register("review", None)
    with pytest.raises(ValueError):
        register(" ", lambda *args: None)


def test_registry_fingerprint_tracks_formatter_and_explicit_revision() -> None:
    class Formatter:
        def __init__(self, prefix):
            self.prefix = prefix

        def __call__(self, chunks):
            return self.prefix

    first = PluginRegistry(revision="v1")
    second = PluginRegistry(revision="v1")
    first.register_formatter("custom", Formatter("same"))
    second.register_formatter("custom", Formatter("same"))
    assert first.fingerprint == second.fingerprint
    original = first.fingerprint
    first.register_formatter("custom", Formatter("changed"), overwrite=True)
    assert first.fingerprint != original
    second.revision = "v2"
    assert second.fingerprint != original


def test_store_reprocesses_opaque_encoder_objects_before_reusing_token_budgets(tmp_path) -> None:
    from omnichunk import ChunkStore

    class Encoder:
        def __init__(self, factor):
            self._factor = factor

        def encode(self, text, **kwargs):
            return [1] * (len(text) * self._factor)

    document = tmp_path / "source.txt"
    document.write_text("alpha beta gamma delta", encoding="utf-8")
    settings = dict(size_unit="tokens", max_chunk_size=12, min_chunk_size=0, context_mode="none")
    first = Chunker(tokenizer=Encoder(1), **settings)
    changed = Chunker(tokenizer=Encoder(2), **settings)
    # Private encoder state is intentionally not a durable provider identity.
    assert first.config_fingerprint() == changed.config_fingerprint()
    with ChunkStore(tmp_path / "index.sqlite") as store:
        store.index(tmp_path, glob="*.txt", chunker=first)
        result = store.sync(tmp_path, glob="*.txt", chunker=changed)
        assert result.files_skipped == 0
        assert result.files_updated == 1
        assert all(
            len(changed._defaults.tokenizer.encode(chunk.contextualized_text)) <= 12
            for chunk in store.query(str(document))
        )
