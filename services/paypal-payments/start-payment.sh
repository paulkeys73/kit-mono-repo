#!/usr/bin/env bash
set -e

# ---------------------------
# PayPal Payments Launcher (interactive)
# VS Code integrated terminal, WSL + Linux aware
# ---------------------------

# Paths
PROJECT_WSL="/mnt/e/paypal-payments"
VENV_DIR="$PROJECT_WSL/venv"
APP_MODULE="app.main"
APP_PORT=8800
POSTDATA_SCRIPT="$PROJECT_WSL/app/routes/postData.py"

echo "🟢 Launching PayPal Payments project in VS Code terminal..."
echo "💡 Split your terminal (Ctrl+Shift+5) if you want to monitor the app and postData.py separately."

# Check if running on Linux/WSL
OS_NAME=$(uname -s)
if [[ "$OS_NAME" != "Linux" ]]; then
    echo "⚠️ Warning: This script is intended for Linux/WSL."
    echo "Please run inside WSL if you are on Windows."
    exit 1
fi

# Activate virtual environment
if [[ -f "$VENV_DIR/bin/activate" ]]; then
    echo "🟢 Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
else
    echo "❌ Virtual environment not found at $VENV_DIR"
    exit 1
fi

# -----------------------------
# Start services in the same terminal
# -----------------------------

echo "🚀 Starting FastAPI app ($APP_MODULE) on port $APP_PORT..."
python3 -m uvicorn "$APP_MODULE:app" --host 0.0.0.0 --port "$APP_PORT" --reload &

sleep 2  # small delay to allow FastAPI to start

echo "💡 Running postData.py..."
python3 "$POSTDATA_SCRIPT" &

# Wait for all background processes
wait

echo "✅ PayPal Payments services are running!"
echo "💡 Tip: Use Ctrl+Shift+5 in VS Code terminal to split panes if you want separate monitoring for the FastAPI app and postData.py."
