Restore original evidence files with Python 3.10+ and its standard library:

From this directory, first download the pinned snapshot and verify its evidence files:

```bash
python download_evidence.py
```

The restored `evidence/` directory is ignored by Git. For an offline restore, pass
`--archive /path/to/snapshot.tar.gz` using the pinned GitHub source archive.

Then restore the original files:

```bash
python restore_evidence.py --archive-root ./evidence --output-dir ./restored
```

The helper verifies stored, decoded and original-source hashes and sizes before
writing. Original gzip files retain their exact compressed bytes. Sources from
`/workspace/work/<relative>` become `restored/<relative>`; other sources are placed
under `restored/other-sources/<published-relative-path>`. Identical existing files
are skipped; conflicting files and unsafe or symlinked paths are rejected.
Restoration does not execute archived scripts or download models.

With Matplotlib installed, regenerate the figures from the restored inputs:

```bash
OMNICHUNK_V3_EVIDENCE="$PWD/restored/omnichunk-v3" \
OMNICHUNK_PLOT_OUTPUT="$PWD/regenerated-plots" \
python restored/omnichunk-v3/plot_validation_final.py
```

Compare the generated CSV/SVG hashes with `restored/omnichunk-v3/drafts/plot-audit.json`.
The archived plotting script records hashes in the new output directory too.
