#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Warning: this script is intended for Linux/WSL."
  echo "Run inside WSL if you are on Windows."
  exit 1
fi

venv_created=0
if [[ ! -d "venv" ]]; then
  python3 -m venv venv
  echo "Virtual environment created."
  venv_created=1
fi

source venv/bin/activate

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

echo "Launching Donation Stats Service on port 8012..."
python -m uvicorn stats.donationStats:app --host 0.0.0.0 --port 8012 --reload &

echo "Launching Main App Service on port 8011..."
python -m uvicorn main:app --host 0.0.0.0 --port 8011 --reload &

wait