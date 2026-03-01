#!/usr/bin/env bash
set -e

# -----------------------------
# DB configuration (Docker only)
# -----------------------------
DB_HOST=${DB_HOST:-app_postgres}
DB_PORT=${DB_PORT:-5432}
DB_USER=${DB_USER:-kit}
DB_PASSWORD=${DB_PASSWORD:-admin123Pw}
DB_NAME=${DB_NAME:-knightindustrytech}

export PGPASSWORD="$DB_PASSWORD"

echo "⏳ Waiting for Postgres at $DB_HOST:$DB_PORT..."

MAX_RETRIES=30
COUNT=0

until psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' >/dev/null 2>&1; do
  COUNT=$((COUNT + 1))
  if [ "$COUNT" -ge "$MAX_RETRIES" ]; then
    echo "❌ Postgres did not become ready after $((MAX_RETRIES*2)) seconds!"
    exit 1
  fi
  echo "Postgres not ready yet. Sleeping 2s..."
  sleep 2
done

echo "✅ Postgres is ready!"
echo "🚀 Starting DB services..."

# Start donation stats service in background
uvicorn stats.donationStats:app \
  --host 0.0.0.0 \
  --port 8012 &

# Start main DB server
exec uvicorn main:app \
  --host 0.0.0.0 \
  --port 8011
