from __future__ import annotations

import pytest

from omnichunk import Chunker


def test_hierarchical_chunk_levels_validated() -> None:
    chunker = Chunker()
    with pytest.raises(ValueError):
        chunker.hierarchical_chunk("f.py", "x", levels=[64])
    with pytest.raises(ValueError):
        chunker.hierarchical_chunk("f.py", "x", levels=[256, 64])


def test_hierarchical_chunk_leaf_reconstruction() -> None:
    code = "def foo():\n    return 1\n" * 20
    chunker = Chunker()
    tree = chunker.hierarchical_chunk("m.py", code, levels=[32, 128, 512], size_unit="chars")
    leaves = tree.leaves()
    assert leaves
    assert "".join(c.text for c in leaves) == code
    raw = code.encode("utf-8")
    for c in leaves:
        assert raw[c.byte_range.start : c.byte_range.end].decode("utf-8") == c.text
    for left, right in zip(leaves, leaves[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_hierarchical_chunk_parent_spans_children() -> None:
    code = "def f():\n    pass\n" * 30
    chunker = Chunker()
    tree = chunker.hierarchical_chunk("m.py", code, levels=[24, 96], size_unit="chars")
    for node in tree.nodes:
        if node.level > 0:
            children = tree.children(node.chunk)
            if children:
                assert node.chunk.byte_range.start == children[0].byte_range.start
                assert node.chunk.byte_range.end == children[-1].byte_range.end


def test_hierarchical_chunk_level_count() -> None:
    text = "Hello world. " * 50
    chunker = Chunker()
    tree = chunker.hierarchical_chunk("doc.md", text, levels=[16, 64, 256], size_unit="chars")
    assert tree.level_count == 3


def test_hierarchical_chunk_at_level_returns_sorted() -> None:
    text = "Para one.\n\n" * 40
    chunker = Chunker()
    tree = chunker.hierarchical_chunk("doc.md", text, levels=[20, 80], size_unit="chars")
    for level in range(tree.level_count):
        chunks = tree.at_level(level)
        for left, right in zip(chunks, chunks[1:]):
            assert left.byte_range.start < right.byte_range.start


def test_hierarchical_chunk_two_levels_tree_structure() -> None:
    text = "Sentence one. " * 60
    chunker = Chunker()
    tree = chunker.hierarchical_chunk("doc.md", text, levels=[20, 80], size_unit="chars")
    leaves = tree.leaves()
    roots = tree.roots()
    assert len(roots) <= len(leaves)
    for root in roots:
        children = tree.children(root)
        assert children


def test_hierarchical_chunk_to_dict_round_trip() -> None:
    code = "def a():\n    pass\n" * 10
    chunker = Chunker()
    tree = chunker.hierarchical_chunk("m.py", code, levels=[24, 96], size_unit="chars")
    d = tree.to_dict()
    assert d["level_count"] == 2
    assert len(d["nodes"]) == len(tree.nodes)


def test_hierarchical_chunk_deterministic() -> None:
    code = "def f(x):\n    return x\n" * 15
    chunker = Chunker()
    t1 = chunker.hierarchical_chunk("m.py", code, levels=[32, 128], size_unit="chars")
    t2 = chunker.hierarchical_chunk("m.py", code, levels=[32, 128], size_unit="chars")
    assert [n.chunk.text for n in t1.nodes] == [n.chunk.text for n in t2.nodes]
    assert [n.level for n in t1.nodes] == [n.level for n in t2.nodes]


def test_hierarchical_chunk_empty_content() -> None:
    chunker = Chunker()
    tree = chunker.hierarchical_chunk("m.py", "", levels=[32, 128], size_unit="chars")
    assert tree.leaves() == []
