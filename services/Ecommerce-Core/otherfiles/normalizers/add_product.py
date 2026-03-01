# File: read_product_details.py
from pathlib import Path
import psycopg2
import importlib.util

# --------------------------------------------------
# Config
# --------------------------------------------------
CONFIG_PATH = Path("/mnt/e/Ecommerce-Core/conf/config.py").resolve()
spec = importlib.util.spec_from_file_location("config", str(CONFIG_PATH))
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

DB_CONFIG = config.DB_CONFIG
PRODUCTS_TABLE = getattr(config, "PRODUCTS_TABLE", "products")

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def fetch_product_details():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, title, description
        FROM {PRODUCTS_TABLE}
        ORDER BY title
        LIMIT 100;
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    products = fetch_product_details()
    print(f"📦 Fetched {len(products)} products from {PRODUCTS_TABLE}\n")
    for idx, (prod_id, title, description) in enumerate(products, 1):
        print(f"{idx}. ID: {prod_id}")
        print(f"   Title: {title}")
        print(f"   Description: {description}\n")

if __name__ == "__main__":
    main()
