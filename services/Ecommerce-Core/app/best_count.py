import json
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import Json

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
sys.path.append(str(PROJECT_ROOT))

from conf.config import DB_CONFIG, PRODUCTS_TABLE

INPUT_FILE = PROJECT_ROOT / "MCP-Products.json"
MIN_RATING_COUNT = 8000

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def get_rating_count(product: dict) -> int:
    rating = product.get("rating")
    if not isinstance(rating, dict):
        return 0
    try:
        return int(rating.get("count", 0))
    except (TypeError, ValueError):
        return 0


def product_key(product: dict) -> str:
    title = product.get("title", "").strip().lower()
    variants = product.get("variants", [])
    keys = [f"{v.get('id','')}:{v.get('price',{}).get('amount','')}" for v in variants]
    keys.sort()
    return f"{title}-{'|'.join(keys)}"


def clean_product(product: dict) -> dict:
    """Remove empty values recursively."""
    if isinstance(product, dict):
        return {k: clean_product(v) for k, v in product.items() if v not in (None, "", [], {})}
    if isinstance(product, list):
        return [clean_product(v) for v in product if v not in (None, "", [], {})]
    return product


def create_columns_if_missing(cur, product: dict):
    """Add top-level columns dynamically."""
    # Ensure timestamps exist
    cur.execute(f"""
        ALTER TABLE {PRODUCTS_TABLE}
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    """)
    cur.execute(f"""
        ALTER TABLE {PRODUCTS_TABLE}
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    """)

    for key, value in product.items():
        if key == "id":
            continue
        col_type = "JSONB" if isinstance(value, (dict, list)) else \
                   "BIGINT" if isinstance(value, int) else \
                   "NUMERIC" if isinstance(value, float) else "TEXT"
        cur.execute(f"""
            ALTER TABLE {PRODUCTS_TABLE}
            ADD COLUMN IF NOT EXISTS "{key.lower()}" {col_type};
        """)


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)

    seen = set()
    unique_products = []
    for p in products:
        if get_rating_count(p) < MIN_RATING_COUNT:
            continue
        key = product_key(p)
        if key not in seen:
            seen.add(key)
            unique_products.append(clean_product(p))

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for product in unique_products:
        external_id = product.get("id") or product.get("handle") or product_key(product)

        # Create missing columns including timestamps
        create_columns_if_missing(cur, product)

        # Build insert/update dynamically
        fields = ["external_id"] + [k.lower() for k in product.keys() if k != "id"]
        values = [external_id] + [
            Json(product[k]) if isinstance(product[k], (dict, list)) else product[k]
            for k in product.keys() if k != "id"
        ]

        placeholders = ", ".join(["%s"] * len(values))
        columns = ", ".join(f'"{f}"' for f in fields)
        updates = ", ".join(f'"{f}" = EXCLUDED."{f}"' for f in fields if f != "external_id")

        sql = f"""
            INSERT INTO {PRODUCTS_TABLE} ({columns})
            VALUES ({placeholders})
            ON CONFLICT (external_id)
            DO UPDATE SET {updates};
        """
        cur.execute(sql, values)

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Products written to DB: {len(unique_products)}")


if __name__ == "__main__":
    main()
