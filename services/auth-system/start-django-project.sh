#!/bin/bash

# ------------------------------
# Django Project Setup Automation
# ------------------------------

# Root working directory
ROOT_DIR=$(pwd)

# ------------------------------
# Virtual Environment Setup
# ------------------------------
echo "🔧 Creating virtual environment..."
python3 -m venv "$ROOT_DIR/venv"

echo "🔧 Activating virtual environment..."
source "$ROOT_DIR/venv/bin/activate"
echo "✅ Virtual environment ready"

# ------------------------------
# .env Creation
# ------------------------------
echo "🔧 Creating .env Config File..."
cat <<EOF > "$ROOT_DIR/.env"
DJANGO_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
DEBUG=True
DJANGO_SUPERUSER_USERNAME=Paulkeys
DJANGO_SUPERUSER_EMAIL=admin@paulkeys.dev
DJANGO_SUPERUSER_PASSWORD=admin123Pw
EOF
echo "✅ .env Config File Ready"

# Load .env into environment
set -a
source "$ROOT_DIR/.env"
set +a
echo "✅ .env Config Loaded"

# ------------------------------
# Install Django + Essentials
# ------------------------------
echo "🔧 Installing Django & essentials..."
pip install --upgrade pip >/dev/null 2>&1
pip install django djangorestframework python-dotenv django-cors-headers >/dev/null 2>&1
django-admin --version

# ------------------------------
# Project & App Setup
# ------------------------------
PROJECT_DIR="$ROOT_DIR/Django-Allauth"
SETTINGS_DIR="Django_Settings"

echo "🔧 Starting Django Project..."
django-admin startproject "$SETTINGS_DIR" "$PROJECT_DIR"

# Move into project directory
cd "$PROJECT_DIR" || exit

# ------------------------------
# Create requirements.txt
# ------------------------------
echo "🔧 Creating requirements..."
pip freeze > requirements.txt
echo "✅ Django Project Ready"

# ------------------------------
# Create Django App
# ------------------------------
echo "🔧 Starting Auth App..."
python manage.py startapp auth_app

# ------------------------------
# Database Migrations
# ------------------------------
echo "🔧 Making Migrations..."
python manage.py makemigrations
python manage.py migrate
echo "✅ Migration Task Completed"

# ------------------------------
# Create Superuser (idempotent)
# ------------------------------
echo "🔧 Creating superuser..."

python - <<END
import os, sys, django

# Add project root to sys.path (one level above)
sys.path.append("$PROJECT_DIR")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', '$SETTINGS_DIR.settings')

django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()

username = os.getenv("DJANGO_SUPERUSER_USERNAME")
email = os.getenv("DJANGO_SUPERUSER_EMAIL")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD")

if not username:
    raise ValueError("Environment variable DJANGO_SUPERUSER_USERNAME is not set.")
if not email:
    raise ValueError("Environment variable DJANGO_SUPERUSER_EMAIL is not set.")
if not password:
    raise ValueError("Environment variable DJANGO_SUPERUSER_PASSWORD is not set.")

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"✅ Superuser '{username}' created successfully.")
else:
    print(f"ℹ️ Superuser '{username}' already exists — skipping creation.")
END

# ------------------------------
# Start Server
# ------------------------------
echo "🔧 Running Django App..."
python manage.py runserver 8034
