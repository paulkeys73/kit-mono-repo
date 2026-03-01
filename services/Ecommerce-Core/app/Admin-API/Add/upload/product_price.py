# E:\Ecommerce-Core\app\Admin-API\Add\upload\product_price.py

import os
import json
import logging
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict, Optional

# ------------------------------
# Logging setup (module-local)
# ------------------------------
logger = logging.getLogger("product_prices")
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
# Variant fingerprinting
# ------------------------------
def build_variant_key(options: list) -> str:
    """
    Deterministic key for a Shopify variant based on options list.
    """
    if not options:
        return "default"
    return "|".join(str(opt.get("value", "")).strip().lower() for opt in options if opt.get("value"))

def parse_price(price) -> Optional[int]:
    """
    Safely parse a Shopify price value and convert to cents.
    Handles:
      - price as dict: {"amount": 28.00, "currency": "USD"}
      - price as string: "28.00"
      - price as number: 28.0 or 2800
    Returns an int in cents or None.
    """
    if price is None:
        return None

    # If price is a dict, take 'amount' key
    if isinstance(price, dict):
        price = price.get("amount", 0)

    # Convert to float first
    try:
        price_float = float(price)
    except (ValueError, TypeError):
        return None

    # If price looks like dollars (<1000), convert to cents
    if price_float < 1000:
        return int(round(price_float * 100))
    return int(round(price_float))  # Already in cents

def normalize_variants(raw_variants: List[Dict]) -> List[Dict]:
    """
    Normalize Shopify variant data to internal format, format prices as cents.
    """
    normalized: List[Dict] = []

    for v in raw_variants:
        options = v.get("options", [])
        key = build_variant_key(options)

        price_amount = parse_price(v.get("price"))
        compare_at_price = parse_price(v.get("compare_at_price"))
        sku = str(v.get("sku") or "").strip() or None

        option1 = options[0]["value"] if len(options) > 0 else None
        option2 = options[1]["value"] if len(options) > 1 else None
        option3 = options[2]["value"] if len(options) > 2 else None

        normalized.append({
            "key": key,
            "price": price_amount,
            "compare_at_price": compare_at_price,
            "sku": sku,
            "options": {
                "option1": option1,
                "option2": option2,
                "option3": option3
            }
        })

    return normalized

# ------------------------------
# Fetch product pricing info
# ------------------------------
def fetch_product_prices(verbose: bool = True) -> List[Dict]:
    """
    Fetch pricerange, variant_count, and variants for all products.
    Returns a list of dicts:
        - title
        - pricerange
        - variant_count
        - variants (list of dicts with key, price, compare_at_price)
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
            SELECT title, pricerange, variant_count, variants
            FROM {table}
            ORDER BY title
        """).format(table=sql.Identifier(PRODUCTS_TABLE))

        if verbose:
            logger.info("Executing query to fetch product prices...")
        cur.execute(query)
        rows = cur.fetchall()
        if verbose:
            logger.info("Fetched %d rows from table '%s'", len(rows), PRODUCTS_TABLE)

    except Exception as e:
        if verbose:
            logger.error("Failed to fetch product prices: %s", e)
        return []

    finally:
        conn.close()
        if verbose:
            logger.info("Database connection closed")

    products_prices = []
    for idx, row in enumerate(rows, start=1):
        title, pricerange, variant_count, variants = row

        # Parse JSON fields safely
        try:
            pricerange_data = json.loads(pricerange) if isinstance(pricerange, str) else pricerange or {}
        except Exception as e:
            if verbose:
                logger.warning("Failed to parse pricerange for product '%s': %s", title, e)
            pricerange_data = {}

        try:
            variants_data = json.loads(variants) if isinstance(variants, str) else variants or []
        except Exception as e:
            if verbose:
                logger.warning("Failed to parse variants for product '%s': %s", title, e)
            variants_data = []

        normalized_variants = normalize_variants(variants_data)

        product_data = {
            "title": title,
            "pricerange": pricerange_data,
            "variant_count": variant_count or len(normalized_variants),
            "variants": normalized_variants
        }

        if verbose:
            logger.info(
                "Product %d: '%s' -> %d variants, price info loaded",
                idx, title, len(normalized_variants)
            )
            for v in normalized_variants:
                logger.info(
                    "  → Variant key=%s, SKU=%s, price=%s, compare_at_price=%s",
                    v["key"], v["sku"], v["price"], v["compare_at_price"]
                )

        products_prices.append(product_data)

    if verbose:
        logger.info("Total products processed: %d", len(products_prices))

    return products_prices

# ------------------------------
# Test run
# ------------------------------
if __name__ == "__main__":
    fetch_product_prices(verbose=True)
