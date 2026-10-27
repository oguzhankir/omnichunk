# Complete frozen validation summary

One frozen sample; all 24 settings and all 8 runtime/adapter curves are reported. There are 144 unique questions/16 validation articles, reused across correlated views, models and budgets. Counts of changed cells are not counts of independent questions. No post-validation sampling, source/model/configuration changes or favorable-setting selection.

## Complete predeclared context-budget frontier

All 12 frozen-vector replays and 84 paired comparisons are complete. Every 512-token anchor reproduces its entire original report exactly after removing only added replay provenance. There were no new encoder calls or replacement samples. Across all 24 fixed settings, candidate/current recall has five positive mean cells and nineteen exact ties, with no recall-loss query-setting instance. The five gains are not five independent findings: four repeat one multilingual-model 64-token case at budgets128/256 in both correlated views. The remaining gain is English Markdown96 at128. Every positive recall delta interval touches zero.

The English Markdown96/128 gain trades precision/IoU for recall. Across all settings, precision/IoU means rise in seven cells, decline in two and tie in fifteen. The multilingual text64/512 loss is tiny but retained. No favorable budget is selected for the headline.

Each paired field below is **delta; W/T/L; 95% article-component interval**. All 144 query pairs are retained per cell, with no pooling across models/views/budgets.

| Encoder / view / chunk tokens | Context tokens | Recall current→candidate | Δ recall; W/T/L; CI | Δ precision; W/T/L; CI | Δ IoU; W/T/L; CI |
| --- | --- | --- | --- | --- | --- |
| multilingual / text / 64 | 128 | 0.813368→0.814670 | +0.001302; 1/143/0; [0, 0.003906] | +0.000248; 2/141/1; [0, 0.000744] | +0.000254; 2/141/1; [0, 0.000762] |
| multilingual / text / 64 | 256 | 0.931424→0.932726 | +0.001302; 1/143/0; [0, 0.003906] | +0.000055; 2/142/0; [0, 0.000166] | +0.000056; 2/142/0; [0, 0.000169] |
| multilingual / text / 64 | 512 | 0.965278→0.965278 | 0; 0/144/0; [0, 0] | -0.000000175; 0/143/1; [-0.000000524, 0] | -0.000000175; 0/143/1; [-0.000000524, 0] |
| multilingual / text / 96 | 128 | 0.777778→0.777778 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| multilingual / text / 96 | 256 | 0.916667→0.916667 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| multilingual / text / 96 | 512 | 0.965278→0.965278 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| multilingual / Markdown / 64 | 128 | 0.806424→0.807726 | +0.001302; 1/143/0; [0, 0.003906] | +0.000394; 4/140/0; [0, 0.001183] | +0.000399; 4/140/0; [0, 0.001196] |
| multilingual / Markdown / 64 | 256 | 0.938368→0.939670 | +0.001302; 1/143/0; [0, 0.003906] | +0.000028; 3/141/0; [0, 0.000084] | +0.000029; 3/141/0; [0, 0.000087] |
| multilingual / Markdown / 64 | 512 | 0.965278→0.965278 | 0; 0/144/0; [0, 0] | +0.000003617; 1/142/1; [0, 0.000011] | +0.000003617; 1/142/1; [0, 0.000011] |
| multilingual / Markdown / 96 | 128 | 0.770833→0.770833 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| multilingual / Markdown / 96 | 256 | 0.916667→0.916667 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| multilingual / Markdown / 96 | 512 | 0.972222→0.972222 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / text / 64 | 128 | 0.847780→0.847780 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / text / 64 | 256 | 0.931114→0.931114 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / text / 64 | 512 | 0.974392→0.974392 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / text / 96 | 128 | 0.864198→0.864198 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / text / 96 | 256 | 0.944444→0.944444 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / text / 96 | 512 | 0.972222→0.972222 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / Markdown / 64 | 128 | 0.847780→0.847780 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / Markdown / 64 | 256 | 0.931114→0.931114 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / Markdown / 64 | 512 | 0.974392→0.974392 | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] | 0; 0/144/0; [0, 0] |
| english / Markdown / 96 | 128 | 0.857253→0.864198 | +0.006944; 1/143/0; [0, 0.020833] | -0.000070; 3/137/4; [-0.000210, 0] | -0.000070; 3/137/4; [-0.000210, 0] |
| english / Markdown / 96 | 256 | 0.944444→0.944444 | 0; 0/144/0; [0, 0] | +0.000030; 4/136/4; [0, 0.000089] | +0.000030; 4/136/4; [0, 0.000089] |
| english / Markdown / 96 | 512 | 0.972222→0.972222 | 0; 0/144/0; [0, 0] | +0.000009965; 7/131/6; [-0.000002426, 0.000026] | +0.000009965; 7/131/6; [-0.000002426, 0.000026] |

![All frozen adapter/runtime recall curves](frontier.svg)

The eight panels show all six adapter choices plus released/current OmniChunk at 128/256/512 native context tokens; curves can overlap exactly. These are descriptive source-evidence means, not latency curves or independently replicated observations. The complete numeric curves for recall, precision and IoU are in `validation-curves.csv`; `validation-summary.json/.md` retains all named-rival paired intervals and cost dimensions.

Named-rival ordering varies across encoder, view, chunk size and budget. The primary 512-token ties must not be presented as an independent recall improvement; smaller-budget gains are narrow and include a precision tradeoff. No universal ranking, Pareto superiority or production latency benefit follows. **Sampling has stopped:** this report closes the frozen experiment without changing or rerunning the candidate from validation outcomes.

## Complete numeric recall curves

Each cell lists mean evidence recall at contexts **128 → 256 → 512**. Precision, IoU, vector/native-token costs and context usage for every point are in CSV/JSON.

### Multilingual

| Runtime / adapter | Text64 | Text96 | Markdown64 | Markdown96 |
| --- | --- | --- | --- | --- |
| release | 0.827257 → 0.924479 → 0.957031 | 0.770833 → 0.916667 → 0.965278 | 0.813368 → 0.924479 → 0.957031 | 0.770833 → 0.916667 → 0.965278 |
| current | 0.813368 → 0.931424 → 0.965278 | 0.777778 → 0.916667 → 0.965278 | 0.806424 → 0.938368 → 0.965278 | 0.770833 → 0.916667 → 0.972222 |
| candidate | 0.814670 → 0.932726 → 0.965278 | 0.777778 → 0.916667 → 0.965278 | 0.807726 → 0.939670 → 0.965278 | 0.770833 → 0.916667 → 0.972222 |
| fixed | 0.765499 → 0.908735 → 0.963085 | 0.702739 → 0.872434 → 0.937500 | 0.738163 → 0.882918 → 0.931250 | 0.647898 → 0.821972 → 0.919560 |
| semchunk | 0.842448 → 0.944010 → 0.971788 | 0.763889 → 0.916667 → 0.965278 | 0.842448 → 0.950955 → 0.971788 | 0.756944 → 0.916667 → 0.972222 |
| langchain | 0.692576 → 0.769825 → 0.857219 | 0.725217 → 0.828998 → 0.917800 | 0.692576 → 0.769825 → 0.864164 | 0.718273 → 0.828998 → 0.924744 |
| semantic-text-splitter | 0.814670 → 0.925781 → 0.965278 | 0.777778 → 0.916667 → 0.965278 | 0.817875 → 0.933007 → 0.972222 | 0.741588 → 0.905331 → 0.951389 |
| llamaindex | 0.699732 → 0.810754 → 0.901933 | 0.790842 → 0.871445 → 0.948413 | 0.706391 → 0.823330 → 0.926996 | 0.767361 → 0.891560 → 0.947774 |

### English

| Runtime / adapter | Text64 | Text96 | Markdown64 | Markdown96 |
| --- | --- | --- | --- | --- |
| release | 0.847780 → 0.926840 → 0.970119 | 0.864969 → 0.941358 → 0.979167 | 0.847780 → 0.926840 → 0.970119 | 0.864969 → 0.941358 → 0.979167 |
| current | 0.847780 → 0.931114 → 0.974392 | 0.864198 → 0.944444 → 0.972222 | 0.847780 → 0.931114 → 0.974392 | 0.857253 → 0.944444 → 0.972222 |
| candidate | 0.847780 → 0.931114 → 0.974392 | 0.864198 → 0.944444 → 0.972222 | 0.847780 → 0.931114 → 0.974392 | 0.864198 → 0.944444 → 0.972222 |
| fixed | 0.785432 → 0.901133 → 0.965313 | 0.708729 → 0.889282 → 0.963790 | 0.773199 → 0.899294 → 0.958333 | 0.755048 → 0.880048 → 0.963816 |
| semchunk | 0.835503 → 0.939670 → 0.971788 | 0.861111 → 0.930556 → 0.972222 | 0.835503 → 0.939670 → 0.971788 | 0.861111 → 0.930556 → 0.972222 |
| langchain | 0.705595 → 0.825493 → 0.892827 | 0.796380 → 0.865859 → 0.938237 | 0.705595 → 0.825493 → 0.892827 | 0.789435 → 0.865859 → 0.938237 |
| semantic-text-splitter | 0.849268 → 0.932602 → 0.974392 | 0.857253 → 0.944444 → 0.972222 | 0.821998 → 0.905331 → 0.972222 | 0.810038 → 0.898386 → 0.944444 |
| llamaindex | 0.791623 → 0.881375 → 0.941468 | 0.775597 → 0.889821 → 0.934960 | 0.736434 → 0.896065 → 0.939709 | 0.764363 → 0.897224 → 0.956996 |

## Actual original producer statistics

Current rows prepare all six adapters; release/candidate rows prepare OmniChunk only. All rows deduplicate across their two chunk capacities. These global costs are not isolated per-adapter bills or end-to-end/query latency.

| Encoder / view / runtime | Unique passage/query texts | Native passage/query tokens | Passage/query batches | Encoding seconds | Load seconds | Process peak RSS MiB |
| --- | --- | --- | --- | --- | --- | --- |
| multilingual / article-text / current | 2367/144 | 93668/2350 | 74/5 | 86.584 | 2.779 | 1588.1 |
| multilingual / article-text / release | 318/144 | 17050/2350 | 10/5 | 12.862 | 2.100 | 1507.1 |
| multilingual / article-text / candidate | 311/144 | 17189/2350 | 10/5 | 13.120 | 2.259 | 1503.4 |
| multilingual / article-markdown / current | 2510/144 | 99235/2350 | 79/5 | 90.045 | 1.828 | 1590.8 |
| multilingual / article-markdown / release | 334/144 | 17139/2350 | 11/5 | 11.833 | 2.090 | 1508.9 |
| multilingual / article-markdown / candidate | 326/144 | 17281/2350 | 11/5 | 12.022 | 2.163 | 1498.4 |
| english / article-text / current | 2216/144 | 83845/2136 | 70/5 | 36.362 | 0.364 | 740.3 |
| english / article-text / release | 279/144 | 15118/2136 | 9/5 | 6.763 | 0.681 | 641.5 |
| english / article-text / candidate | 275/144 | 15210/2136 | 9/5 | 5.275 | 0.681 | 650.5 |
| english / article-markdown / current | 2355/144 | 89165/2136 | 74/5 | 40.207 | 0.354 | 731.0 |
| english / article-markdown / release | 295/144 | 15202/2136 | 10/5 | 6.540 | 0.602 | 660.0 |
| english / article-markdown / candidate | 289/144 | 15293/2136 | 10/5 | 5.226 | 0.587 | 650.1 |
