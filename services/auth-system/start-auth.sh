#!/bin/bash

# -----------------------------
# Start Django Auth Service (ASGI, uvicorn)
# -----------------------------

set -e  # Exit on any error

echo "🟢 Starting Auth Service..."

# -----------------------------
# Check OS
# -----------------------------
OS_NAME=$(uname -s)
if [[ "$OS_NAME" != "Linux" ]]; then
    echo "⚠️ Warning: This script is intended for Linux/WSL."
    echo "Please run inside WSL if you are on Windows."
    exit 1
fi

# -----------------------------
# Path
# -----------------------------
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/venv"
APP_DIR="$PROJECT_DIR/Django-Allauth"
PORT=8034

# -----------------------------
# Create virtual environment if missing
# -----------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    echo "💡 Virtual environment not found. Creating venv..."
    python3 -m venv "$VENV_DIR"
    echo "✅ Virtual environment created at $VENV_DIR"
fi

# -----------------------------
# Activate virtual environment
# -----------------------------
echo "🟢 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# -----------------------------
# Install dependencies
# -----------------------------
if [[ -f "requirements.txt" ]]; then
    echo "📦 Installing dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# -----------------------------
# Database migrations
# -----------------------------
echo "🛠 Running Django migrations..."
cd "$APP_DIR"
python manage.py makemigrations
python manage.py migrate

# -----------------------------
# Start Django ASGI server with uvicorn
# -----------------------------
echo "🚀 Launching Auth Service on port $PORT..."
python -m uvicorn Django_Settings.asgi:application --host 0.0.0.0 --port "$PORT" --reload

echo "✅ Auth Service running! Access it at http://localhost:$PORT"
