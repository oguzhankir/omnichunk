# Mutation testing

This project uses `mutmut` to measure test effectiveness on invariant-critical logic.

## Scope

Mutation testing is intentionally limited to:

- `src/omnichunk/windowing/`
- `src/omnichunk/sizing/counter.py`
- `src/omnichunk/sizing/nws.py`

Test and benchmark files are excluded from mutation targets.

## Run locally

```bash
pip install -e ".[dev]"
bash scripts/run_mutmut.sh
```

You can also run a narrower command directly:

```bash
PYTHONPATH=src mutmut run --paths-to-mutate src/omnichunk/windowing
PYTHONPATH=src mutmut results
```

## Reading the report

- `killed`: a test failed after mutation (good)
- `survived`: mutation did not fail tests (coverage gap)
- `timeout` / `suspicious`: usually indicates flaky or slow tests

Investigate each surviving mutant by running:

```bash
PYTHONPATH=src mutmut show <mutant-id>
```

Add or strengthen tests when a mutant survives for behavior that should be protected.

## Quality target

For the scoped modules above, the expected baseline is **>85% kill rate**.

- Below 85%: strengthen tests before merging
- 85% or above: acceptable for release gating
