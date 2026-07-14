#!/usr/bin/env bash
# Start the private LLM Wiki locally.
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "› Creating virtual environment…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "› Installing dependencies (first run only)…"
pip install -q -r requirements.txt

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
echo "› My-PI running privately at http://${HOST}:${PORT}"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
