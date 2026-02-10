#!/usr/bin/env bash
set -e

# -----------------------------
# WebSocket Server Launcher
# Interactive, WSL + Windows aware
# -----------------------------

# Paths
PROJECT_WSL="/mnt/e/WebSocket-Server"
VENV_DIR="$PROJECT_WSL/venv"

MAIN_APP_MODULE="main:app"
MAIN_APP_PORT=8009

DONATE_STATS_MODULE="donate_stat:app"
DONATE_STATS_PORT=8008

echo "🟢 Launching WebSocket-Server project..."

# -----------------------------
# Activate virtual environment
# -----------------------------
if [[ -f "$VENV_DIR/bin/activate" ]]; then
    echo "🟢 Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
else
    echo "❌ Virtual environment not found at $VENV_DIR"
    exit 1
fi

# -----------------------------
# Start services in background
# -----------------------------
cd "$PROJECT_WSL"

echo "🚀 Launching Main WebSocket App on port $MAIN_APP_PORT..."
python -m uvicorn "$MAIN_APP_MODULE" --host 0.0.0.0 --port "$MAIN_APP_PORT" --reload &

echo "🚀 Launching Donation Stats WS App on port $DONATE_STATS_PORT..."
python -m uvicorn "$DONATE_STATS_MODULE" --host 0.0.0.0 --port "$DONATE_STATS_PORT" --reload &

# -----------------------------
# Wait for both to finish
# -----------------------------
wait

echo "✅ WebSocket services are running!"
echo "💡 Tip: Use Ctrl+Shift+5 in VS Code terminal to split panes for monitoring Main App and Donation Stats WS separately."
