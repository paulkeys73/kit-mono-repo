#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# If caller uses main.py subcommands directly, forward as-is.
if [[ $# -ge 1 && ( "$1" == "onboard" || "$1" == "list-steps" ) ]]; then
    exec python3 main.py "$@"
fi

# Backward-compatible shorthand: ./startup.sh <username> <email> <domain> [main.py onboard flags]
if [[ $# -lt 3 ]]; then
    echo "Usage:"
    echo "  ./startup.sh <username> <email> <domain> [--dry-run|--steps ...]"
    echo "  ./startup.sh list-steps"
    echo "  ./startup.sh onboard <username> <email> <domain> [--dry-run|--steps ...]"
    exit 1
fi

exec python3 main.py onboard "$@"
