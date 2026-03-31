#!/usr/bin/env bash
set -euo pipefail

# Focus mutation testing on invariant-critical logic.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHONPATH=src mutmut run \
  --paths-to-mutate src/omnichunk/windowing \
  --paths-to-mutate src/omnichunk/sizing/counter.py \
  --paths-to-mutate src/omnichunk/sizing/nws.py

PYTHONPATH=src mutmut results
