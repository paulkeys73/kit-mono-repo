#!/usr/bin/env bash
set -e

echo "🟢 Starting WebSocket services inside container..."

echo "🚀 Starting Main WebSocket App on port 8009..."
python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8009 \
  &

echo "🚀 Starting Donation Stats WS App on port 8008..."
python -m uvicorn donate_stat:app \
  --host 0.0.0.0 \
  --port 8008 \
  &

# Forward signals properly
wait -n
exit $?
