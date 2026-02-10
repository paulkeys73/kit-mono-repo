# core/env_db.py

import os

# -------------------------------
# DB Configuration (Docker / Local)
# -------------------------------

def get_db_settings():
    """
    Returns database settings dict.
    Supports Docker and localhost PostgreSQL.
    """

    # Explicit environment selector
    env = os.getenv("DB_ENV", "local").lower()
    # allowed: docker | local

    db_user = os.getenv("DB_USER", "kit")
    db_password = os.getenv("DB_PASSWORD", "admin123Pw")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "knightindustrytech")

    if env == "local":
        db_host = os.getenv("DB_HOST", "127.0.0.1")
    else:
        # Docker default
        db_host = os.getenv("DB_HOST", "app_postgres")

    return {
        "DB_ENV": env,
        "DB_USER": db_user,
        "DB_PASSWORD": db_password,
        "DB_HOST": db_host,
        "DB_PORT": db_port,
        "DB_NAME": db_name,
    }


# -------------------------------
# Helper functions to build URLs
# -------------------------------

def build_admin_db_url():
    """
    Returns SQLAlchemy URL for admin connection
    (default 'postgres' DB).
    """
    cfg = get_db_settings()
    return (
        f"postgresql+psycopg2://"
        f"{cfg['DB_USER']}:{cfg['DB_PASSWORD']}"
        f"@{cfg['DB_HOST']}:{cfg['DB_PORT']}/postgres"
    )


def build_app_db_url():
    """
    Returns SQLAlchemy URL for application DB.
    """
    cfg = get_db_settings()
    return (
        f"postgresql+psycopg2://"
        f"{cfg['DB_USER']}:{cfg['DB_PASSWORD']}"
        f"@{cfg['DB_HOST']}:{cfg['DB_PORT']}/{cfg['DB_NAME']}"
    )
