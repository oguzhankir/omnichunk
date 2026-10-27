# Secondary held-out parent/window stress execution

This directory runs the same previously declared workflow grid on the released
whole-file multilingual validation view. The child capacities (64/96), expansion
targets (128/256/512), complete final context budget (512), window construction,
hierarchy mapping and union/prefix-stop assembly rules were fixed before the
12:50 validation release. `protocol-addendum.json` records this development-to-test
execution. It introduces no parameter search, winning-workflow selection,
source/profile change or primary benchmark claim.

This is an exploratory secondary stress experiment. The 56 questions and their
whole-function evidence in 35 original files are correlated with the isolated
validation-function view. They are documentation-summary proxy queries from 16
MIT-licensed repository clusters, not an independent user-QA corpus. Findings
cannot be used to promote a workflow after observing these validation scores.

The controller consumes completed primary benchmark reports; it makes zero
encoder or additional ranking calls. It retains all 106 declared baseline-version
rows and all 48 final default/prose-compact/code-compact rows, including every
named rival raw and source-window control. Of those 154 rows, 149 have complete
56-query scores and five explicitly retain the frozen Chonkie64 adapter failure.
Runtime is immutable `frozen-candidate-v3`
(`d0bd4b5`). No dependency, core or harness file is edited.

The public hierarchy call and exact source-window implementation are unchanged
from the original study. `pre-execution-proof.json` records that `Span`,
`Document`, `merged` and `assemble` have identical ASTs in both validation study
scripts and the original pre-release study. Default public trees are used for
all Omni profile anchors. Mapping uses exact native leaf ancestry when available,
then the smallest complete containing parent, then the declared source-window
fallback. Every mapping count is retained. `identity-cache-audit.py` independently
rechecks hierarchy input identity and the full frozen vector caches on these
validation inputs; native identity is never inferred from development results.

`controller.py` waits for both completed primary reports before invoking the
scoring scripts. Run with `/workspace/work/omnichunk-dense/venv/bin/python`.
`identity-cache-audit.py --check-ready` checks the two compressed reports and vector
artifacts before its independent identity/cache audit.

`combined-results.json.gz`, `combined-summary.json` and
`outcomes.csv` retain all 154 cells. `paired.json` includes every own-raw and
matched hierarchy/window comparison; `rival-comparisons.json` includes all 432
matched final-profile versus named-rival controls. Resampling uses all 16
repository clusters with replacement, query-weighted resampled means, 2,000 draws
and seed 20261027. Reported percentile 95% intervals are unadjusted and exploratory
under multiple comparisons.

`row-hashes.json.gz` binds all 154 full workflow rows and all 8,344 available
per-query result rows using canonical JSON SHA-256. The exact source/budget/metric audit and final
file manifest retain input report and protocol hashes. The original development
experiments, their negative outcomes and their manifests remain unchanged in
the parent directories.

## Native identity and cache audit

Native identity was verified again on validation rather than assumed from
development. Default and prose-compact indexed passages exactly equal actual
public hierarchy leaves in source ID, UTF-8 range, text, benchmark passage ID and
order: **1,336 leaves at child64 and 887 at child96**. All 280 stored anchors per
target/capacity map to exact native ancestry, with zero fallback. Code-compact
has 1,059/716 indexed passages and differs from the default tree; its hierarchy
rows keep the explicit span-mapping/fallback label.

`identity-cache-audit.json` independently checked both complete decompressed
vector artifact SHA-256 hashes, matching corpus/model/revision/preprocessing,
dimension/overflow and model-file metadata, and all **1,643** shared raw vector
payloads. The candidate cache alone covers all **2,105** required exact role/text
keys (2,049 passage texts and 56 query texts), filling 708 baseline cache gaps.
The audit also passed 4,446 canonical-byte/native-capacity checks. Existing
candidate preparation had encoder cost; this secondary workflow execution reuses
it and makes zero new encoder or ranking calls.

`workflow-index-labels.json` labels each hierarchy row using that independent
identity/cache proof. Default/prose rows can be labelled native-leaf-indexed;
code-compact and legacy baseline hierarchy rows remain explicitly span-mapped.

## Complete final-profile recall table

Every cell has the same complete 512-token final-context ceiling. Raw top-one
controls, precision, IoU, vector counts, complete budget use and all per-query
outcomes are retained in the full artifacts.

| Indexed profile | Child capacity | Raw prefix | Window128 | Window256 | Window512 | Hierarchy128 | Hierarchy256 | Hierarchy512 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Default | 64 | .380026 | .395696 | .415348 | .360778 | .369044 | .393422 | .358204 |
| Default | 96 | .442240 | .404073 | .401190 | .297657 | .385576 | .371404 | .284521 |
| Prose-compact | 64 | .380026 | .395696 | .415348 | .360778 | .369044 | .393422 | .358204 |
| Prose-compact | 96 | .442240 | .404073 | .401190 | .297657 | .385576 | .371404 | .284521 |
| Code-compact | 64 | .399108 | .419889 | .435560 | .363721 | .397544 | .378912 | .325512 |
| Code-compact | 96 | .370523 | .361020 | .446443 | .355614 | .340319 | .413020 | .312077 |

The positive development result for default child96/window128 did **not**
replicate: validation recall falls from raw .442240 to .404073, delta -.038167
(17 wins, 26 ties, 13 losses), unadjusted 95% interval [-.111574, .042195]. The
same anchor hierarchy128 mean is .385576. Default child96/window512 and
hierarchy512 regress versus raw: deltas -.144583 and -.157719, intervals
[-.269923, -.039422] and [-.271075, -.058327]. Prose-compact is identical on this
Python corpus and retains these same outcomes. Every positive recall delta in
the final profiles has an interval crossing zero. These are unadjusted,
exploratory intervals; no workflow is promoted.

## Named rival controls

Mean recall for every named rival's raw prefix and all source-window targets at
the same child capacity/final budget is retained below. These tables retain
strong controls such as LlamaIndex Sentence64/window256 (.459300) and Chonkie
Sentence96/window256 (.462947); they are reported cells, not selected winners or
a universal library ranking.

| Rival at child64 | Raw prefix | Window128 | Window256 | Window512 |
| --- | --- | --- | --- | --- |
| Fixed | .362808 | .364806 | .374789 | .418994 |
| semchunk | .407709 | .407092 | .384633 | .329556 |
| LangChain recursive | .354011 | .367067 | .374896 | .334457 |
| semantic-text-splitter | .419300 | .419631 | .393676 | .376965 |
| LlamaIndex token | .271411 | .355036 | .378407 | .437193 |
| Chonkie Sentence | Failed | Failed | Failed | Failed |
| LangChain code | .378416 | .353892 | .368614 | .280886 |
| LlamaIndex Sentence | .364035 | .394629 | .459300 | .381397 |
| semantic code | .361367 | .421782 | .398496 | .320692 |

| Rival at child96 | Raw prefix | Window128 | Window256 | Window512 |
| --- | --- | --- | --- | --- |
| Fixed | .386688 | .423251 | .459984 | .419488 |
| semchunk | .435657 | .409639 | .416479 | .317826 |
| LangChain recursive | .437738 | .395202 | .430125 | .362104 |
| semantic-text-splitter | .428966 | .430711 | .399695 | .321789 |
| LlamaIndex token | .309269 | .364345 | .403467 | .405987 |
| Chonkie Sentence | .382946 | .383519 | .462947 | .387440 |
| LangChain code | .431639 | .424465 | .375524 | .308532 |
| LlamaIndex Sentence | .359116 | .396586 | .369959 | .328229 |
| semantic code | .415109 | .360036 | .396314 | .310945 |

Chonkie64 failed frozen canonical-output/native-budget conformance with
`ValueError: Adapter output exceeds the shared payload budget` before dense
evaluation. It has no retrieval score. Five workflow rows and 24 matched
comparisons explicitly retain that failure; no zero score, adapter repair,
per-file filtering or rerun is substituted. Chonkie96's completed independent
report is included from `baseline-valid-96`. `control-inventory-record.json`
binds both source reports and the failure artifact. The first combined-analysis
attempt stopped at its declared count guard before writing results, because the
main baseline report held only the other 18 strategy/capacity cells. Its source
and log remain preserved; completed scoring rows were reused unchanged.

## Completed checks and commitments

The exact artifact audit passed **72,807** canonical-source, complete-budget,
metric and aggregate checks. There are 154 declared own-raw comparisons
(149 available, five explicit failures) and 432 declared matched rival
comparisons (408 available, 24 explicit failures). All use 16 repository clusters
and the previously fixed bootstrap settings.

`row-hashes.json.gz` commits all 154 workflow rows, including failure rows, and
all **8,344** available per-query rows. The 280 unavailable per-query slots belong
to the five frozen failed workflow rows and are not fabricated. Finalization
independently verifies all **8,498** workflow/query row hashes and records the
native/mapped labels. `manifest.json` binds every secondary artifact, including
the original unsuccessful count-guard attempt and inventory correction. No
additional inference, ranking, dependency/core/harness edit, parameter change or
winning-workflow promotion occurred.
