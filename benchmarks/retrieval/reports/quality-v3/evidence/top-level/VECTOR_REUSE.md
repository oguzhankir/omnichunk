# External frozen-vector reuse producer

`extend_dense_vectors.py` is research orchestration outside the frozen library and
benchmark harness. It prepares a new candidate-required artifact by reusing trusted
baseline vectors under exact `(role, SHA-256 of UTF-8 input text)` keys. Unrelated
baseline records are omitted. Neither baseline artifacts nor existing output files
are overwritten.

Use the frozen candidate checkout for both `--harness-root` and `--runtime-root`
when preparing candidate vectors; use the corresponding baseline checkout as the
runtime when preparing an additional baseline strategy. The harness must remain
frozen. Pass `--corpus`, `--split dev|test`, comma-separated `--tools`,
`--chunk-sizes 64 96`, a pinned local `--model-dir`, explicit `--model-id` and
`--model-revision`, original standard producer `--prior` JSON/JSON.gz artifact,
its committed compressed-file `--prior-sha256`, and a new `--output` path.
`--batch-size 32`, `--cpu-threads 2` and the standard no-prompt preprocessing
revision are the defaults. All token budgets include model special tokens.

The prior must come from the frozen standard producer. Validation checks artifact
schema, role/digest uniqueness, model/corpus/preprocessing identity, full snapshot
file hashes, installed package versions, producer source hash, pipeline/prompt/
normalization/device/thread policies, maximum full-input length, encoded-record
cardinality and each role's cardinality. Complete installed-package file hashes
are bound by the separate frozen environment audit, not inferred from versions.

Every requested input, including cache hits, is checked with the full tokenizer
and native model token IDs/attention masks. Overflow or transformed/truncated inputs
fail. Only missing role/text inputs reach `model.encode` using the same pinned CPU
Transformer + mean Pooling (+ Normalize), empty prompt and unnormalized output
policy as the frozen producer. All vector dimensions and values are validated.
Model file hashes and package versions are checked again before serialization.

The frozen artifact builder deduplicates and orders candidate inputs. Publication
uses a staged artifact, a byte-exact audit of reused vector payloads and an atomic
no-overwrite link. Metadata records prior/source hashes, per-role reuse/new input
and token counts, actual encoder calls and actual sparse batch sizes. Per-candidate
total workloads are separate. Baseline model encoding times are not copied or
attributed to a candidate. Cache-miss batching can differ from full preparation
batching, so newly computed floats need not be bit-identical to a complete pass.
This is an experiment resource optimization, not an algorithm latency claim. The
producer loads baseline records and the model into memory; it is not a bounded
memory streaming implementation.

`test_extend_dense_vectors.py` contains integrity tests using explicit toy vectors;
those tests are not model-quality evidence. `extension-smoke-final/command.json`
records the real pretrained development smoke command; `audit.json` records actual
reused/new work and an independent raw-vector reuse audit. No validation data was
opened for the smoke test.

For portable integrity tests, set `OMNICHUNK_FROZEN_HARNESS=/path/to/frozen/checkout`
and run `pytest -q test_extend_dense_vectors.py` beside the producer. The default
expects a sibling `frozen-candidate` checkout.
