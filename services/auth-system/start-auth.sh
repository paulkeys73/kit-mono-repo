#!/usr/bin/env bash
set -euo pipefail

echo "Starting Auth Service..."

OS_NAME=$(uname -s)
if [[ "$OS_NAME" != "Linux" ]]; then
    echo "Warning: this script is intended for Linux/WSL."
    echo "Run inside WSL if you are on Windows."
    exit 1
fi

PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/venv"
APP_DIR="$PROJECT_DIR/Django-Allauth"
PORT=8034

venv_created=0
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Virtual environment not found. Creating venv..."
    python3 -m venv "$VENV_DIR"
    venv_created=1
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

if [[ -f "requirements.txt" ]]; then
    req_stamp_file=".requirements.sha256"
    should_install="$venv_created"

    if command -v sha256sum >/dev/null 2>&1; then
        current_req_hash=$(sha256sum requirements.txt | awk '{print $1}')
        previous_req_hash=""
        [[ -f "$req_stamp_file" ]] && previous_req_hash=$(<"$req_stamp_file")
        if [[ "$current_req_hash" != "$previous_req_hash" ]]; then
            should_install=1
        fi
    elif [[ ! -f "$req_stamp_file" || requirements.txt -nt "$req_stamp_file" ]]; then
        should_install=1
    fi

    if [[ "$should_install" == "1" ]]; then
        echo "Installing dependencies from requirements.txt..."
        pip install --upgrade pip
        pip install -r requirements.txt
        if command -v sha256sum >/dev/null 2>&1; then
            printf '%s\n' "$current_req_hash" > "$req_stamp_file"
        else
            touch "$req_stamp_file"
        fi
    else
        echo "Requirements unchanged; skipping dependency install."
    fi
fi

echo "Running Django migrations..."
cd "$APP_DIR"
python manage.py makemigrations
python manage.py migrate

echo "Launching Auth Service on port $PORT..."
exec python -m uvicorn Django_Settings.asgi:application --host 0.0.0.0 --port "$PORT" --reload