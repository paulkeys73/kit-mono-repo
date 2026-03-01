#!/usr/bin/env bash
set -e

# -----------------------------
# Alert Server Launcher
# -----------------------------
SUPPORT_PROJECT_WIN="F:\\my-servers\\alert-server\\support"
SUPPORT_PROJECT_WSL="/mnt/f/my-servers/alert-server/support"
VENV_DIR="venv"
PYTHON_CMD="python3"
UVICORN_CMD="uvicorn main:app --host 0.0.0.0 --port 8099 --reload"

# -----------------------------
# Detect environment
# -----------------------------
OS_NAME=$(uname -s)
if [[ "$OS_NAME" == *"Linux"* && -f /proc/version && "$(cat /proc/version)" == *"Microsoft"* ]]; then
    ENV="WSL"
elif [[ "$OS_NAME" == "Linux" ]]; then
    ENV="Linux"
else
    ENV="Windows"
fi
echo "🟢 Detected environment: $ENV"

# -----------------------------
# Run alert server in background
# -----------------------------
run_alert_server() {
    local PROJECT_DIR=$1
    echo "🟢 Launching Alert Server in $PROJECT_DIR..."
    (
        cd "$PROJECT_DIR"
        # Activate virtual environment
        if [[ "$ENV" == "Windows" ]]; then
            echo "💡 Windows detected — activating venv"
            call "$VENV_DIR/Scripts/activate"
            $PYTHON_CMD -m $UVICORN_CMD
        else
            echo "💡 Linux/WSL detected — activating venv"
            source "$VENV_DIR/bin/activate"
            $PYTHON_CMD -m $UVICORN_CMD
        fi
    ) &
}

# -----------------------------
# Launch
# -----------------------------
if [[ "$ENV" == "WSL" || "$ENV" == "Linux" ]]; then
    run_alert_server "$SUPPORT_PROJECT_WSL"
elif [[ "$ENV" == "Windows" ]]; then
    run_alert_server "$SUPPORT_PROJECT_WIN"
else
    echo "❌ Unknown environment — cannot launch Alert Server"
    exit 1
fi

echo "✅ Alert Server launched in background on port 8099!"
wait
