#!/usr/bin/env bash
# Common macOS/Linux setup. Use --metal on an Apple Silicon Mac.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
extras="dev"
if [[ "${1:-}" == "--metal" ]]; then
    if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
        echo "--metal requires an Apple Silicon Mac." >&2
        exit 2
    fi
    extras="dev,metal"
elif [[ $# -gt 0 ]]; then
    echo "Usage: bash scripts/bootstrap.sh [--metal]" >&2
    exit 2
fi

if command -v uv >/dev/null 2>&1; then
    if [[ ! -x .venv/bin/python ]]; then
        uv venv --python 3.12
    fi
    uv pip install --python .venv/bin/python -e ".[$extras]"
else
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -e ".[$extras]"
fi

echo "Ready: .venv/bin/cfd-sdf research doctor"
