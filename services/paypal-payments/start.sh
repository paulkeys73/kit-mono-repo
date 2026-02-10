#!/usr/bin/env bash
set -e

echo "🟢 Starting PayPal Payments services inside container..."

# Start FastAPI app
echo "🚀 Starting FastAPI app (app.main) on port 8800..."
python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8800 &

# Short delay to ensure FastAPI starts
sleep 2

# Start postData.py
echo "💡 Running postData.py..."
python app/routes/postData.py &

# Wait for all background processes and forward signals
wait -n
exit $?
