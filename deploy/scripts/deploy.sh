#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$APP_ROOT/backend"
if command -v python3.11 >/dev/null 2>&1; then
  python3.11 -m venv .venv
else
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
mkdir -p data/provider-cwd data/runtime

cd "$APP_ROOT/frontend"
npm ci
npm run build

