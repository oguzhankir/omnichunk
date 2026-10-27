# Causal diagnosis of new English development gaps

Only the 16 development articles/144 independently authored questions were read. Text and Markdown views contain the same questions and paragraph bytes with exact offset rebasing, so their repeated gap IDs are correlated observations. No sealed validation was inspected. Frozen-vector replay verified the original top-five cosine scores and selected prefix IDs; no model inference was performed.

The current paragraph-isolation rule is exactly neutral in both views at 64/96: passages and all per-query quality fields match. Native-token structure explains its limited reach: all 48 paragraphs exceed 64 tokens; only 2 fit 96, and their existing boundaries already stay separate. There are 266 heuristic sentences, 15 exceeding 64 and exactly one exceeding 96. That last sentence contains a semicolon that can split it into fitting complete clauses.

## All five positive semchunk recall gaps

These are the complete text-control gaps, repeated at the same question IDs in Markdown. “Prefix” counts passages retained by the whole 512-token rank prefix.

| Capacity / question | Current gold rank / prefix | semchunk gold rank / prefix | Causal finding |
| --- | --- | --- | --- |
| 64 / `new-squad-57268f2bf1498d1400e8e3c6` — EU reform referendum | 14 / 12 | 14 / 14 | Gold text has identical native token IDs and cosine 0.330850. Larger earlier current passages exhaust the budget before the unchanged gold item; no gold segmentation defect. Recall 0→1. |
| 64 / `new-squad-5726f7715951b619008f838f` — doctors' conflict-of-interest analogy | 33 / 11 | 2 and 61 / 13 | Current answer begins “This system reflects…” without the prior self-interest explanation and ranks poorly. semchunk combines that supporting sentence with the start of the answer, ranking it second, but cuts the answer itself after “U.S.”; only 0.6 recall is recovered. Context support versus boundary preservation is a real tradeoff. |
| 64 / `new-squad-5728facd4b864d1900165173` — Vietnam War civil disobedients | 10 / 9 | 11 / 12 | Identical gold token IDs and cosine 0.343098. Different earlier chunk sizes/pools let semchunk retain more passages; current excludes intact gold at the budget cutoff. Recall 0→1. |
| 96 / `new-squad-5728fc9e1d04691400778f15` — courthouse leafleters | 1 and 12 / 6 | 2 / 8 | One 97-token sentence becomes a 95-token prefix plus orphan `evidence."` of 4 tokens. The latter contains the last 8 gold bytes and is not retrieved, producing 0.891892 recall. semchunk cuts at the sentence's existing semicolon; its 66-token second clause preserves the complete answer and recalls 1.0. |
| 96 / `new-squad-5729f4273f37b319004785fe` — author of *Capital in the Twenty-First Century* | 8 / 6 | 4 / 6 | Current gold remains intact in a 77-token passage, but the heuristic boundary at `[pp. ` separates numeric citation material. semchunk keeps more citation context in a 94-token passage and ranks it fourth. This is representation/ranking, not gold-byte loss. Recall 0→1. |

At 64 the three positive gaps sum to 2.6/144 = 0.018056, explaining semchunk recall 0.976389 versus current 0.958333. At 96 the two gaps sum to 1.108108/144 = 0.007695, explaining 0.986111 versus 0.978416. The three 64-token cases and two 96-token cases exhaust the positive recall differences; there is no fourth independent 64-token gap.

## General families to screen independently

1. **Complete sentence atoms inside long prose.** This changes oversized paragraphs that paragraph isolation cannot affect and can lower unrelated passage payload before a gold item at a fixed context budget. Cost and context losses must be measured: the pharmacy case demonstrates that isolating an anaphoric answer sentence can discard necessary topical support. No improvement should be assumed from the number of emitted sentences.
2. **Clause-first fallback for oversized sentences.** Try strong semicolon/colon/em-dash units before generic whitespace, preserving delimiters and full-source token accounting. The courthouse example gives a direct structural cause: the existing semicolon divides the 97-token sentence into clauses of 32 and 66 tokens, avoiding the tiny final word tail without changing 96. It is also the sole sentence above 96 in this corpus, so a gain would have narrow measured support rather than establishing broad English quality superiority.

These families were assigned for isolated actual-model screens. Do not add a citation-specific, query-specific or scores-only exception before those screens finish. The Piketty citation boundary is a useful limitation to disclose, not justification for a one-question abbreviation patch. Changes to global distractor representations can also affect the two budget-cutoff cases despite leaving their gold embeddings unchanged.

## Workload context

In the text view, current/semchunk use 205/220 chunks and 9658/9688 passage tokens at 64; at 96 they use 137/141 chunks and 9522/9530 tokens. Mean context usage is 489.29/490.19 tokens and 478.86/478.38 tokens respectively, so the aggregate precision difference is not explained simply by semchunk leaving more budget unused. It retains more, shorter relevant-ranked items in some cases with modest extra native-token overhead and extra vectors.

`new-english-development-diagnosis.json` preserves exact ranks, cosine scores, token counts and gold passages. `new-english-development-structure.json` records structure counts and model/source fingerprints. `new-development-summary.json/.md`, regenerated by `summarize_new_development.py`, incrementally includes both frozen encoders, all named current baselines and available candidate reports, with missing paired comparisons explicitly marked.
