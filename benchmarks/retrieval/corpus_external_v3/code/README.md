# CodeSearchNet Python MIT subset, v3

This is a development/validation corpus derived from the original CodeSearchNet
Python validation and test partitions, at Hugging Face dataset revision
`bd0cf261e357a3eb5c8fba490d23ec1a1cd59555`. The upstream parquet bytes match their
Git LFS SHA256 values (see `upstream-audit.json`). CodeSearchNet's authors are
Hamel Husain, Ho-Hsiang Wu, Tiferet Gazit, Miltiadis Allamanis and Marc Brockschmidt
(2019), https://github.com/github/CodeSearchNet and arXiv:1909.09436.

The dataset does not relicense upstream code. Each selected repository's root
MIT license was obtained at the exact commit appearing in its source-function
URLs, and is retained in that corpus's `licenses/` directory. Manifest records
provide the original repository, function name, file path, commit URL and license
checksum. Every selected function's commit matches its recorded license commit.
Code is used as data and is never executed.

Each split has 64 individual function documents from 16 repositories, four
functions per repository. The selected upstream validation and test repositories do not overlap. All code is original human-authored open-source Python, and
queries are the first blank-line-separated paragraphs of original human-authored documentation, not assistant-generated
questions. The task is documentation-to-function retrieval; docstrings are a
proxy for user queries, not independently annotated code-QA questions.

Transformation: parse the extracted function with Python's AST; remove source
ranges belonging to AST docstring statements, including nested definitions;
retain remaining source, strip boundary whitespace and append one newline.
No query text or neighboring functions are inserted. Gold evidence is the whole
transformed function in exact half-open UTF-8 byte coordinates. Whole-function
gold tests completeness of retrieved code, but does not establish dependency-
complete evidence or answer correctness. A method may be extracted without its
original class/import context. This is a transformed function-retrieval task,
not a full-repository assistant workload.

Selection uses the predeclared hash namespace, eligibility rules and MIT license
filter in `protocol.json`, before any scoring. The initial bundle-document plan
was amended at the root agent's request before data exposure/scoring; function
selection and split membership did not change. No synthetic bundles are present
in the final corpus. Sources and normalized queries are checked for overlap.
Both development and validation are now public and observed. Validation was
released only after the recorded runtime/model/settings freeze and clean
code/security reviews. The transient AES key was unavailable after agent
reactivation, so the custodian reconstructed the corpus from pinned upstream
inputs and exact-commit repository licenses after the freeze. Its manifest
exactly recovered the previously committed SHA256
`ddbe1ee7172576c20339ed6e261bc066bb4269612b2f04232cd89a07498be46f`.
`validation-release.json` discloses that recovery and the release checks; it was
not a successful decryption. No source/settings changes or score-based selection
were used in recovery. This is procedural custody in a shared agent workspace,
not an independent external custodian. Validation must not be reused as a new
unseen tuning set. Public CodeSearchNet sources may overlap model pretraining.

Reproduction uses Python 3.12+ and PyArrow 23.0.1; it was verified with
Python 3.12.14. Follow the [scratch-copy commands](../README.md#reproduce-in-a-scratch-copy)
in the parent README: the importer writes into its own directory, so do not run
it in the checkout or scoring environment. `reproduce.py` invokes `build.py` and
`individual_functions.py`, defaults to development only, and checks the canonical
manifest hashes against `expected-manifests.json`. `--include-validation` also
writes the historical `private-validation/` directory; the published equivalent
is named `validation/`. This is a directory-name difference, not another split.
The two pinned parquets are identified in `upstream-audit.json`; exact-commit root
MIT licenses are fetched during import. Network/license disappearance can prevent
a rebuild and must not silently pass with different data. Retained attributions,
protocols and immutable data hashes remain part of the evidence. MIT-only
eligibility is a selection bias. Use repository clusters for uncertainty, not 64
independent functions.

Query policy was amended before any valid retrieval score: full documentation exceeded the native 128-token query limit on 6 development and 7 validation queries. The exact transform is `full.split(chr(10)+chr(10))[0].strip()`; it is not a regex or first-line heuristic. All 64 selected queries in each split fit after this transform (maximum 98 development / 101 validation), so no function was filtered or reselected. Superseded full-docstring manifests and commitments remain immutable. Earlier preliminary summary counts were computed with incorrectly escaped newline literals and were corrected before scoring.
