#!/usr/bin/env bash
set -e


echo "Checking WebSocket dependencies..."
python - <<'PY'
import importlib.util
import subprocess
import sys


def websockets_compatible() -> bool:
    if importlib.util.find_spec("websockets") is None:
        return False
    try:
        import websockets  # type: ignore
        major = int(str(getattr(websockets, "__version__", "0")).split(".", 1)[0])
        # uvicorn 0.29 works reliably with websockets <= 12.
        return major <= 12
    except Exception:
        return False


has_wsproto = importlib.util.find_spec("wsproto") is not None
has_compatible_websockets = websockets_compatible()

if has_wsproto or has_compatible_websockets:
    print("WebSocket backend dependency found")
else:
    print("Missing compatible websocket backend; installing requirements.txt...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
PY
echo "🟢 Starting WebSocket services inside container..."

echo "🚀 Starting Main WebSocket App on port 8009..."
python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8009 \
  --no-access-log \
  --log-level warning \
  &

echo "🚀 Starting Donation Stats WS App on port 8008..."
python -m uvicorn donate_stat:app \
  --host 0.0.0.0 \
  --port 8008 \
  --no-access-log \
  --log-level warning \
  &

# Forward signals properly
wait -n
exit $?
