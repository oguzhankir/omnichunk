# Final-c1 development workflow extension

This is a secondary development-only extension of the existing fixed parent/window
workflow grid. It does not change the primary benchmark, frozen settings, chosen
profiles, source or claims. The original protocol fixed child capacities 64/96,
expansion targets 128/256/512 and the complete 512-token context ceiling before
held-out release. `protocol-addendum.json` records only the final candidate version
and profile inputs; there is no new parameter search or winning-workflow selection.

All **154** cells are retained: the original 106 baseline-version cells and all 48
final default/prose-compact/code-compact cells. `combined-results.json.gz` contains
every per-query source span, metric and mapping count; `outcomes.csv` and
`combined-summary.json` contain the full table. Version identity is explicit, so
old and final OmniChunk rows cannot be confused. Every competitor keeps all its
raw and source-window controls. No new inference or ranking calls occurred.

## Native hierarchy identity and cache proof

The previous baseline-version study needed span mapping because raw OmniChunk
leaves differed from native hierarchy leaves. The final default candidate removes
that limitation **for these exact development inputs**:

| Child capacity | Actual public hierarchy leaves | Final default indexed passages | Exact source/range/text/passage-ID identity |
| --- | --- | --- | --- |
| 64 | 1,417 | 1,417 | All, including global order |
| 96 | 938 | 938 | All, including global order |

`identity-audit.json` independently verifies the public API output under immutable
runtime `d0bd4b5` against the final-c1 report, including 4,710 canonical-span and
native-budget checks. That runtime's Python inputs match c1; these files are all
Python. Each default top-five anchor maps to its exact public leaf: **280/280** at
every target/capacity, with zero containment or source-window fallback. Therefore
the final default hierarchy rows are genuine native-leaf-indexed workflows using
already-stored native-leaf ranks, rather than a claim about differently indexed
leaf payloads.

`cache-coverage.json` independently verifies both full decompressed vector-artifact
SHA-256 hashes, matching corpus/model/revision/preprocessing/dimension/overflow
and model-file metadata, and all 1,683 shared raw vector payloads. Every one of the
2,216 required exact role/text keys (2,161 passage texts, 55 distinct query texts
for 56 questions) exists in the candidate cache alone. It fills all 718 gaps in
the earlier baseline cache. This study reuses that completed preparation; it does
not claim those vectors originally cost zero encoder calls.

The same unchanged **default public hierarchy** is used for all profile anchor
sets. Prose-compact produces identical Python chunks here and therefore identical
results. Code-compact differs and keeps the original exact-leaf → containing
parent → source-window fallback rule. Its hierarchy rows remain explicitly
span-mapped; no native code-compact hierarchy index is claimed.

## All final mean recall values

Every value uses the same complete 512-token final-context ceiling. All precision,
IoU, vector counts, budget usage, top-one controls and per-query outcomes remain
in the full artifacts.

| Indexed profile | Child capacity | Raw prefix | Window 128 | Window 256 | Window 512 | Hierarchy 128 | Hierarchy 256 | Hierarchy 512 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Default | 64 | .424103 | .435421 | .452428 | .405177 | .429405 | .409735 | .336835 |
| Default | 96 | .444765 | .513930 | .451012 | .354930 | .454465 | .393982 | .344600 |
| Prose-compact | 64 | .424103 | .435421 | .452428 | .405177 | .429405 | .409735 | .336835 |
| Prose-compact | 96 | .444765 | .513930 | .451012 | .354930 | .454465 | .393982 | .344600 |
| Code-compact | 64 | .360734 | .411241 | .424396 | .357143 | .386218 | .365625 | .295899 |
| Code-compact | 96 | .357815 | .383587 | .416590 | .338168 | .372038 | .427802 | .286753 |

The hierarchy results do not show a consistent advantage over plain source
windows. For example, default child96 hierarchy128 has recall .454465 while its
same-anchor window128 control has .513930. Larger hierarchy parents can lose
recall because fewer source spans fit in the fixed final budget. These negative
rows are retained, including both hierarchy512 default means below raw.

Default child96/window128 increases recall over its own raw control by .069165
(21 wins, 32 ties, 3 losses); its unadjusted repository-cluster 95% interval is
[.007905, .133659]. This is one cell in an exploratory multi-cell grid, not an
independent superiority result or permission to promote a preset. Same-target
rival-window comparisons include positive and inconclusive intervals, all
reported in `rival-comparisons.json`. Raw rival semchunk96 remains .471130;
ChonkieSentence64/window256 remains .483230. Those are different reported cells,
not a reason to omit stronger controls or collapse the grid into a winning mean.

## Fixed workflow and public API

Public trees use exactly the originally declared call:

```python
tree = Chunker(
    size_unit="tokens",
    tokenizer=count_native_tokens_with_specials,
    context_mode="none",
    coverage_policy="retrieval",
).hierarchical_chunk(
    path,
    canonical_source,
    source_id=source_id,
    levels=[child_capacity, 128, 256, 512],
)
```

Index child text, retain its source/range identity, and get ancestors through
`tree.parent(leaf)`. Parent text is exact canonical source. Use a separate context
counter when assembling retrieved parents: union overlapping or adjacent
same-source ranges in anchor-rank order, include two-newline separator costs, and
stop at the first proposed addition exceeding 512 complete tokens. Parent payloads
are not embedded; the model's 128-token encoder limit remains distinct from the
retrieved-context budget.

The source-window control uses native fast-tokenizer offset mappings to center
the declared target around each complete raw anchor, shifts at source edges,
then deterministically shrinks outside token bounds until the complete native
counter fits. It uses no query terms or gold labels. The exact helper is
`Document.window` in `study.py`; `assemble` implements the shared union/budget
rules. Their ASTs are identical to the original declared study, along with
`Document`, `Span` and `merged`. Windowing adds source-access/tokenization work;
hierarchy adds tree construction and metadata. No latency or memory advantage
is inferred from concurrent diagnostic timings.

## Verification and reproduction

The scoring script reproduced every final raw-prefix metric exactly from the
source candidate report. The combined independent audit passed **74,183** exact
source/budget/metric/aggregate checks. The original four meaningful UTF-8,
anchor-preservation, transitive-union and prefix-stop unit tests passed again.
`paired.json` contains all 154 own-raw comparisons plus every matched hierarchy
versus window comparison; `rival-comparisons.json` contains all 432 final-profile
versus matched rival-control comparisons. Both use the same 15 repository
clusters, 2,000 replacement draws and seed 20261027 as the original study.
Intervals are unadjusted percentile intervals and descriptive under multiple
comparisons.

Run the scripts with `/workspace/work/omnichunk-dense/venv/bin/python`. Artifact
paths, frozen source and hashes are explicit in the scripts and protocols.
Completed result files are never overwritten by the scoring/analysis scripts.
`manifest.json` binds every final-extension artifact. The earlier study and its
negative results are preserved unchanged in the parent directory.

Only the already observed 56-query, 37-file development view was accessed. Its
queries are correlated with the isolated-function corpus and include 55 unique
query texts; whole-function evidence, documentation-summary proxy queries,
MIT-only source selection and 15 repository clusters limit generalization.
No validation path, label or metric was accessed, and no core or harness file
was edited.
