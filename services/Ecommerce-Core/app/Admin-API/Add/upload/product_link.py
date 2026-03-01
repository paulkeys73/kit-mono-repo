import os
import json
import logging
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
from pathlib import Path

# ------------------------------
# Logging setup (module-local)
# ------------------------------
logger = logging.getLogger("product_links")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False  # prevents logs from leaking to orchestrator

# ------------------------------
# Config
# ------------------------------
BASE_DIR = Path(__file__).parent.resolve()
ENV_PATH = "/mnt/e/Ecommerce-Core/.env"
load_dotenv(ENV_PATH)

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

PRODUCTS_TABLE = os.getenv("PRODUCTS_TABLE", "products")

# ------------------------------
# DB Helpers
# ------------------------------
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ------------------------------
# Fetch product lookup URL & rating
# ------------------------------
def fetch_product_links(verbose: bool = True) -> dict:
    """
    Fetch 'lookupurl' and 'rating' fields from the products table.
    Handles rating stored as dict or JSON.
    Returns:
        Dict[product_title, Dict]: 
        {
            "Product Title": {"lookupurl": "...", "rating": 4.5}
        }
    """
    if verbose:
        logger.info("Connecting to database...")

    try:
        conn = get_connection()
        if verbose:
            logger.info("Database connection established")
    except Exception as e:
        if verbose:
            logger.error("Failed to connect to database: %s", e)
        return {}

    try:
        cur = conn.cursor()
        query = sql.SQL("""
            SELECT title, lookupurl, rating
            FROM {products_table}
            ORDER BY title
        """).format(products_table=sql.Identifier(PRODUCTS_TABLE))

        if verbose:
            logger.info("Executing query to fetch product links and ratings...")
        cur.execute(query)
        rows = cur.fetchall()
        if verbose:
            logger.info("Fetched %d products from table '%s'", len(rows), PRODUCTS_TABLE)
    except Exception as e:
        if verbose:
            logger.error("Failed to fetch product links: %s", e)
        return {}
    finally:
        conn.close()
        if verbose:
            logger.info("Database connection closed")

    product_links = {}
    for idx, row in enumerate(rows, start=1):
        title, lookupurl, rating = row

        # Parse rating if it's a dict or JSON string
        final_rating = None
        if isinstance(rating, dict):
            final_rating = float(rating.get("value", 0))
        elif isinstance(rating, str):
            try:
                rating_parsed = json.loads(rating)
                if isinstance(rating_parsed, dict):
                    final_rating = float(rating_parsed.get("value", 0))
                else:
                    final_rating = float(rating_parsed)
            except Exception:
                final_rating = None
        elif isinstance(rating, (int, float)):
            final_rating = float(rating)

        product_links[title] = {
            "lookupurl": lookupurl or "",
            "rating": final_rating
        }

        if verbose:
            logger.info(
                "Product %d: '%s' -> lookupurl: %s, rating: %s",
                idx, title, lookupurl, final_rating
            )

    if verbose:
        logger.info("Total products processed: %d", len(product_links))

    return product_links

# ------------------------------
# Test run
# ------------------------------
if __name__ == "__main__":
    all_links = fetch_product_links(verbose=True)
    for title, info in all_links.items():
        logger.info("Product: %s | Lookup URL: %s | Rating: %s", title, info['lookupurl'], info['rating'])
