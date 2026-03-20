"""
Code chunking: Python + TypeScript samples, overlap and context_mode,
and byte-range reconstruction checks.
"""

from __future__ import annotations

from omnichunk import Chunker


def main() -> None:
    py_src = '''\
class Greeter:
    """Doc."""

    def hello(self, name: str) -> str:
        return f"hi {name}"

    def bye(self) -> None:
        pass
'''

    ts_src = '''\
interface User { id: number; name: string; }

export function greet(u: User): string {
  return `Hello ${u.name}`;
}
'''

    chunker = Chunker(
        max_chunk_size=120,
        size_unit="chars",
        overlap=20,
        overlap_lines=0,
        context_mode="full",
        sibling_detail="names",
    )
    py_chunks = chunker.chunk("sample.py", py_src)
    print(f"Python chunks: {len(py_chunks)}")
    raw_py = py_src.encode("utf-8")
    for c in py_chunks:
        sl = raw_py[c.byte_range.start : c.byte_range.end]
        assert sl.decode("utf-8") == c.text, "reconstruction failed"
        ents = [e.type.value for e in c.context.entities]
        print(f"  idx={c.index} entities={ents} breadcrumb={c.context.breadcrumb}")
        if c.context.siblings:
            print(f"    siblings: {[s.name for s in c.context.siblings]}")

    chunker_min = Chunker(
        max_chunk_size=120,
        size_unit="chars",
        context_mode="minimal",
    )
    py_min = chunker_min.chunk("sample.py", py_src)
    print(f"Python chunks (minimal context): {len(py_min)}")
    print("  first contextualized length:", len(py_min[0].contextualized_text) if py_min else 0)

    ts_chunks = chunker.chunk("sample.ts", ts_src)
    print(f"TypeScript chunks: {len(ts_chunks)}")
    raw_ts = ts_src.encode("utf-8")
    for c in ts_chunks:
        assert raw_ts[c.byte_range.start : c.byte_range.end].decode("utf-8") == c.text


if __name__ == "__main__":
    main()
