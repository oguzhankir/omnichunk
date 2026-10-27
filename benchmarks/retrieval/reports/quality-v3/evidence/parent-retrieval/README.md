# Development-only parent/window retrieval exploration

This experiment does **not** establish a hierarchy quality advantage. It uses
the 56 already-observed development queries in the correlated CodeSearchNet
original-file view (37 files, 15 repository clusters), the frozen multilingual
MiniLM baseline, and the existing public `Chunker.hierarchical_chunk` / `ChunkTree`
API. No validation material was accessed, no repository code was changed, and no
model inference occurred.

## Declared workflows

`protocol.json` was written before the first workflow scores. All 106 cells are
retained in `results.json.gz`, `summary.json` and `outcomes.csv`:

- Original 512-token raw rank prefix and raw top-1 controls.
- Source-centered windows of 128, 256 or 512 tokens around the same stored top-5
  child anchors, for every one of the ten raw strategies and both child sizes.
- Public hierarchy parents of 128, 256 or 512 tokens for the same OmniChunk
  anchors. Exact native leaf ancestry is used where possible; otherwise a parent
  containing the complete source span is selected. Missing containment uses the
  declared source-window fallback, whose counts are reported.

Overlapping/adjacent ranges from the same source are merged for both expanded
workflows. Proposed additions stop at the first non-fitting result under the
complete 512-token input counter, including two-newline separators. All returned
spans are exact half-open UTF-8 ranges in canonical source. Coarse contexts are
not embedded; the encoder's 128-token per-input limit is therefore not confused
with the separate 512-token retrieved-context budget.

## Results

Mean whole-function evidence recall, same 512-token final context ceiling:

| OmniChunk indexed child size | Raw prefix | Window 128 | Window 256 | Window 512 | Hierarchy 128 | Hierarchy 256 | Hierarchy 512 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 64 | .378606 | .415440 | .403636 | .370492 | .387653 | .391878 | .288901 |
| 96 | .381298 | .422586 | .446930 | .372787 | .415882 | .395369 | .380315 |

The strongest raw named strategy was semantic-text-splitter at 64 tokens
(.409919) and semchunk at 96 tokens (.471130). Applying the same source-window
controls to competitors also helps: the best 64-token expanded mean is
Chonkie SentenceChunker with a 256-token window (.483230). At 96 tokens the best
expanded mean is LangChain's language-specific splitter with a 128-token window
(.461019), below semchunk's raw mean. These are descriptive maxima over the
reported development grid, not independent significance tests.

All positive OmniChunk recall changes versus its own raw prefix have
repository-cluster bootstrap intervals crossing zero. Hierarchy 512 at child
size 64 is a negative result: mean delta -.089704, unadjusted 95% interval
[-.168587, -.008366]. `paired.json` reports every comparison against the same
tool/size raw result and every hierarchy comparison against its matched
source-window control. Resampling uses all 15 repository clusters, 2,000 draws,
seed 20261027. These are exploratory, unadjusted intervals.

## Native hierarchy indexing limitation

The stored anchors were indexed under baseline source `e63c7f0`; the public
hierarchy is built under immutable `79c0c32` (production sources `7413977`).
The hierarchy API also chooses a nonzero leaf minimum unlike the raw benchmark's
zero minimum. Consequently its leaf payloads are not all the indexed payloads:

| Child size | Indexed raw Omni chunks | Actual hierarchy leaves | Exact matching leaves |
| --- | --- | --- | --- |
| 64 | 1,410 | 1,417 | 830 |
| 96 | 941 | 938 | 521 |

This study is explicitly **source-span mapped hierarchy expansion**, not a claim
that native hierarchy leaves were indexed. A second feasibility protocol was
declared before attempting native-index evaluation (`native-protocol.json`).
The verified baseline artifact contains 1,498 of the 2,216 exact role/text keys
required by native leaves and queries; 718 passage embeddings are missing.
`native-cache-coverage.json` records the complete hash-key audit. The declared
rule stops rather than generating native-quality results from incomplete
embeddings. No native-index score or additional model call is claimed.

## Reproduction and audit

Run `study.py`, `test_study.py` and `analyze.py` with the experiment virtualenv;
the scripts use the explicit frozen checkout and development artifact paths
recorded in their source. They never download models or read validation data.
`native_study.py` verifies the decompressed original artifact SHA-256 before
accepting exact role/text-key cached vectors. Outputs are preserved rather than
overwritten by the scoring scripts.

Four meaningful source-window/Unicode/merge/prefix-budget tests passed.
`artifact-audit.json` records **59,901 passed checks** covering exact source
slices, complete budgets, non-overlapping merged spans, metric recomputation and
aggregate numbers. Original raw-prefix metrics were reproduced exactly.

The index vectors and encoder workload are unchanged for the mapped study;
hierarchy construction and source-window mapping add processing/storage work.
Concurrent diagnostic construction timings are retained but do not establish
isolated latency or memory savings. Whole-function gold, documentation-summary
queries, the MIT-only source selection and correlated code views retain the
limitations of the parent corpus. The result does not justify promoting a new
quality preset or changing the v3 frozen source/profile selection.
