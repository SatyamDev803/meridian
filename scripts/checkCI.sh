#!/usr/bin/env bash
# Local mirror of CI. Run once before pushing.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
echo "== ruff lint";   "$PY" -m ruff check meridian tests
echo "== ruff format"; "$PY" -m ruff format --check meridian tests
echo "== pytest";      "$PY" -m pytest -q -p no:cacheprovider
echo "== web typecheck and build"
(cd web && pnpm typecheck && NEXT_PUBLIC_API_BASE= pnpm build >/dev/null)
echo "All checks passed."
