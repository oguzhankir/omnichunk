# Turkish passage retrieval from Belebele

This corpus adapts the independently authored Belebele multiple-choice reading-comprehension pairs into passage retrieval. The query is the original Turkish question, without answer choices. The indexed document is exactly the originating Turkish passage, without headings or answer labels. Gold evidence is the entire passage, not an independently audited minimal answer-support span. Consequently, byte recall here measures recovery of the original passage and can penalize omitting irrelevant sentences. It does not measure multiple-choice accuracy or generated answers. Some question stems depend on their omitted answer choices to disambiguate the intended topic, so query-only retrieval can be underspecified; this limitation is not repaired by post-score question filtering.

The source is `facebook/belebele` at revision `7899cdfa4e1e0d733fd77c848e2c273cb1d32be2` (CC-BY-SA 4.0). The dataset's human annotation and multilingual translation process is described in its original README; it is not original Turkish production traffic. Authors: Lucas Bandarkar et al., *The Belebele Benchmark: a Parallel Reading Comprehension Dataset in 122 Language Variants* (2023). Original FLORES/Wikipedia/Wikibooks links are retained per document for attribution. `upstream.json` records exact download URLs, sizes and SHA256 fingerprints.

Selection was declared in `../belebele_protocol.json` before scoring. Of 488 unique original passage/source links, 412 contain two questions. None overlaps the previous published corpora under the recorded normalized full-passage/substring and normalized-question checks against both paired English and Turkish. The first 120 eligible source links in namespace-SHA256 order are selected, alternated into development/validation, with two questions per passage. Each split has 60 source documents and 120 questions. All passage/source links and normalized question texts are disjoint across splits. There are no synthetic paragraph joins or model-generated queries. Multiple passages form retrieval distractors within each split.

`development/manifest.json` and `validation/manifest.json` are now public. Validation was released at 2026-10-27T12:50:01.674929Z only after final runtime/model/settings freeze `54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334` and clean code/security reviews. Its manifest exactly matches the previously committed SHA256 `7e4f9a1916689380289ce437f22df0a4e30677a62a15d3ea83256f84a8706b8f`; `validation-release.json` records source-hash, UTF-8 quote and split-overlap checks. During selection the validation archive remained encrypted outside public staging, with the key held by the corpus custodian agent. This was procedural blindness within a shared agent workspace, not an independent external custodian. Validation is now observed data and must not be reused as an unseen tuning set. No validation key or ciphertext is published; model pretraining overlap remains possible.

`tokenizer-preflight.json` records that all 900 upstream Turkish questions fit within the chosen multilingual MiniLM encoder's 128-token limit (including native special tokens); length measurements do not choose or filter examples. The builder validates exact UTF-8 evidence bytes, document hashes, and corpus manifest conformance. No score or embedding was used to create the split.


Reproduction uses Python 3.12+ (verified with Python 3.12.14); this importer uses
the standard library and the pinned OmniChunk corpus loader. Follow the parent
[scratch-copy recipe](../README.md#reproduce-in-a-scratch-copy). PyArrow 23.0.1 is
needed only for the separate CodeSearchNet import. `--include-validation` writes
both `development/` and `validation/` under the supplied scratch output directory;
without it, only development is reconstructed. The builder verifies exact
committed manifest hashes and never performs embeddings or retrieval scoring.
