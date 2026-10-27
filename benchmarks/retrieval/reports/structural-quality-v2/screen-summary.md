# Original-development screening summary

Current reference: `ce356a251b156ed3a5b8607793224c3a4dc47ee1` (same core as the recorded final-development source). Release reference: `fa80b981efa84d1fe8ca1cbb8556aa715c14cb0e`.

All four 64/96-token × synthetic/external development cells use the same real model, native special-token accounting and 512-token context. This summary excludes new development and sealed validation; it makes no final variant selection. CIs are descriptive after screening. W/T/L is per-query candidate wins/ties/losses. Full language/category metrics, all cost ratios and named-rival comparisons are retained in JSON.

## code-atoms

Fitting leading comment + following statement association. Source `ccb9888011274f7e54e6ace896860fd6274adc1f`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.919361 / 0.081650 / 0.081377 | +0.006652; 6/174/0; [0.001079, 0.014303] | 208→217 (1.043×) | 8851→8869 (1.002×) | 487.3→489.2 |
| Synthetic / 96 | 0.900000 / 0.084591 / 0.084591 | +0.005485; 10/165/5; [-0.036561, 0.050147] | 119→127 (1.067×) | 8673→8689 (1.002×) | 478.0→476.5 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.000386; 55/76/49; [-0.000277, 0.001194] | +0.000417; 55/76/49; [-0.000266, 0.001257] | +0.017763; 8/172/0; [0.002145, 0.041051] |
| Synthetic / 96 | +0.000474; 65/61/54; [-0.002697, 0.003827] | +0.000529; 65/61/54; [-0.002654, 0.003894] | -0.000070; 10/164/6; [-0.041905, 0.044516] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ -0.007721); precision rival semchunk 0.081857 (Δ -0.000207). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.000000); precision rival semchunk 0.085022 (Δ -0.000431). Recall losses vs current: en/retry_client/q09, en/task_lease/q05, en/file_reader/q09, tr/stock_reservation/q03, tr/stock_reservation/q07.

## paragraph-atoms

Complete Markdown paragraph isolation. Source `3a347af47fb100381333875ebb4145c7322c7549`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.929376 / 0.082292 / 0.081991 | +0.016667; 3/177/0; [0.000000, 0.044444] | 208→221 (1.062×) | 8851→8877 (1.003×) | 487.3→488.9 |
| Synthetic / 96 | 0.928987 / 0.086724 / 0.086679 | +0.034472; 7/173/0; [0.005556, 0.072222] | 119→146 (1.227×) | 8673→8727 (1.006×) | 478.0→482.4 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.001028; 54/74/52; [-0.000429, 0.002925] | +0.001030; 54/74/52; [-0.000427, 0.002924] | +0.027778; 5/175/0; [0.000000, 0.061111] |
| Synthetic / 96 | +0.002606; 75/39/66; [0.000340, 0.005647] | +0.002616; 75/39/66; [0.000353, 0.005657] | +0.028916; 6/174/0; [0.005556, 0.056694] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ +0.002294); precision rival semchunk 0.081857 (Δ +0.000435). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.028987); precision rival semchunk 0.085022 (Δ +0.001702). Recall losses vs current: none.

## combined-atoms

Comment association + Markdown paragraph isolation. Source `d131578257470ac5e141a64c3063b8b7b4fab6a8`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.936028 / 0.082725 / 0.082449 | +0.023319; 9/171/0; [0.004304, 0.048679] | 208→230 (1.106×) | 8851→8895 (1.005×) | 487.3→490.6 |
| Synthetic / 96 | 0.927778 / 0.086372 / 0.086372 | +0.033263; 14/162/4; [-0.016071, 0.084410] | 119→154 (1.294×) | 8673→8743 (1.008×) | 478.0→481.3 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.001461; 74/32/74; [-0.000192, 0.003338] | +0.001488; 74/32/74; [-0.000165, 0.003362] | +0.034430; 11/169/0; [0.007985, 0.065346] |
| Synthetic / 96 | +0.002255; 88/14/78; [-0.001498, 0.006292] | +0.002309; 88/14/78; [-0.001429, 0.006313] | +0.027708; 13/163/4; [-0.017838, 0.074503] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ +0.008946); precision rival semchunk 0.081857 (Δ +0.000868). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.027778); precision rival semchunk 0.085022 (Δ +0.001350). Recall losses vs current: en/retry_client/q09, en/task_lease/q05, tr/stock_reservation/q03, tr/stock_reservation/q07.

## code-tail

Recursive pending code tail added to comment association. Source `582844eb7507728cc07839db9e01ad647bdac98c`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.919361 / 0.081650 / 0.081377 | +0.006652; 6/174/0; [0.001079, 0.014303] | 208→217 (1.043×) | 8851→8869 (1.002×) | 487.3→489.2 |
| Synthetic / 96 | 0.900000 / 0.084591 / 0.084591 | +0.005485; 10/165/5; [-0.036561, 0.050147] | 119→127 (1.067×) | 8673→8689 (1.002×) | 478.0→476.5 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.000386; 55/76/49; [-0.000277, 0.001194] | +0.000417; 55/76/49; [-0.000266, 0.001257] | +0.017763; 8/172/0; [0.002145, 0.041051] |
| Synthetic / 96 | +0.000474; 65/61/54; [-0.002697, 0.003827] | +0.000529; 65/61/54; [-0.002654, 0.003894] | -0.000070; 10/164/6; [-0.041905, 0.044516] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ -0.007721); precision rival semchunk 0.081857 (Δ -0.000207). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.000000); precision rival semchunk 0.085022 (Δ -0.000431). Recall losses vs current: en/retry_client/q09, en/task_lease/q05, en/file_reader/q09, tr/stock_reservation/q03, tr/stock_reservation/q07.

## code-isolated

Separate complete logical code blocks. Source `c127fca7ab4b68502b84d99e7952b396e730b8eb`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.919361 / 0.081615 / 0.081341 | +0.006652; 6/174/0; [0.001079, 0.014303] | 208→219 (1.053×) | 8851→8873 (1.002×) | 487.3→489.3 |
| Synthetic / 96 | 0.927778 / 0.085866 / 0.085866 | +0.033263; 11/168/1; [-0.004152, 0.084885] | 119→157 (1.319×) | 8673→8749 (1.009×) | 478.0→479.7 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.000351; 56/72/52; [-0.000397, 0.001205] | +0.000381; 56/72/52; [-0.000385, 0.001272] | +0.017763; 8/172/0; [0.002145, 0.041051] |
| Synthetic / 96 | +0.001749; 60/49/71; [-0.001090, 0.005626] | +0.001804; 60/49/71; [-0.001046, 0.005668] | +0.027708; 11/167/2; [-0.012650, 0.080798] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ -0.007721); precision rival semchunk 0.081857 (Δ -0.000242). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.027778); precision rival semchunk 0.085022 (Δ +0.000844). Recall losses vs current: en/task_lease/q05.

## combined-isolated

Separate logical code blocks + Markdown paragraphs. Source `39fb3d76a48bdc1957f465d4ccce7dae90784089`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.936028 / 0.082706 / 0.082430 | +0.023319; 9/171/0; [0.004304, 0.048679] | 208→232 (1.115×) | 8851→8899 (1.005×) | 487.3→491.0 |
| Synthetic / 96 | 0.950000 / 0.086983 / 0.086983 | +0.055485; 15/164/1; [0.009899, 0.108907] | 119→184 (1.546×) | 8673→8803 (1.015×) | 478.0→486.3 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.001442; 75/30/75; [-0.000244, 0.003335] | +0.001469; 75/30/75; [-0.000207, 0.003351] | +0.034430; 11/169/0; [0.007985, 0.065346] |
| Synthetic / 96 | +0.002865; 78/14/88; [-0.000662, 0.007088] | +0.002920; 78/14/88; [-0.000601, 0.007146] | +0.049930; 14/165/1; [0.007977, 0.101061] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ +0.008946); precision rival semchunk 0.081857 (Δ +0.000849). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.050000); precision rival semchunk 0.085022 (Δ +0.001960). Recall losses vs current: en/task_lease/q05.

## citation-clauses

citation-clauses. Source `740146d64ef8ec0078e5d32796867000b3c97a6c`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.936028 / 0.082706 / 0.082430 | +0.023319; 9/171/0; [0.004304, 0.048679] | 208→232 (1.115×) | 8851→8899 (1.005×) | 487.3→491.0 |
| Synthetic / 96 | 0.950000 / 0.086983 / 0.086983 | +0.055485; 15/164/1; [0.009899, 0.108907] | 119→184 (1.546×) | 8673→8803 (1.015×) | 478.0→486.3 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.001442; 75/30/75; [-0.000244, 0.003335] | +0.001469; 75/30/75; [-0.000207, 0.003351] | +0.034430; 11/169/0; [0.007985, 0.065346] |
| Synthetic / 96 | +0.002865; 78/14/88; [-0.000662, 0.007088] | +0.002920; 78/14/88; [-0.000601, 0.007146] | +0.049930; 14/165/1; [0.007977, 0.101061] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ +0.008946); precision rival semchunk 0.081857 (Δ +0.000849). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.050000); precision rival semchunk 0.085022 (Δ +0.001960). Recall losses vs current: en/task_lease/q05.

## clause-first

clause-first. Source `638ca44bf24893a6e6b2040e5b92e278a5fc3f0e`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.936028 / 0.082706 / 0.082430 | +0.023319; 9/171/0; [0.004304, 0.048679] | 208→232 (1.115×) | 8851→8899 (1.005×) | 487.3→491.0 |
| Synthetic / 96 | 0.950000 / 0.086983 / 0.086983 | +0.055485; 15/164/1; [0.009899, 0.108907] | 119→184 (1.546×) | 8673→8803 (1.015×) | 478.0→486.3 |
| External / 64 | 0.979167 / 0.012791 / 0.012791 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→64 (1.000×) | 3030→3030 (1.000×) | 486.1→486.1 |
| External / 96 | 0.979167 / 0.012891 / 0.012891 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→45 (1.000×) | 2992→2992 (1.000×) | 471.9→471.9 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.001442; 75/30/75; [-0.000244, 0.003335] | +0.001469; 75/30/75; [-0.000207, 0.003351] | +0.034430; 11/169/0; [0.007985, 0.065346] |
| Synthetic / 96 | +0.002865; 78/14/88; [-0.000662, 0.007088] | +0.002920; 78/14/88; [-0.000601, 0.007146] | +0.049930; 14/165/1; [0.007977, 0.101061] |
| External / 64 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ +0.008946); precision rival semchunk 0.081857 (Δ +0.000849). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.050000); precision rival semchunk 0.085022 (Δ +0.001960). Recall losses vs current: en/task_lease/q05.

## sentence-atoms

sentence-atoms. Source `7fa55e2c02cfcc64f9b25439b53dab1dfa3e5622`.

| Corpus / tokens | Recall / precision / IoU | Δ recall vs current; W/T/L; 95% CI | Chunks vs current | Passage tokens vs current | Mean context tokens vs current |
| --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | 0.936028 / 0.082706 / 0.082430 | +0.023319; 9/171/0; [0.004304, 0.048679] | 208→232 (1.115×) | 8851→8899 (1.005×) | 487.3→491.0 |
| Synthetic / 96 | 0.950000 / 0.086983 / 0.086983 | +0.055485; 15/164/1; [0.009899, 0.108907] | 119→184 (1.546×) | 8673→8803 (1.015×) | 478.0→486.3 |
| External / 64 | 0.979167 / 0.012794 / 0.012794 | +0.000000; 0/48/0; [0.000000, 0.000000] | 64→89 (1.391×) | 3030→3080 (1.017×) | 486.1→490.3 |
| External / 96 | 0.979167 / 0.012762 / 0.012762 | +0.000000; 0/48/0; [0.000000, 0.000000] | 45→88 (1.956×) | 2992→3078 (1.029×) | 471.9→484.1 |

| Corpus / tokens | Δ precision vs current; W/T/L; CI | Δ IoU vs current; W/T/L; CI | Δ recall vs v2.2.0; W/T/L; CI |
| --- | --- | --- | --- |
| Synthetic / 64 | +0.001442; 75/30/75; [-0.000244, 0.003335] | +0.001469; 75/30/75; [-0.000207, 0.003351] | +0.034430; 11/169/0; [0.007985, 0.065346] |
| Synthetic / 96 | +0.002865; 78/14/88; [-0.000662, 0.007088] | +0.002920; 78/14/88; [-0.000601, 0.007146] | +0.049930; 14/165/1; [0.007977, 0.101061] |
| External / 64 | +0.000003; 25/2/21; [-0.000207, 0.000237] | +0.000003; 25/2/21; [-0.000207, 0.000237] | +0.000000; 0/48/0; [0.000000, 0.000000] |
| External / 96 | -0.000129; 17/1/30; [-0.000424, 0.000212] | -0.000129; 17/1/30; [-0.000424, 0.000212] | +0.000000; 0/48/0; [0.000000, 0.000000] |

- Synthetic 64: strongest aggregate recall rival langchain 0.927082 (candidate Δ +0.008946); precision rival semchunk 0.081857 (Δ +0.000849). Recall losses vs current: none.
- Synthetic 96: strongest aggregate recall rival semchunk/semantic-text-splitter 0.900000 (candidate Δ +0.050000); precision rival semchunk 0.085022 (Δ +0.001960). Recall losses vs current: en/task_lease/q05.

## Redundant rule and interpretation

Reject the extra code-tail rule as unnecessary for the measured workload: all passages and per-query quality are identical to code-atoms.

External scores remain unchanged by these code/Markdown-specific rules. A new plain-English corpus cannot establish a direct code-rule advantage because that code path is absent. Evaluate new development before selecting a variant; reserve sealed validation for the frozen final experiment. Do not describe precision gains caused only by lower context utilization as an unqualified quality advantage.
