# Correlated original-file CodeSearchNet view

This supplementary view keeps the same human-authored summary queries selected for the isolated-function corpus. It indexes each complete original source file at the exact repository commit, preserving real neighboring imports, classes and functions. It adds no synthetic joins. It is a correlated view of the same questions, not an independent dataset. Always report the original isolated-function primary results alongside it.

`protocol.json` was declared before building/scoring. Original source files must be UTF-8, at most 30,000 Unicode characters, and parse as Python 3. A selected function must map uniquely by its exact source URL line anchors and AST function name, including decorators. Every AST docstring statement is removed from the complete file. A sole-body docstring becomes `pass` to retain syntactically valid Python. Gold evidence is the original selected function's complete AST line range, including original indentation, decorators, final-line comments and newline, rebased through those edits. Citations therefore address canonical transformed text, not untouched original source bytes; original source URLs and line anchors remain in metadata.

All selected queries whose files satisfy the predeclared rules are retained. Failures and exclusions are recorded in `build-audit.json`; there is no retrieval-score filter. Exact and whitespace/case-normalized query substrings remaining after docstring removal are audited without filtering. Whole-file source content is never executed.

Development retains 56 of the original 64 questions, grouped into 37 original files and 15 repository clusters. Seven queries exceed the predeclared source-size limit and one belongs to a whole file with Python 2 syntax. All source fetches and function mappings succeed. Neither exact nor normalized complete query substrings remain in transformed code. The native corpus loader validates all gold UTF-8 byte spans. The view contains 224,934 canonical source bytes, so index cost must be measured against the original-function task rather than assumed equivalent.

Development and validation are now public and observed. Validation was originally
built with the same frozen builder/protocol and sealed before the first
development-view score. At release, the transient AES key was unavailable after
agent reactivation. After the final runtime/model/settings freeze, the custodian
refetched pinned original files and reran the frozen importer, exactly recovering
the committed manifest SHA256
`dcfb7769bffade3c0bf9e3b6cc3f4d77822ce15595e668d430d606fa7c0e24b7`.
`validation-release.json` explicitly records this reconstruction rather than a
successful decryption, with no score-based edits or quality tuning. Custody was
within shared agent workspaces, not an independent external custodian. Validation
must not be reused as a new unseen tuning set.

Validation retains 56 questions in 35 files from all 16 validation repositories,
with five resource-limit and three Python 3 parse exclusions. It has zero complete
query-substring matches. Source-file/repository membership remains disjoint
across development/validation. `validation-commitment.json` and the release record
retain the pre-release commitments and recovered hashes.

Repository MIT license texts are retained per document at the exact source commit. Per-file attribution and raw original source hashes are in the manifest. The root MIT license verification and the original primary corpus's selection biases still apply. Docstring queries are retrieval proxies, whole-function gold is not complete dependency evidence, and removing documentation changes the original files. Public code may occur in model pretraining.

Reproduce with Python 3.12+ (verified with Python 3.12.14); the primary-function
importer additionally needs PyArrow 23.0.1. Follow the complete
[scratch-copy recipe](../README.md#reproduce-in-a-scratch-copy). Keep imports
outside the checkout and scoring environment. The real-file builder itself uses
the Python standard library, fetches exact-commit original sources and performs
no embeddings or retrieval scoring.

Use the primary `development/manifest.json` for the development view. For the
validation view, the historical function importer writes `code/private-validation/`;
the published corresponding directory is `code/validation/`. Pass that manifest
to `build_view.py` and choose a separate scratch output directory. Compare rebuilt
manifest hashes with the published manifests/release records; `build-audit.json`
records source outcomes, exclusions and remaining query substrings. For uncertainty,
use `repository-clusters.json`, not individual functions or files as independent
observations.
