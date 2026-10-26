# Code-comment atom screen: development-only independent analysis

Candidate `ccb9888011274f7e54e6ace896860fd6274adc1f` is compared with the `ce356a2` core under unchanged native tokenizer/model and 64/96-token chunk, 512-token retrieval budgets. Both external configurations are exact quality ties. This is a development screen, not another held-out evaluation.

| Synthetic capacity | Metric | Before | After | Delta | W/T/L | Descriptive 95% delta interval |
| --- | --- | --- | --- | --- | --- | --- |
| 64 | Recall | 0.912709 | 0.919361 | +0.006652 | 6/174/0 | [0.001079, 0.014303] |
| 64 | Precision | 0.081264 | 0.081650 | +0.000386 | 55/76/49 | [-0.000277, 0.001194] |
| 64 | IoU | 0.080961 | 0.081377 | +0.000417 | 55/76/49 | [-0.000266, 0.001257] |
| 96 | Recall | 0.894515 | 0.900000 | +0.005485 | 10/165/5 | [-0.036561, 0.050147] |
| 96 | Precision | 0.084118 | 0.084591 | +0.000474 | 65/61/54 | [-0.002697, 0.003827] |
| 96 | IoU | 0.084063 | 0.084591 | +0.000529 | 65/61/54 | [-0.002654, 0.003894] |

At 64 all six recall gains repair the previously diagnosed fitting comment/statement split: `en/retry_client/q04`, `en/file_reader/q09`, `tr/stock_reservation/q01`, and `tr/report_filter/q01`, `q04`, `q08`. Their previous partial recalls become 1.0; none decline. Code-category recall rises by 0.014967; English rises 0.007307, Turkish 0.012648 and Japanese is unchanged. Precision still declines on 49 queries, including a table-slice mean loss of 0.000509 caused by changed global distractors.

At 96 the five recall losses are `en/retry_client/q09`, `en/task_lease/q05`, `en/file_reader/q09`, and `tr/stock_reservation/q03`, `q07`, each 1→0. Every gold comment+statement remains intact; each moves into a different two-policy chunk with a preceding unrelated policy and falls outside the ranked context prefix. The previous representation paired it with following material or split neighboring policies differently. This is embedding dilution and greedy grouping alignment, not source loss, token overflow or incorrect atom ownership.

The ten 96-token gains comprise nine code queries and `tr/import_workflow/q10`, an unchanged Markdown passage that wins after code distractors change. Code-category mean recall actually changes -0.000158; the overall gain depends on this global-ranking Markdown gain. English recall falls 0.042154 (3 losses, 2 partial gains), Turkish rises 0.053416 (6 gains, 2 losses), and Japanese rises 0.005194 (2 partial gains). Report all three rather than claiming every language improves.

## Named rivals and cost

| Synthetic capacity | Adapter | Recall | Precision | Chunks | Passage tokens |
| --- | --- | --- | --- | --- | --- |
| 64 | Code-atoms OmniChunk | 0.919361 | 0.081650 | 217 | 8869 |
| 64 | Current OmniChunk | 0.912709 | 0.081264 | 208 | 8851 |
| 64 | semchunk | 0.917331 | 0.081857 | 217 | 8869 |
| 64 | semantic-text-splitter | 0.917913 | 0.081282 | 217 | 8869 |
| 64 | LangChain | 0.927082 | 0.080945 | 239 | 8913 |
| 96 | Code-atoms OmniChunk | 0.900000 | 0.084591 | 127 | 8689 |
| 96 | Current OmniChunk | 0.894515 | 0.084118 | 119 | 8673 |
| 96 | semchunk | 0.900000 | 0.085022 | 127 | 8689 |
| 96 | semantic-text-splitter | 0.900000 | 0.084586 | 127 | 8689 |
| 96 | LangChain | 0.888889 | 0.083159 | 134 | 8703 |

All 180 per-query recall values at 96 exactly match semchunk and semantic-text-splitter, including the five losses. At 64 the new candidate exceeds both in recall and exceeds ST in precision, while semchunk keeps higher precision and LangChain keeps higher recall. No universal superiority is established.

Compared with current OmniChunk, vector counts grow 4.3%/6.7% at 64/96, while full native passage-token workloads grow only 0.20%/0.18%. These counts exactly match semchunk/ST. Chunking medians are 0.359→0.355 seconds and 0.207→0.242 seconds; frozen ranking medians are 5.280→5.250 ms and 2.812→2.887 ms. Those noisy local samples are not evidence of a speedup. The screen encodes only OmniChunk, so its shared preparation duration cannot be compared with the earlier six-adapter preparation pass.

External scores and workloads stay unchanged: recall 0.979167 at both capacities, 64/45 chunks and 3030/2992 native tokens. Fixed still has better external precision and wins external 64 recall; this code-only rule does not address that gap.

Recommendation: keep this as a promising general structural repair for combination screening, with the five 96-token losses disclosed. Do not add query-specific exceptions. A later general strong-block rule could screen preserving each complete blank-line-separated logical atom instead of merging unrelated pairs, but its increased vector cost must be reported; no further tweak is warranted by these five examples alone.

`independent-analysis.json` retains all changed query metrics, slice comparisons, native workloads and named-rival deltas. No additional model runs or test inspection were performed.
