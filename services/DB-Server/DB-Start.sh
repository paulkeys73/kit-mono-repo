#!/bin/bash

# -----------------------------
# Start DB Server & Donation Stats (interactive, VS Code terminal)
# -----------------------------

set -e  # Exit on any error

# Paths
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo "🟢 Launching DB services in VS Code integrated terminal..."
echo "💡 Ensure you split your terminal (Ctrl+Shift+5) for separate panes if desired."

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
# Start services in the same VS Code terminal
# -----------------------------

echo "🚀 Launching Donation Stats Service on port 8012..."
uvicorn stats.donationStats:app --host 0.0.0.0 --port 8012 --reload &

echo "🚀 Launching Main App Service on port 8011..."
uvicorn main:app --host 0.0.0.0 --port 8011 --reload &

# Wait for both services
wait

echo "✅ DB services are running!"
echo "💡 Tip: Split your VS Code terminal (Ctrl+Shift+5) to monitor Main App and Donation Stats separately."
