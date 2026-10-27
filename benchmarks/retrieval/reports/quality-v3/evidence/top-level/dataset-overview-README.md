# External passage and function retrieval corpora, v3

This directory contains development and released validation data. **Validation is
now observed and must not be reused as a new unseen tuning set.** Dataset import
and source/evidence verification do not establish retrieval quality; results and
uncertainty belong in the completed benchmark report.

| Corpus | Development / validation | Evidence and license |
| --- | --- | --- |
| `turkish/` | 60 / 60 passages, 120 / 120 questions | Original Belebele Turkish question stems; whole originating passage as gold. CC-BY-SA-4.0, original contributor links retained. |
| `code/` | 64 / 64 individual functions and queries, 16 / 16 repository clusters | Human documentation-summary queries; indexed AST docstrings removed; whole transformed function as gold. Exact-commit repository MIT licenses retained. |
| `code-files/` | 37 / 35 original files, 56 / 56 eligible existing queries, 15 / 16 repository clusters | Correlated real-file view of the same code questions, with real neighboring code and rebased whole-function gold. Same MIT source attribution. |

The two code views are correlated, not independent datasets. Docstrings are query
proxies, and whole-function gold does not establish complete dependency evidence
or answer correctness. Turkish question stems omit multiple-choice options and
can be underspecified; whole-passage gold is not independently audited minimal
support. Each corpus README records transformations, eligibility and exclusions.

Selection and query-policy amendments preceded valid retrieval scores. Original
passages/repositories are disjoint across splits. `candidate-source-rejections.json`
records why XQuAD and TQuAD were not adopted. Corpus manifests contain exact source
hashes and UTF-8 gold ranges; license/notice files and per-source links preserve
attribution. The dataset licenses do not relicense third-party source material.

Validation release followed frozen runtime/harness commit
`d0bd4b5ea10ff458313a82b3340c8f1a3f49e572`, recorded in
`freeze-before-validation-v3.json` with SHA256
`54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334`.
Model/settings fingerprints, completed code/security reviews and comparison
references were fixed before release; the evidence report retains
`reference-choices-before-validation.json` and
`reference-selection-commitment.json`. Per-corpus `validation-release.json` records
the committed/recovered manifest hashes and verification outcomes.

Custody was procedural within shared agent workspaces, not an external custodian.
Turkish validation was decrypted with its retained key after the freeze. For both
code views, transient AES keys were unavailable after agent reactivation; the
custodian reconstructed the data from pinned upstream inputs and exact source
commits after the freeze, recovering both previously committed manifest hashes
exactly. Those release records disclose the recovery. Public upstream availability
and possible model pretraining overlap limit blindness claims. No private keys,
encrypted archives, model weights, embeddings or upstream parquets are published.

## Reproduce in a scratch copy

Use **Python 3.12+**; imports were verified with Python 3.12.14 and PyArrow 23.0.1.
These are research-import dependencies, not OmniChunk runtime requirements. Code
import writes into its own directory, so run it in a scratch copy, outside the
checkout and scoring environment. Set `OMNICHUNK_REPO` to an OmniChunk checkout
containing the earlier manifests pinned in `turkish/previous-manifests.json`.

```bash
IMPORT_WORK="$(mktemp -d)"
cp -R "$OMNICHUNK_REPO/benchmarks/retrieval/corpus_external_v3" "$IMPORT_WORK/corpora"
python3 -m venv "$IMPORT_WORK/venv"
"$IMPORT_WORK/venv/bin/pip" install pyarrow==23.0.1
cd "$IMPORT_WORK/corpora"

"$IMPORT_WORK/venv/bin/python" download_upstream.py turkish
"$IMPORT_WORK/venv/bin/python" turkish/build.py \
  --repo-root "$OMNICHUNK_REPO" --output-dir "$IMPORT_WORK/turkish-rebuilt" \
  --include-validation

"$IMPORT_WORK/venv/bin/python" download_upstream.py code
"$IMPORT_WORK/venv/bin/python" code/reproduce.py --include-validation

"$IMPORT_WORK/venv/bin/python" code-files/build_view.py \
  --manifest code/development/manifest.json \
  --output-dir "$IMPORT_WORK/code-files-development" \
  --source-cache "$IMPORT_WORK/original-files"
"$IMPORT_WORK/venv/bin/python" code-files/build_view.py \
  --manifest code/private-validation/manifest.json \
  --output-dir "$IMPORT_WORK/code-files-validation" \
  --source-cache "$IMPORT_WORK/original-files"
```

Downloads use pinned revisions, sizes and hashes. The Turkish importer validates
the earlier corpus fingerprints and exact rebuilt manifests. The code importer
fetches exact-commit root MIT licenses, applies the frozen first-paragraph query
policy, and checks canonical manifest hashes through `expected-manifests.json`.
Network/license disappearance must not silently produce a different successful
rebuild. Parsed source code is data and is never executed.

`--include-validation` is explicit; without it the Turkish and isolated-code
commands rebuild development only. The historical isolated-code importer writes
its second split as `code/private-validation/`; publication uses `code/validation/`.
They represent the same committed manifest/data, not different splits. The
Turkish importer writes `validation/` under its selected output directory. The
real-file builder uses the output directory supplied on the command line. Compare
all rebuilt manifest hashes with the published manifests and release records.
