#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -e .
python -m uvicorn app.main:app --host "${PIPESIGHT_HOST:-0.0.0.0}" --port "${PIPESIGHT_PORT:-8000}"

