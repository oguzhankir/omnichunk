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

The target for the scoped modules is **at least 85% kill rate**. This is a target,
not a measured repository baseline or an enforced CI release gate. The current
workflows do not run mutation testing or enforce that percentage.

Record the commit, command, mutation counts and tool version with each result.
Investigate surviving mutants and report equivalent mutants, timeouts and skipped
cases separately. Establish a reproducible baseline before making this a release
gate; meeting the percentage alone does not prove the chunk invariants are correct.
