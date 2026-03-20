from __future__ import annotations

from omnichunk import Chunker, chunks_to_pinecone_vectors, stable_chunk_id


def test_chunk_diff_no_change() -> None:
    code = "def foo():\n    return 1\n" * 10
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks_v1 = chunker.chunk("m.py", code)
    diff = chunker.chunk_diff("m.py", code, previous_chunks=chunks_v1)
    assert diff.total_added == 0
    assert diff.total_removed == 0
    assert diff.total_unchanged == len(chunks_v1)


def test_chunk_diff_append_only() -> None:
    # Plaintext + max_chunk_size == len(base) keeps v1 as one chunk; v2 splits
    # into [0:len(base)] + tail so the prefix chunk ID matches (no removals).
    base = ("hello world\n") * 10
    new = base + ("goodbye\n") * 5
    chunker = Chunker(max_chunk_size=120, size_unit="chars", min_chunk_size=1)
    chunks_v1 = chunker.chunk("m.txt", base)
    diff = chunker.chunk_diff("m.txt", new, previous_chunks=chunks_v1)
    assert diff.total_added > 0
    assert diff.total_removed == 0


def test_chunk_diff_delete_section() -> None:
    full = "def foo():\n    return 1\n" * 10 + "def bar():\n    return 2\n" * 10
    trimmed = "def foo():\n    return 1\n" * 10
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks_full = chunker.chunk("m.py", full)
    diff = chunker.chunk_diff("m.py", trimmed, previous_chunks=chunks_full)
    assert diff.total_removed > 0


def test_chunk_diff_removed_ids_are_strings() -> None:
    code = "def f():\n    pass\n" * 8
    new_code = "def g():\n    pass\n" * 8
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    old_chunks = chunker.chunk("m.py", code)
    diff = chunker.chunk_diff("m.py", new_code, previous_chunks=old_chunks)
    for rid in diff.removed_ids:
        assert isinstance(rid, str)
        assert len(rid) == 64


def test_chunk_diff_empty_previous() -> None:
    code = "def f():\n    pass\n" * 5
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    diff = chunker.chunk_diff("m.py", code, previous_chunks=[])
    new_chunks = chunker.chunk("m.py", code)
    assert diff.total_added == len(new_chunks)
    assert diff.total_unchanged == 0
    assert diff.total_removed == 0


def test_chunk_diff_empty_new_content() -> None:
    code = "def f():\n    pass\n" * 5
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    old_chunks = chunker.chunk("m.py", code)
    diff = chunker.chunk_diff("m.py", "", previous_chunks=old_chunks)
    assert diff.total_removed == len(old_chunks)
    assert diff.total_added == 0


def test_stable_chunk_id_deterministic() -> None:
    code = "def f():\n    pass\n"
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    ids1 = [stable_chunk_id(c) for c in chunks]
    ids2 = [stable_chunk_id(c) for c in chunks]
    assert ids1 == ids2


def test_chunk_diff_consistent_with_pinecone_ids() -> None:
    code = "def f():\n    pass\n" * 5
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    embeddings = [[0.0] * 4 for _ in chunks]
    vecs = chunks_to_pinecone_vectors(chunks, embeddings)
    pinecone_ids = [v["id"] for v in vecs]
    stable_ids = [stable_chunk_id(c) for c in chunks]
    assert pinecone_ids == stable_ids
