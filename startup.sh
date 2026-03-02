#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -x "./venv/bin/python" ]; then
  PYTHON_BIN="./venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi

HOST="${TOPIC_API_HOST:-0.0.0.0}"
PORT="${TOPIC_API_PORT:-8787}"

# Publish steps are disabled by default for now.
export ENABLE_WP_POST="${ENABLE_WP_POST:-0}"
export ENABLE_BING_NOTIFY="${ENABLE_BING_NOTIFY:-0}"
export ENABLE_SITEMAP_UPDATE="${ENABLE_SITEMAP_UPDATE:-0}"

echo "Starting topic API on ${HOST}:${PORT} (WP=${ENABLE_WP_POST}, BING=${ENABLE_BING_NOTIFY}, SITEMAP=${ENABLE_SITEMAP_UPDATE})"
exec "$PYTHON_BIN" topic_api.py --host "$HOST" --port "$PORT"
