#E:\Ecommerce-Core\app\Admin-API\Add\upload\product_options.py

import os
import json
import logging
import psycopg2
import re
from psycopg2 import sql
from dotenv import load_dotenv
from pathlib import Path

# ------------------------------
# Logging setup
# ------------------------------
logger = logging.getLogger("product_options")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False

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
    "password": os.getenv("DB_PASSWORD"),
}

PRODUCTS_TABLE = os.getenv("PRODUCTS_TABLE", "products")

# ------------------------------
# DB Helpers
# ------------------------------
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ------------------------------
# Option normalization maps
# ------------------------------
OPTION_NAME_MAP = {
    "color": "Color",
    "colour": "Color",
    "farbe": "Color",
    "kleur": "Color",

    "size": "Size",
    "größe": "Size",
    "grosse": "Size",
    "taille": "Size",
}

COLOR_CANONICAL_MAP = {
    "black": "Black",
    "schwarz": "Black",
    "zwart": "Black",

    "grey": "Grey",
    "grijs": "Grey",
    "grau": "Grey",

    "army green": "Army Green",
    "donker groen": "Army Green",
    "hellgrün": "Green",

    "orange": "Orange",
    "oranje": "Orange",
}

SIZE_ORDER = [
    "XXS", "XS", "S", "M", "L", "XL",
    "2X", "XXL",
    "3X", "XXXL",
    "4X"
]

PACK_REGEX = re.compile(r"^\s*(\d+)\s*pack\s*$", re.I)

# ------------------------------
# Normalization helpers
# ------------------------------
def normalize_option_name(name: str) -> str:
    if not name:
        return "Unknown"
    key = name.strip().lower()
    return OPTION_NAME_MAP.get(key, name.strip().title())

def normalize_value(val: str) -> str | None:
    if not val:
        return None
    v = str(val).strip()
    if not v or v.lower() in {"n/a", "na", "none"}:
        return None
    return v

def normalize_color(val: str) -> str | None:
    v = normalize_value(val)
    if not v:
        return None
    return COLOR_CANONICAL_MAP.get(v.lower(), v)

def normalize_pack_sizes(values: list[str]) -> list[str] | None:
    """
    If all values are numeric pack sizes (e.g. '1 Pack'),
    return numerically sorted list. Otherwise return None.
    """
    packs = []
    for v in values:
        m = PACK_REGEX.match(v)
        if not m:
            return None
        packs.append((int(m.group(1)), f"{int(m.group(1))} Pack"))

    packs.sort(key=lambda x: x[0])
    return [p[1] for p in packs]

def normalize_size_list(values: list[str]) -> list[str]:
    clean = [normalize_value(v) for v in values]
    clean = [v for v in clean if v]

    # Try pack-based ordering first
    pack_sorted = normalize_pack_sizes(clean)
    if pack_sorted:
        return pack_sorted

    def size_key(v):
        try:
            return SIZE_ORDER.index(v)
        except ValueError:
            return len(SIZE_ORDER)

    return sorted(set(clean), key=size_key)

# ------------------------------
# Fetch product options
# ------------------------------
def fetch_product_options(verbose: bool = True) -> dict:
    if verbose:
        logger.info("Connecting to database...")

    try:
        conn = get_connection()
        if verbose:
            logger.info("Database connection established")
    except Exception as e:
        logger.error("Failed to connect to database: %s", e)
        return {}

    try:
        cur = conn.cursor()
        query = sql.SQL("""
            SELECT title, options
            FROM {products_table}
            ORDER BY title
        """).format(products_table=sql.Identifier(PRODUCTS_TABLE))

        if verbose:
            logger.info("Executing query to fetch product options...")
        cur.execute(query)
        rows = cur.fetchall()
        if verbose:
            logger.info("Fetched %d products from table '%s'", len(rows), PRODUCTS_TABLE)
    except Exception as e:
        logger.error("Failed to fetch product options: %s", e)
        return {}
    finally:
        conn.close()
        if verbose:
            logger.info("Database connection closed")

    product_options = {}

    for idx, (title, opts_json) in enumerate(rows, start=1):
        try:
            opts_list = json.loads(opts_json) if isinstance(opts_json, str) else opts_json or []
        except Exception as e:
            logger.warning("Failed to parse options JSON for '%s': %s", title, e)
            opts_list = []

        merged: dict[str, list[str]] = {}

        for o in opts_list:
            raw_name = o.get("name") or o.get("attribute") or "Unknown"
            name = normalize_option_name(raw_name)

            raw_values = []
            if isinstance(o.get("values"), list):
                for v in o["values"]:
                    raw_values.append(v.get("value") if isinstance(v, dict) else v)

            if name == "Color":
                values = {normalize_color(v) for v in raw_values if normalize_color(v)}
            elif name == "Size":
                values = normalize_size_list(raw_values)
            else:
                values = {normalize_value(v) for v in raw_values if normalize_value(v)}

            if not values:
                continue

            merged.setdefault(name, [])
            merged[name].extend(values)

        formatted_options = []
        for name, values in merged.items():
            if name == "Size":
                values = normalize_size_list(values)
            else:
                values = sorted(set(values))

            formatted_options.append({
                "name": name,
                "values": values
            })

        product_options[title] = formatted_options

        if verbose:
            logger.info(
                "Product %d: '%s' -> %d attributes",
                idx,
                title,
                len(formatted_options)
            )

    if verbose:
        logger.info("Total products processed: %d", len(product_options))

    return product_options

# ------------------------------
# Test run
# ------------------------------
if __name__ == "__main__":
    all_options = fetch_product_options(verbose=True)
    for title, opts in all_options.items():
        logger.info("Product: %s", title)
        for o in opts:
            logger.info("   - Attribute: %s -> Options: %s", o["name"], o["values"])
