# File: E:\Ecommerce-Core\app\Admin-API\Add\upload\product_image.py

import os
import json
import logging
import psycopg2
import requests
from psycopg2 import sql
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

# ------------------------------
# Logging setup (module-local only)
# ------------------------------
logger = logging.getLogger("product_image")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False  # prevents logs from leaking to orchestrator

# ------------------------------
# Config / Env
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
OUTPUT_JSON = BASE_DIR / "media_ready.json"

# ------------------------------
# Helpers
# ------------------------------
def get_connection():
    """Return a new database connection."""
    return psycopg2.connect(**DB_CONFIG)

def extract_product_handle(variant_url: str) -> str | None:
    try:
        path = urlparse(variant_url).path
        parts = path.strip("/").split("/")
        if "products" in parts:
            return parts[parts.index("products") + 1]
    except Exception:
        pass
    return None

def fetch_storefront_images(variant_url: str) -> list:
    handle = extract_product_handle(variant_url)
    if not handle:
        logger.warning("Could not extract handle from variantUrl: %s", variant_url)
        return []

    json_url = f"https://{urlparse(variant_url).netloc}/products/{handle}.json"
    try:
        r = requests.get(json_url, timeout=15)
        r.raise_for_status()
        product = r.json().get("product", {})
    except Exception as e:
        logger.warning("Storefront fetch failed for %s: %s", json_url, e)
        return []

    images = []
    for img in product.get("images", []):
        src = img.get("src")
        if src:
            images.append({"src": src, "alt": img.get("alt") or product.get("title")})
    return images

# ------------------------------
# Main Logic
# ------------------------------
def fetch_product_media(verbose: bool = True) -> dict:
    """Fetch product media from DB and storefronts.
       Set verbose=False to suppress logs when called from orchestrator.
    """
    if verbose:
        logger.info("Step 1: Default product image fetch from DB")
        logger.info("Connecting to database...")

    conn = get_connection()
    if verbose:
        logger.info("Database connection established")

    try:
        cur = conn.cursor()
        cur.execute(
            sql.SQL("SELECT title, media, variants FROM {} ORDER BY title")
            .format(sql.Identifier(PRODUCTS_TABLE))
        )
        rows = cur.fetchall()
        if verbose:
            logger.info("DB products fetched: %d", len(rows))
    finally:
        conn.close()
        if verbose:
            logger.info("Database connection closed")

    media_map = {}
    if verbose:
        logger.info("Collecting all product images...")

    for title, media_field, variants_field in rows:
        images = []
        seen = set()

        # ------------------------------
        # STEP 1: EXTRACT DEFAULT IMAGES FROM DB
        # ------------------------------
        if media_field:
            try:
                media = json.loads(media_field) if isinstance(media_field, str) else media_field
            except Exception as e:
                if verbose:
                    logger.warning("Media JSON parse error for '%s': %s", title, e)
                media = []

            for m in media:
                db_url = m.get("url")
                if db_url and db_url not in seen:
                    images.append({"src": db_url, "alt": m.get("altText") or title})
                    seen.add(db_url)

        # ------------------------------
        # STEP 2: PROCESS VARIANTS
        # ------------------------------
        if variants_field:
            try:
                variants = json.loads(variants_field) if isinstance(variants_field, str) else variants_field
            except Exception as e:
                if verbose:
                    logger.warning("Variants JSON parse error for '%s': %s", title, e)
                variants = []

            for v in variants:
                variant_url = v.get("variantUrl")
                if not variant_url:
                    continue

                variant_images = fetch_storefront_images(variant_url)
                v_media = v.get("media", [])
                for m in v_media:
                    v_url = m.get("url")
                    if v_url and v_url not in seen:
                        variant_images.append({"src": v_url, "alt": m.get("altText") or title})

                for img in variant_images:
                    if img["src"] not in seen:
                        images.append(img)
                        seen.add(img["src"])

        if images:
            media_map[title] = images

    if verbose:
        logger.info("Images collected and stored successfully for %d products", len(media_map))
    return media_map

# ------------------------------
# Save Output
# ------------------------------
def save_media_map(media_map: dict):
    try:
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(media_map, f, ensure_ascii=False, indent=2)
        logger.info("Media map saved to %s", OUTPUT_JSON)
    except Exception as e:
        logger.warning("Failed to save media map: %s", e)

# ------------------------------
# Run standalone
# ------------------------------
if __name__ == "__main__":
    media_map = fetch_product_media(verbose=True)
    save_media_map(media_map)
