import os
import json
import requests
from dotenv import load_dotenv
from typing import List, Dict, Any

# -----------------------------
# Load ENV
# -----------------------------
load_dotenv()

SHOPIFY_STORE = os.getenv("MY_STORE_DOMAIN")
ADMIN_TOKEN = os.getenv("MY_SHOPIFY_ADMIN_TOKEN")

if not SHOPIFY_STORE or not ADMIN_TOKEN:
    raise RuntimeError("Missing Shopify store or admin token in environment")

HEADERS = {
    "X-Shopify-Access-Token": ADMIN_TOKEN,
    "Content-Type": "application/json"
}

MCP_PRODUCTS_FILE = r"/mnt/e/Ecommerce-Core/app/Best-Count.json"
OUTPUT_FILE = r"Shopify-Filtered-Products.json"

# -----------------------------
# Utils
# -----------------------------
def safe_float(v):
    try:
        return float(v)
    except Exception:
        return 0.0

def load_mcp_products() -> List[Dict[str, Any]]:
    with open(MCP_PRODUCTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, list) else [data]

# -----------------------------
# Shopify API Helpers
# -----------------------------
def fetch_existing_products_titles() -> Dict[str, List[float]]:
    """Fetch existing Shopify products (title -> list of variant prices)"""
    products_lookup: Dict[str, List[float]] = {}
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products.json?limit=250&fields=id,title,variants"
    
    while url:
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        data = r.json().get("products", [])
        for p in data:
            title = p.get("title")
            prices = [safe_float(v.get("price")) for v in p.get("variants", [])]
            products_lookup[title] = prices
        # Pagination via Link header
        link_header = r.headers.get("Link", "")
        next_url = None
        if 'rel="next"' in link_header:
            parts = link_header.split(",")
            for part in parts:
                if 'rel="next"' in part:
                    next_url = part.split("<")[1].split(">")[0]
        url = next_url
    return products_lookup

def is_duplicate(product: Dict[str, Any], existing_lookup: Dict[str, List[float]]) -> bool:
    title = product.get("title")
    new_prices = [safe_float(v.get("price")) for v in product.get("variants", [])]
    existing_prices = existing_lookup.get(title)
    if existing_prices and set(new_prices) == set(existing_prices):
        return True
    return False

def create_shopify_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Add product to Shopify with proper formatting and debug logging."""
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products.json"

    variants = product.get("variants", [])

    # If no variants, auto-create a default one
    if not variants:
        variants = [{"displayName": "Default", "price": 1000}]  # 1000 cents = $10

    cleaned_variants = []
    for v in variants:
        price = safe_float(v.get("price"))
        compare = safe_float(v.get("compareAtPrice") or v.get("compare_at_price"))
        if price <= 0:
            price = 1000  # default $10 if price invalid
        cleaned_variants.append({
            "option1": v.get("displayName") or "Default",
            "price": f"{price/100:.2f}",
            "compare_at_price": f"{compare/100:.2f}" if compare > 0 else f"{(price+500)/100:.2f}"
        })

    images = [{"src": m.get("url")} for m in product.get("media", []) if m.get("url")]

    payload = {
        "product": {
            "title": product.get("title") or "MCP Product",
            "body_html": product.get("description") or "",
            "vendor": product.get("vendor") or "MCP Vendor",
            "product_type": product.get("category") or "MCP Product",
            "variants": cleaned_variants,
            "images": images
        }
    }

    print(f"🔹 Sending product to Shopify: {product.get('title')}")
    r = requests.post(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()["product"]

def delete_shopify_product(product_id: int):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products/{product_id}.json"
    r = requests.delete(url, headers=HEADERS)
    return r.status_code in (200, 404)

# -----------------------------
# Filter Logic
# -----------------------------
def filter_discounted_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered = []
    for p in products:
        keep = False
        for v in p.get("variants", []):
            price = safe_float(v.get("price"))
            compare = safe_float(v.get("compare_at_price"))
            if compare > 0 and price < compare:
                keep = True
                break
        if keep or p.get("hasFreeShipping") or p.get("matchedCoupons"):
            filtered.append(p)
    return filtered

# -----------------------------
# Main
# -----------------------------
def main():
    mcp_products = load_mcp_products()
    print(f"📦 Loaded MCP products: {len(mcp_products)}")

    existing_lookup = fetch_existing_products_titles()
    print(f"📌 Existing Shopify products: {len(existing_lookup)}")

    shopify_products = []

    for p in mcp_products:
        if is_duplicate(p, existing_lookup):
            print(f"⚠️ Skipping duplicate product: {p.get('title')}")
            continue
        try:
            created = create_shopify_product(p)
        except Exception as e:
            print(f"⚠️ Skipping product '{p.get('title')}': {e}")
            continue
        shopify_products.append(created)

    filtered_products = filter_discounted_products(shopify_products)

    deleted_count = 0
    for p in shopify_products:
        if p not in filtered_products:
            if delete_shopify_product(p["id"]):
                deleted_count += 1

    print(f"✅ Added products: {len(shopify_products)}")
    print(f"🗑 Deleted non-discounted products: {deleted_count}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(filtered_products, f, indent=2, ensure_ascii=False)
    print(f"📄 Filtered products written to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()