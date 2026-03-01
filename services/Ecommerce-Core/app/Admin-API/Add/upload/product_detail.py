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
logger = logging.getLogger("product_detail")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False  # prevent logs from leaking

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
# DB Helper
# ------------------------------
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ------------------------------
# Fetch Products
# ------------------------------
def fetch_products(verbose: bool = True) -> list:
    """
    Fetch products from the database including title, description, 
    uniqueSellingPoint, topFeatures, techSpecs, media, and variants.
    Set verbose=False to suppress logs when called from orchestrator.
    Returns:
        List[Dict]: List of product dictionaries.
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
        return []

    try:
        cur = conn.cursor()
        query = sql.SQL("""
            SELECT title, description, uniquesellingpoint, topfeatures, techspecs, media, variants
            FROM {table}
            ORDER BY title
        """).format(table=sql.Identifier(PRODUCTS_TABLE))
        if verbose:
            logger.info("Executing query to fetch products...")
        cur.execute(query)
        rows = cur.fetchall()
        if verbose:
            logger.info("Fetched %d rows from table '%s'", len(rows), PRODUCTS_TABLE)
    except Exception as e:
        if verbose:
            logger.error("Failed to fetch products: %s", e)
        return []
    finally:
        conn.close()
        if verbose:
            logger.info("Database connection closed")

    products = []
    for idx, row in enumerate(rows, start=1):
        title, description, usp, top_features, tech_specs, media, variants = row

        # Format product data for Shopify without printing content
        product_data = {
            "title": title or "",
            "description": description or "",
            "uniqueSellingPoint": usp or "",
            "topFeatures": json.loads(top_features) if isinstance(top_features, str) else top_features or [],
            "techSpecs": json.loads(tech_specs) if isinstance(tech_specs, str) else tech_specs or []
        }

        if verbose:
            field_names = list(product_data.keys())
            logger.info("Product %d: Fields prepared for Shopify -> %s", idx, ", ".join(field_names))

        products.append(product_data)

    if verbose:
        logger.info("Total products processed: %d", len(products))

    return products

# ------------------------------
# Test run
# ------------------------------
if __name__ == "__main__":
    fetch_products(verbose=True)
