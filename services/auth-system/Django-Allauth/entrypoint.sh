#!/usr/bin/env bash
set -e

echo "🟢 Starting Django Auth Service inside container..."

# -----------------------------
# DB connection settings
# -----------------------------
DB_HOST=${DB_HOST:-app_postgres}
DB_PORT=${DB_PORT:-5432}
DB_USER=${DB_USER:-kit}

echo "⏳ Waiting for Postgres at $DB_HOST:$DB_PORT..."

# Wait for Postgres to be ready
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
    sleep 2
done

echo "✅ Postgres is ready!"

# -----------------------------
# Install Python dependencies
# -----------------------------
if [ -f /app/requirements.txt ]; then
    echo "📦 Installing Python dependencies..."
    pip install --no-cache-dir --upgrade pip
    pip install --no-cache-dir -r /app/requirements.txt
fi

# -----------------------------
# Run Django migrations
# -----------------------------
echo "🛠 Running Django migrations..."
cd /app
python manage.py makemigrations
python manage.py migrate

# -----------------------------
# Start Django ASGI server with uvicorn
# -----------------------------
echo "🚀 Launching Auth Service on port 8034..."
exec python -m uvicorn Django_Settings.asgi:application --host 0.0.0.0 --port 8034
