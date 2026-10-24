"""
TokenBudgetOptimizer: greedy vs DP, preserve_order, dedup, size units, simulated RAG retrieval.
"""

from __future__ import annotations

from omnichunk import Chunker
from omnichunk.budget import TokenBudgetOptimizer
from omnichunk.types import ByteRange, Chunk, ChunkContext, LineRange


def _synthetic_chunks(texts: list[str]) -> list[Chunk]:
    out: list[Chunk] = []
    cursor = 0
    for i, text in enumerate(texts):
        end = cursor + len(text.encode("utf-8"))
        out.append(
            Chunk(
                text=text,
                contextualized_text=text,
                byte_range=ByteRange(cursor, end),
                line_range=LineRange(i, i),
                index=i,
                total_chunks=len(texts),
                context=ChunkContext(filepath="rag.txt", language="plaintext"),
                token_count=len(text.split()),
                char_count=len(text),
                nws_count=sum(1 for c in text if not c.isspace()),
            )
        )
        cursor = end
    return out


def main() -> None:
    # The optimizer uses raw chunk counts. Omit added context so selected text
    # matches those counts, and reserve prompt/separator space separately.
    chunker = Chunker(max_chunk_size=80, size_unit="chars", context_mode="none")
    prose = "\n\n".join(f"Section {i}. " + "word " * 30 for i in range(10))
    chunks = chunker.chunk("retrieval.txt", prose)
    scores = [1.0 / (i + 1) for i in range(len(chunks))]

    for strategy in ("greedy", "dp"):
        opt = TokenBudgetOptimizer(budget=512, strategy=strategy, size_unit="chars")
        r = opt.select(chunks, scores=scores)
        assert r.total_tokens <= 512
        # The result field is named total_tokens for every size unit.
        print(
            f"{strategy}: selected={len(r.selected)} total_chars={r.total_tokens} "
            f"dropped={len(r.dropped)}"
        )

    r2 = TokenBudgetOptimizer(budget=200, preserve_order=False, size_unit="chars").select(
        chunks, scores=scores
    )
    print(
        "preserve_order=False: first selected byte_start="
        f"{r2.selected[0].byte_range.start if r2.selected else None}"
    )

    t = "the quick brown fox " * 10
    dup_chunks = _synthetic_chunks([t, t + " extra", "completely different content"])
    dup_scores = [1.0, 0.9, 0.5]
    rd = TokenBudgetOptimizer(
        budget=500,
        deduplicate_overlap=True,
        overlap_threshold=0.8,
        size_unit="chars",
    ).select(dup_chunks, scores=dup_scores)
    assert len(rd.selected) == 2
    print(f"deduplicate_overlap: selected={len(rd.selected)}")

    nws_chunks = _synthetic_chunks(["a " * 20, "b " * 20])
    rn = TokenBudgetOptimizer(budget=25, size_unit="nws").select(nws_chunks, scores=[1.0, 0.5])
    print(f"size_unit=nws: total_nws_sum={rn.total_tokens}")


if __name__ == "__main__":
    main()
