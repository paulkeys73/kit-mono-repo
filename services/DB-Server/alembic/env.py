import logging
from alembic import context
from sqlalchemy import engine_from_config, pool
from core.env_db import get_db_settings

logging.basicConfig(level=logging.INFO)

config = context.config

db = get_db_settings()

DATABASE_URL = (
    f"postgresql+psycopg2://{db['DB_USER']}:{db['DB_PASSWORD']}"
    f"@{db['DB_HOST']}:{db['DB_PORT']}/{db['DB_NAME']}"
    "?client_encoding=utf8"
)

config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = None

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            transactional_ddl=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if __name__ == "__main__":
    run_migrations_online()
