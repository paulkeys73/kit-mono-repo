# E:\paypal-payments\app\config.py
import os
import psycopg2
from psycopg2 import pool as psycopg2_pool
from psycopg2.extras import RealDictCursor
from pydantic import PrivateAttr
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from datetime import datetime
from decimal import Decimal as d
import uuid
import json
import time
from threading import Lock

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
    DB_CONNECT_TIMEOUT: int = 3
    DB_STARTUP_RETRIES: int = 6
    DB_RETRY_DELAY_SECONDS: float = 1.0
    DB_POOL_MIN_CONN: int = 1
    DB_POOL_MAX_CONN: int = 5

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

    _db_pool: psycopg2_pool.SimpleConnectionPool | None = PrivateAttr(default=None)
    _db_pool_host: str | None = PrivateAttr(default=None)
    _db_pool_lock: Lock = PrivateAttr(default_factory=Lock)

    # -------------------------------------------------
    # DB helpers
    # -------------------------------------------------
    def resolve_db_hosts(self) -> list[str]:
        if self.DB_HOST:
            # Allow comma-separated host fallbacks via DB_HOST.
            return [h.strip() for h in self.DB_HOST.split(",") if h.strip()]

        env = self.DB_ENV.lower()
        if self.FORCE_LOCAL_DB or env == "local":
            candidates = ["127.0.0.1", "localhost", "host.docker.internal", "app_postgres"]
        else:
            candidates = ["app_postgres", "postgres", "host.docker.internal", "127.0.0.1", "localhost"]

        seen: set[str] = set()
        ordered: list[str] = []
        for host in candidates:
            if host not in seen:
                seen.add(host)
                ordered.append(host)
        return ordered

    def _ensure_db_pool(self):
        if self._db_pool is not None:
            return

        with self._db_pool_lock:
            if self._db_pool is not None:
                return

            last_error = None
            hosts = self.resolve_db_hosts()

            for host in hosts:
                print(
                    f"DB CONNECT -> env={self.DB_ENV} "
                    f"host={host}:{self.DB_PORT} "
                    f"db={self.DB_NAME} user={self.DB_USER}"
                )
                try:
                    new_pool = psycopg2_pool.SimpleConnectionPool(
                        minconn=max(1, int(self.DB_POOL_MIN_CONN)),
                        maxconn=max(1, int(self.DB_POOL_MAX_CONN)),
                        host=host,
                        port=self.DB_PORT,
                        dbname=self.DB_NAME,
                        user=self.DB_USER,
                        password=self.DB_PASSWORD,
                        cursor_factory=RealDictCursor,
                        connect_timeout=self.DB_CONNECT_TIMEOUT,
                    )

                    # Validate one pooled connection immediately.
                    conn = new_pool.getconn()
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1")
                            cur.fetchone()
                    finally:
                        new_pool.putconn(conn)

                    self._db_pool = new_pool
                    self._db_pool_host = host
                    print(
                        f"DB POOL READY -> env={self.DB_ENV} "
                        f"host={host}:{self.DB_PORT} "
                        f"size={self.DB_POOL_MIN_CONN}-{self.DB_POOL_MAX_CONN}"
                    )
                    return
                except psycopg2.OperationalError as exc:
                    last_error = exc
                    print(f"DB connect failed for host={host}:{self.DB_PORT} -> {exc}")

            if last_error:
                raise last_error
            raise psycopg2.OperationalError("No valid DB host candidates were resolved")

    def get_db_connection(self):
        self._ensure_db_pool()
        if self._db_pool is None:
            raise psycopg2.OperationalError("Database pool is not initialized")
        raw_conn = self._db_pool.getconn()
        if raw_conn.closed:
            self._db_pool.putconn(raw_conn, close=True)
            raw_conn = self._db_pool.getconn()
        return PooledConnection(raw_conn, self._db_pool)

    def wait_for_db_connection(self):
        retries = max(1, int(self.DB_STARTUP_RETRIES))
        delay = max(0.0, float(self.DB_RETRY_DELAY_SECONDS))

        for attempt in range(1, retries + 1):
            try:
                conn = self.get_db_connection()
                self.release_db_connection(conn)
                return True
            except psycopg2.OperationalError as exc:
                if attempt == retries:
                    raise
                print(
                    f"DB not reachable on startup (attempt {attempt}/{retries}): {exc}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)

        raise psycopg2.OperationalError("Database did not become reachable during startup retries")

    def release_db_connection(self, conn):
        if isinstance(conn, PooledConnection):
            conn.close()
        elif conn is not None:
            conn.close()

    def close_db_pool(self):
        with self._db_pool_lock:
            if self._db_pool is not None:
                self._db_pool.closeall()
                self._db_pool = None
                self._db_pool_host = None


class PooledConnection:
    """
    Light wrapper that returns psycopg2 connections to the pool on close().
    """

    def __init__(self, raw_conn, connection_pool: psycopg2_pool.SimpleConnectionPool):
        self._raw_conn = raw_conn
        self._pool = connection_pool
        self._released = False

    def __getattr__(self, item):
        return getattr(self._raw_conn, item)

    def __enter__(self):
        return self._raw_conn.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._raw_conn.__exit__(exc_type, exc_val, exc_tb)

    def close(self):
        if not self._released:
            try:
                self._pool.putconn(self._raw_conn)
            except Exception:
                pass
            self._released = True

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

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
