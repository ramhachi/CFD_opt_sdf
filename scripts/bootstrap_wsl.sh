#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[dev]"

cat <<'MSG'

Environment ready.
Try:
  ./.venv/bin/cfd-sdf init examples/front_wing
  ./.venv/bin/cfd-sdf build-sdf examples/front_wing/project.yaml
  ./.venv/bin/cfd-sdf check-constraints examples/front_wing/project.yaml
MSG
