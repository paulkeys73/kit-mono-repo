import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    # -------------------------------------------------
    # PayPal
    # -------------------------------------------------
    PAYPAL_BASE_URL: str
    PAYPAL_CLIENT_ID: str
    PAYPAL_SECRET: str
    PAYPAL_MODE: str = "sandbox"

    # -------------------------------------------------
    # App
    # -------------------------------------------------
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8800

    # -------------------------------------------------
    # Database
    # -------------------------------------------------
    DB_ENV: str = "local"            # local | docker
    FORCE_LOCAL_DB: bool = False

    DB_HOST: str | None = None
    DB_PORT: int = 5432
    DB_NAME: str = "knightindustrytech"
    DB_USER: str = "kit"
    DB_PASSWORD: str = "admin123Pw"

    # -------------------------------------------------
    # SMTP
    # -------------------------------------------------
    SMTP_SERVER: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    SMTP_FROM: str
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    # -------------------------------------------------
    # Data paths
    # -------------------------------------------------
    SPONSOR_TIERS_PATH: str = "app/data/sponsor_tiers.json"

    class Config:
        env_file = ".env"
        extra = "ignore"

    # -------------------------------------------------
    # DB helpers
    # -------------------------------------------------
    def resolve_db_host(self) -> str:
        """
        Resolve DB host for:
        - Windows / WSL local
        - Docker container network
        """
        if self.FORCE_LOCAL_DB or self.DB_ENV.lower() == "local":
            return self.DB_HOST or "127.0.0.1"

        # Docker default
        return self.DB_HOST or "app_postgres"

    def get_db_connection(self):
        """
        Create a new psycopg2 connection.
        Caller MUST close it.
        """
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
# Initialize settings (ONCE)
# -------------------------------------------------
settings = Settings()


# -------------------------------------------------
# Load Sponsor Tiers
# -------------------------------------------------
def load_sponsor_tiers():
    path = settings.SPONSOR_TIERS_PATH

    if not os.path.exists(path):
        print(f"[WARNING] Sponsor tiers file not found: {path}")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                print("[ERROR] Sponsor tiers JSON must be a list")
                return []
            return data
    except Exception as e:
        print(f"[ERROR] Failed to load sponsor tiers: {e}")
        return []


SPONSOR_TIERS = load_sponsor_tiers()
