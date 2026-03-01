#!/usr/bin/env bash
set -e

echo "🟢 Starting Alert Server inside container..."

# Start FastAPI app
echo "🚀 Launching main:app on port 8099..."
python -m uvicorn main:app \
    --host 0.0.0.0 \
    --port 8099 &

# Wait for background process and forward signals properly
wait -n
exit $?
