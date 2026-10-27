# Publication checks

These records supplement the immutable `../evidence/` archive. They bind the
published report, raw numeric comparisons, plot coordinates, restored artifact
bytes, package contents and the CI-only NLTK asset repair. They do not introduce
new retrieval runs or change the frozen runtime.

From the report directory, run the portable restoration regressions with only
Python's standard library:

```bash
python -B -m unittest discover -s publication-audits -p test_restore_evidence.py
```

The independent report/plot audit producers retain their original experiment
paths. Their JSON records identify input hashes and checks; use the storage map
and restoration helper to locate the corresponding published artifacts.

Final hosted checks and review results belong to
[PR #39](https://github.com/oguzhankir/omnichunk/pull/39), since the publication
commit cannot embed a check result for its own future commit hash.
