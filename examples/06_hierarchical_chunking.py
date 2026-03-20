"""
Hierarchical ChunkTree: leaves for indexing, roots for LLM context, levels, parent/child, invariant.
"""

from __future__ import annotations

import sys
from pathlib import Path

repo_src = Path(__file__).resolve().parents[1] / "src"
if repo_src.exists():
    sys.path.insert(0, str(repo_src))

from omnichunk import Chunker


def main() -> None:
    src = '''\
def outer():
    def inner():
        return 42
    return inner()

class Box:
    value = 1
'''
    chunker = Chunker(size_unit="chars", min_chunk_size=8)
    tree = chunker.hierarchical_chunk("mod.py", src, levels=[64, 256, 1024])

    print(f"level_count={tree.level_count}")
    leaves = tree.leaves()
    roots = tree.roots()
    print(f"leaves={len(leaves)} roots={len(roots)}")

    if tree.level_count > 1:
        mid = tree.at_level(1)
        print(f"at_level(1): {len(mid)} chunks")

    if roots:
        r0 = roots[0]
        print(f"first root byte_range: {r0.byte_range}")
        kids = tree.children(r0)
        print(f"  children of first root: {len(kids)}")
        if leaves:
            p = tree.parent(leaves[0])
            print(f"parent(leaves[0]) is None? {p is None}")

    for node in tree.nodes:
        if node.level == 0:
            continue
        chs = tree.children(node.chunk)
        if not chs:
            continue
        assert node.chunk.byte_range.start == chs[0].byte_range.start
        assert node.chunk.byte_range.end == chs[-1].byte_range.end
    print("invariant OK: each parent byte_range spans exactly its children")

    d = tree.to_dict()
    print(f"to_dict: level_count={d['level_count']} nodes={len(d['nodes'])}")


if __name__ == "__main__":
    main()
