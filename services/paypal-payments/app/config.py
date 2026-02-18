# E:\paypal-payments\app\config.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from datetime import datetime
from decimal import Decimal as d
import uuid
import json

# -------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()


# -------------------------------------------------
# Settings
# -------------------------------------------------
class Settings(BaseSettings):
    # PayPal
    PAYPAL_BASE_URL: str
    PAYPAL_CLIENT_ID: str
    PAYPAL_SECRET: str
    PAYPAL_MODE: str = "sandbox"

    # App
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8800

    # Database
    DB_ENV: str = "local"            # local | docker
    FORCE_LOCAL_DB: bool = False

    DB_HOST: str | None = None
    DB_PORT: int = 5432
    DB_NAME: str = "knightindustrytech"
    DB_USER: str = "kit"
    DB_PASSWORD: str = "admin123Pw"

    # SMTP
    SMTP_SERVER: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    SMTP_FROM: str
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"

    # -------------------------------------------------
    # DB helpers
    # -------------------------------------------------
    def resolve_db_host(self) -> str:
        if self.FORCE_LOCAL_DB or self.DB_ENV.lower() == "local":
            return self.DB_HOST or "127.0.0.1"
        return self.DB_HOST or "app_postgres"

    def get_db_connection(self):
        host = self.resolve_db_host()
        print(
            f"📡 DB CONNECT → env={self.DB_ENV} "
            f"host={host}:{self.DB_PORT} "
            f"db={self.DB_NAME} user={self.DB_USER}"
        )
        return psycopg2.connect(
            host=host,
            port=self.DB_PORT,
            dbname=self.DB_NAME,
            user=self.DB_USER,
            password=self.DB_PASSWORD,
            cursor_factory=RealDictCursor,
            connect_timeout=5,
        )


# -------------------------------------------------
# Initialize settings
# -------------------------------------------------
settings = Settings()


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def now_utc():
    return datetime.utcnow()


# -------------------------------------------------
# Payments table columns
# -------------------------------------------------
PAYMENTS_TABLE_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "paypal_order_id": "VARCHAR(50) UNIQUE NOT NULL",
    "user_id": "INTEGER NOT NULL",
    "user_name": "VARCHAR(150)",
    "first_name": "VARCHAR(150)",
    "last_name": "VARCHAR(150)",
    "full_name": "VARCHAR(255)",
    "email": "VARCHAR(255)",
    "amount": "NUMERIC(12,2) NOT NULL",
    "currency": "VARCHAR(10) NOT NULL",
    "status": "VARCHAR(50) NOT NULL",
    "card_last4": "VARCHAR(10) DEFAULT '0000'",
    "card_brand": "VARCHAR(50) DEFAULT 'UNKNOWN'",
    "card_type": "VARCHAR(50) DEFAULT 'UNKNOWN'",
    "paypal_fee": "NUMERIC(12,2) DEFAULT 0.0",
    "net_amount": "NUMERIC(12,2) DEFAULT 0.0",
    "network": "VARCHAR(50) DEFAULT 'paypal'",
    "network_reference_id": "VARCHAR(100) DEFAULT ''",
    "paypal_order_id": "VARCHAR(50)",
    "source": "VARCHAR(50) DEFAULT 'paypal'",
    "method": "VARCHAR(50) DEFAULT 'pre-capture'",
    "billing_full_name": "VARCHAR(255)",
    "billing_country": "VARCHAR(100) DEFAULT 'Unknown'",
    "payment_type": "VARCHAR(50) DEFAULT 'UNKNOWN'",
    "metadata": "JSONB",
    "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
}


# -------------------------------------------------
# Ensure table exists & flexible column update
# -------------------------------------------------
def ensure_payments_table():
    conn = settings.get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Create table if not exists
                columns_def = ",\n  ".join(f"{k} {v}" for k, v in PAYMENTS_TABLE_COLUMNS.items())
                cur.execute(f"CREATE TABLE IF NOT EXISTS payments (\n  {columns_def}\n);")
                print("✅ payments table ensured")

                # Check and add missing columns safely
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='payments';
                    """
                )
                # fetchall returns list of dicts with 'column_name'
                existing_cols = {row["column_name"] for row in cur.fetchall()}

                for col, col_def in PAYMENTS_TABLE_COLUMNS.items():
                    if col not in existing_cols:
                        cur.execute(f"ALTER TABLE payments ADD COLUMN {col} {col_def};")
                        print(f"➕ Column added: {col}")

    finally:
        conn.close()


# -------------------------------------------------
# Insert helper
# -------------------------------------------------
def insert_payment(payment: dict):
    columns = payment.keys()
    values = [payment[col] for col in columns]
    query = f"""
    INSERT INTO payments ({', '.join(columns)})
    VALUES ({', '.join(['%s'] * len(values))})
    RETURNING *;
    """
    conn = settings.get_db_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, values)
                return cur.fetchone()
    finally:
        conn.close()


# -------------------------------------------------
# Update helper
# -------------------------------------------------
def update_payment(paypal_order_id: str, updates: dict):
    set_clause = ", ".join(f"{k}=%s" for k in updates.keys())
    values = list(updates.values()) + [paypal_order_id]

    query = f"UPDATE payments SET {set_clause} WHERE paypal_order_id=%s RETURNING *;"
    conn = settings.get_db_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, values)
                return cur.fetchone()
    finally:
        conn.close()


# -------------------------------------------------
# Main runner for start-payment.sh
# -------------------------------------------------
def main():
    ensure_payments_table()
    print("💡 payments table checked and ready")


# -------------------------------------------------
# Auto-run if called directly
# -------------------------------------------------
if __name__ == "__main__":
    main()
