import os
from pathlib import Path
from dotenv import load_dotenv

# --------------------------------------------------
# Load .env
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # points to Ecommerce-Core
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# --------------------------------------------------
# Database connection
# --------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "knightindustrytech"),
    "user": os.getenv("DB_USER", "kit"),
    "password": os.getenv("DB_PASSWORD"),  # now pulled from .env
    "sslmode": "require" if os.getenv("DB_SSL") == "true" else "disable",
}

# --------------------------------------------------
# Tables
# --------------------------------------------------
PRODUCTS_TABLE = "products"
