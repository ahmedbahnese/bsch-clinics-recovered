#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export BSCH_OPERATING_MODE=standalone_offline
export BSCH_HOST="${BSCH_HOST:-127.0.0.1}"
export BSCH_PORT="${BSCH_PORT:-4173}"
cd "$ROOT"
exec python3 app.py
