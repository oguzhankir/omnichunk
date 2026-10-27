# New English development matrix

Only new article-disjoint English development reports under matrix/dev. Text and Markdown views reuse the same articles/questions and are correlated controls. Encoders have different native tokenization; matched budgets compare adapters within an encoder, not equal semantic payload across encoders. No sealed validation is read.

Named rival maxima are aggregate means for a fixed encoder/view/capacity/metric, not per-query oracle scores. Preserve all views, metrics, losses and context utilization. Do not infer a code-rule advantage from plain English prose without that code path. Selection waits for all declared development evidence.

## english / article-markdown

`sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; 16 development articles and 144 queries.

| Run / adapter | Tokens | Recall | Precision | IoU | Chunks | Native passage tokens | Mean context used |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current / omnichunk | 64 | 0.986111 | 0.009574 | 0.009574 | 200 | 8620 | 489.6 |
| current / omnichunk | 96 | 0.993056 | 0.009849 | 0.009849 | 136 | 8492 | 475.9 |
| current / fixed | 64 | 0.993056 | 0.009764 | 0.009764 | 140 | 8581 | 484.1 |
| current / fixed | 96 | 0.969807 | 0.009691 | 0.009691 | 97 | 8440 | 475.3 |
| current / semchunk | 64 | 0.986111 | 0.009556 | 0.009556 | 209 | 8638 | 490.2 |
| current / semchunk | 96 | 0.993056 | 0.010027 | 0.010027 | 137 | 8494 | 473.1 |
| current / langchain | 64 | 0.962846 | 0.008584 | 0.008578 | 600 | 9420 | 505.0 |
| current / langchain | 96 | 0.981541 | 0.009039 | 0.009035 | 417 | 9054 | 499.8 |
| current / semantic-text-splitter | 64 | 0.986111 | 0.009420 | 0.009420 | 208 | 8636 | 491.8 |
| current / semantic-text-splitter | 96 | 1.000000 | 0.009893 | 0.009893 | 143 | 8506 | 476.2 |
| current / llamaindex | 64 | 0.969462 | 0.008916 | 0.008914 | 341 | 8902 | 500.0 |
| current / llamaindex | 96 | 0.980620 | 0.009425 | 0.009424 | 228 | 8676 | 490.8 |
| citation / omnichunk | 64 | 0.986111 | 0.009585 | 0.009585 | 200 | 8620 | 488.0 |
| citation / omnichunk | 96 | 0.993056 | 0.009849 | 0.009849 | 136 | 8492 | 475.9 |
| combined / omnichunk | 64 | 0.986111 | 0.009574 | 0.009574 | 200 | 8620 | 489.6 |
| combined / omnichunk | 96 | 0.993056 | 0.009849 | 0.009849 | 136 | 8492 | 475.9 |

| Candidate / tokens | Δ recall; W/T/L; 95% CI | Δ precision; W/T/L; CI | Δ IoU; W/T/L; CI |
| --- | --- | --- | --- |
| citation / 64 | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000010; 19/111/14; [-0.000008, 0.000029] | +0.000010; 19/111/14; [-0.000008, 0.000029] |
| citation / 96 | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] |

- citation / 64: changed output; all gains/losses and cost ratios are preserved in JSON.
- citation / 96: exactly unchanged passages and per-query quality.

## english / article-text

`sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; 16 development articles and 144 queries.

| Run / adapter | Tokens | Recall | Precision | IoU | Chunks | Native passage tokens | Mean context used |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current / omnichunk | 64 | 0.986111 | 0.009596 | 0.009596 | 185 | 8533 | 488.6 |
| current / omnichunk | 96 | 0.993056 | 0.009850 | 0.009850 | 122 | 8407 | 476.2 |
| current / fixed | 64 | 0.977533 | 0.009557 | 0.009557 | 139 | 8505 | 483.4 |
| current / fixed | 96 | 0.983092 | 0.009769 | 0.009768 | 97 | 8396 | 472.4 |
| current / semchunk | 64 | 0.986111 | 0.009564 | 0.009564 | 194 | 8551 | 489.0 |
| current / semchunk | 96 | 0.993056 | 0.009976 | 0.009976 | 123 | 8409 | 474.8 |
| current / langchain | 64 | 0.962846 | 0.008598 | 0.008593 | 569 | 9301 | 504.5 |
| current / langchain | 96 | 0.981541 | 0.009026 | 0.009022 | 389 | 8941 | 499.8 |
| current / semantic-text-splitter | 64 | 0.986111 | 0.009600 | 0.009600 | 185 | 8533 | 488.4 |
| current / semantic-text-splitter | 96 | 0.993056 | 0.009851 | 0.009851 | 122 | 8407 | 476.2 |
| current / llamaindex | 64 | 0.971639 | 0.008921 | 0.008919 | 340 | 8843 | 501.5 |
| current / llamaindex | 96 | 0.984496 | 0.009424 | 0.009424 | 226 | 8615 | 491.2 |
| citation / omnichunk | 64 | 0.986111 | 0.009559 | 0.009559 | 185 | 8533 | 489.4 |
| citation / omnichunk | 96 | 0.993056 | 0.009850 | 0.009850 | 122 | 8407 | 476.2 |
| combined / omnichunk | 64 | 0.986111 | 0.009596 | 0.009596 | 185 | 8533 | 488.6 |
| combined / omnichunk | 96 | 0.993056 | 0.009850 | 0.009850 | 122 | 8407 | 476.2 |

| Candidate / tokens | Δ recall; W/T/L; 95% CI | Δ precision; W/T/L; CI | Δ IoU; W/T/L; CI |
| --- | --- | --- | --- |
| citation / 64 | +0.000000; 0/144/0; [0.000000, 0.000000] | -0.000037; 13/110/21; [-0.000078, -0.000002] | -0.000037; 13/110/21; [-0.000078, -0.000002] |
| citation / 96 | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] |

- citation / 64: changed output; all gains/losses and cost ratios are preserved in JSON.
- citation / 96: exactly unchanged passages and per-query quality.

## multilingual / article-markdown

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` @ `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`; 16 development articles and 144 queries.

| Run / adapter | Tokens | Recall | Precision | IoU | Chunks | Native passage tokens | Mean context used |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current / omnichunk | 64 | 0.958333 | 0.010309 | 0.010309 | 221 | 9756 | 487.7 |
| current / omnichunk | 96 | 0.978416 | 0.010904 | 0.010903 | 152 | 9618 | 479.7 |
| current / fixed | 64 | 0.957483 | 0.010338 | 0.010336 | 158 | 9668 | 484.6 |
| current / fixed | 96 | 0.943142 | 0.010869 | 0.010866 | 106 | 9548 | 464.4 |
| current / semchunk | 64 | 0.976389 | 0.010669 | 0.010667 | 236 | 9786 | 489.3 |
| current / semchunk | 96 | 0.986111 | 0.010942 | 0.010942 | 156 | 9626 | 480.2 |
| current / langchain | 64 | 0.897731 | 0.008924 | 0.008916 | 629 | 10572 | 503.9 |
| current / langchain | 96 | 0.972874 | 0.010300 | 0.010296 | 431 | 10176 | 497.5 |
| current / semantic-text-splitter | 64 | 0.965278 | 0.010580 | 0.010580 | 230 | 9784 | 488.3 |
| current / semantic-text-splitter | 96 | 0.979167 | 0.010919 | 0.010919 | 155 | 9630 | 475.1 |
| current / llamaindex | 64 | 0.949041 | 0.009904 | 0.009903 | 358 | 10030 | 499.4 |
| current / llamaindex | 96 | 0.972222 | 0.010423 | 0.010423 | 240 | 9794 | 491.1 |
| citation / omnichunk | 64 | 0.957583 | 0.010295 | 0.010294 | 222 | 9758 | 487.4 |
| citation / omnichunk | 96 | 0.986111 | 0.010977 | 0.010977 | 152 | 9618 | 478.9 |
| clause / omnichunk | 64 | 0.957583 | 0.010308 | 0.010307 | 222 | 9758 | 487.1 |
| clause / omnichunk | 96 | 0.979167 | 0.010934 | 0.010934 | 152 | 9618 | 479.4 |
| paragraph / omnichunk | 64 | 0.958333 | 0.010309 | 0.010309 | 221 | 9756 | 487.7 |
| paragraph / omnichunk | 96 | 0.978416 | 0.010904 | 0.010903 | 152 | 9618 | 479.7 |
| sentence / omnichunk | 64 | 0.972222 | 0.010398 | 0.010398 | 271 | 9856 | 490.1 |
| sentence / omnichunk | 96 | 0.978416 | 0.010485 | 0.010484 | 265 | 9844 | 487.9 |

| Candidate / tokens | Δ recall; W/T/L; 95% CI | Δ precision; W/T/L; CI | Δ IoU; W/T/L; CI |
| --- | --- | --- | --- |
| citation / 64 | -0.000751; 0/143/1; [-0.002252, 0.000000] | -0.000014; 19/102/23; [-0.000085, 0.000050] | -0.000015; 19/102/23; [-0.000086, 0.000050] |
| citation / 96 | +0.007695; 2/142/0; [0.000000, 0.022335] | +0.000073; 21/118/5; [-0.000013, 0.000182] | +0.000074; 21/118/5; [-0.000012, 0.000184] |
| paragraph / 64 | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] |
| paragraph / 96 | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] |

- citation / 64: changed output; all gains/losses and cost ratios are preserved in JSON.
- citation / 96: changed output; all gains/losses and cost ratios are preserved in JSON.
- paragraph / 64: exactly unchanged passages and per-query quality.
- paragraph / 96: exactly unchanged passages and per-query quality.

## multilingual / article-text

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` @ `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`; 16 development articles and 144 queries.

| Run / adapter | Tokens | Recall | Precision | IoU | Chunks | Native passage tokens | Mean context used |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current / omnichunk | 64 | 0.958333 | 0.010292 | 0.010292 | 205 | 9658 | 489.3 |
| current / omnichunk | 96 | 0.978416 | 0.010881 | 0.010880 | 137 | 9522 | 478.9 |
| current / fixed | 64 | 0.970729 | 0.010678 | 0.010676 | 157 | 9595 | 485.7 |
| current / fixed | 96 | 0.964224 | 0.010698 | 0.010695 | 105 | 9474 | 471.5 |
| current / semchunk | 64 | 0.976389 | 0.010600 | 0.010598 | 220 | 9688 | 490.2 |
| current / semchunk | 96 | 0.986111 | 0.010998 | 0.010998 | 141 | 9530 | 478.4 |
| current / langchain | 64 | 0.897731 | 0.008926 | 0.008918 | 597 | 10442 | 503.9 |
| current / langchain | 96 | 0.972874 | 0.010313 | 0.010309 | 401 | 10050 | 497.1 |
| current / semantic-text-splitter | 64 | 0.958333 | 0.010295 | 0.010295 | 205 | 9661 | 489.6 |
| current / semantic-text-splitter | 96 | 0.979167 | 0.010915 | 0.010915 | 137 | 9523 | 479.0 |
| current / llamaindex | 64 | 0.933261 | 0.009703 | 0.009699 | 355 | 9958 | 500.1 |
| current / llamaindex | 96 | 0.965278 | 0.010422 | 0.010422 | 239 | 9726 | 492.2 |
| citation / omnichunk | 64 | 0.957583 | 0.010303 | 0.010302 | 206 | 9660 | 488.6 |
| citation / omnichunk | 96 | 0.986111 | 0.010973 | 0.010973 | 137 | 9522 | 477.7 |
| clause / omnichunk | 64 | 0.957583 | 0.010290 | 0.010289 | 206 | 9660 | 488.9 |
| clause / omnichunk | 96 | 0.979167 | 0.010931 | 0.010931 | 137 | 9522 | 478.1 |
| paragraph / omnichunk | 64 | 0.958333 | 0.010292 | 0.010292 | 205 | 9658 | 489.3 |
| paragraph / omnichunk | 96 | 0.978416 | 0.010881 | 0.010880 | 137 | 9522 | 478.9 |
| sentence / omnichunk | 64 | 0.972222 | 0.010397 | 0.010397 | 269 | 9786 | 491.0 |
| sentence / omnichunk | 96 | 0.978416 | 0.010491 | 0.010490 | 265 | 9778 | 489.0 |

| Candidate / tokens | Δ recall; W/T/L; 95% CI | Δ precision; W/T/L; CI | Δ IoU; W/T/L; CI |
| --- | --- | --- | --- |
| citation / 64 | -0.000751; 0/143/1; [-0.002252, 0.000000] | +0.000010; 20/101/23; [-0.000070, 0.000098] | +0.000009; 20/101/23; [-0.000073, 0.000098] |
| citation / 96 | +0.007695; 2/142/0; [0.000000, 0.022335] | +0.000093; 22/118/4; [0.000010, 0.000200] | +0.000093; 22/118/4; [0.000010, 0.000201] |
| paragraph / 64 | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] |
| paragraph / 96 | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] | +0.000000; 0/144/0; [0.000000, 0.000000] |

- citation / 64: changed output; all gains/losses and cost ratios are preserved in JSON.
- citation / 96: changed output; all gains/losses and cost ratios are preserved in JSON.
- paragraph / 64: exactly unchanged passages and per-query quality.
- paragraph / 96: exactly unchanged passages and per-query quality.

## Pending matrix cells

- english/clause-article-markdown: not available
- english/clause-article-text: not available
- english/combined-article-markdown: paired comparison not present
- english/combined-article-text: paired comparison not present
- english/paragraph-article-markdown: not available
- english/paragraph-article-text: not available
- english/sentence-article-markdown: not available
- english/sentence-article-text: not available
- multilingual/clause-article-markdown: paired comparison not present
- multilingual/clause-article-text: paired comparison not present
- multilingual/combined-article-markdown: not available
- multilingual/combined-article-text: not available
- multilingual/sentence-article-markdown: paired comparison not present
- multilingual/sentence-article-text: paired comparison not present
