#!/usr/bin/env bash
# Run this before every commit/push. Exits non-zero if anything fails.
#   ./scripts/check.sh                 Python tests only (fast)
#   RUN_ANCHOR=1 ./scripts/check.sh    also run the Solana program tests
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== Python tests"
python -m pytest -q

if [[ "${RUN_ANCHOR:-0}" == "1" ]]; then
  echo "== Anchor tests"
  ./scripts/prepare.sh
  anchor test
else
  echo "(skipped Anchor tests; use RUN_ANCHOR=1 to include them)"
fi

echo "All checks passed."
