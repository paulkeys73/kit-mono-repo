#!/usr/bin/env bash
set -e

DB_HOST=${DB_HOST:-app_postgres}
DB_PORT=${DB_PORT:-5432}
DB_USER=${DB_USER:-kit}
DB_PASSWORD=${DB_PASSWORD:-admin123Pw}
DB_NAME=${DB_NAME:-knightindustrytech}

echo "Waiting for Postgres at $DB_HOST:$DB_PORT..."

python - <<'PY'
import os
import time

import psycopg2

host = os.getenv("DB_HOST", "app_postgres")
port = int(os.getenv("DB_PORT", "5432"))
user = os.getenv("DB_USER", "kit")
password = os.getenv("DB_PASSWORD", "admin123Pw")
dbname = os.getenv("DB_NAME", "knightindustrytech")
max_retries = int(os.getenv("DB_WAIT_MAX_RETRIES", "30"))
sleep_seconds = float(os.getenv("DB_WAIT_SLEEP_SECONDS", "2"))

for attempt in range(1, max_retries + 1):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=3,
        )
        conn.close()
        print("Postgres is ready.")
        break
    except Exception as exc:
        if attempt == max_retries:
            print(f"Postgres did not become ready after {max_retries} attempts: {exc}")
            raise SystemExit(1)
        print(f"Postgres not ready yet (attempt {attempt}/{max_retries}): {exc}")
        time.sleep(sleep_seconds)
PY

echo "Starting DB services..."

uvicorn stats.donationStats:app \
  --host 0.0.0.0 \
  --port 8012 &

exec uvicorn main:app \
  --host 0.0.0.0 \
  --port 8011