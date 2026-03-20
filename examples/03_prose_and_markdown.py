"""
Prose and Markdown: headings, fenced code delegation, plaintext, char vs token sizing.
"""

from __future__ import annotations

from omnichunk import Chunker


def main() -> None:
    md = """# Title

## Section A

Some prose here.

```python
def x():
    return 1
```

## Section B

| h1 | h2 |
|----|----|
| a  | b  |
"""

    plain = "First paragraph.\n\nSecond paragraph with more words.\n" * 5

    c_chars = Chunker(max_chunk_size=200, size_unit="chars", min_chunk_size=20)
    md_chunks = c_chars.chunk("doc.md", md)
    print(f"Markdown chunks (chars): {len(md_chunks)}")
    for c in md_chunks:
        print(
            f"  heading_hierarchy={c.context.heading_hierarchy!r} "
            f"section_type={c.context.section_type!r}"
        )

    c_tok = Chunker(max_chunk_size=64, size_unit="tokens", min_chunk_size=8)
    plain_chunks = c_tok.chunk("notes.txt", plain)
    print(f"Plaintext chunks (tokens): {len(plain_chunks)}")


if __name__ == "__main__":
    main()
