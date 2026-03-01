import os
import json
import requests
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

# -----------------------------
# Paths & environment
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = "/mnt/e/Ecommerce-Core/.env"
CATEGORY_PATH = "/mnt/e/Ecommerce-Core/app/Admin-API/Add/category.json"
INPUT_FILE = "/mnt/e/Ecommerce-Core/app/Best-Count.json"

for path, name in [(ENV_PATH, ".env"), (CATEGORY_PATH, "category.json"), (INPUT_FILE, "ProductsOnSales.json")]:
    if not os.path.exists(path):
        raise RuntimeError(f"{name} not found at: {path}")

load_dotenv(ENV_PATH)
SHOPIFY_STORE_DOMAIN = os.getenv("MY_STORE_DOMAIN")
SHOPIFY_ADMIN_TOKEN = os.getenv("MY_SHOPIFY_ADMIN_TOKEN")
if not SHOPIFY_STORE_DOMAIN or not SHOPIFY_ADMIN_TOKEN:
    raise RuntimeError("Missing Shopify credentials")

print(f"🌐 Using store: {SHOPIFY_STORE_DOMAIN}")

# -----------------------------
# Load JSON
# -----------------------------
with open(CATEGORY_PATH, "r", encoding="utf-8") as f:
    CATEGORY_MAP = json.load(f)
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    products_on_sale: List[Dict[str, Any]] = json.load(f)
print(f"📦 Loaded {len(products_on_sale)} products")
print(f"🗂 Loaded category.json")

# -----------------------------
# Shopify helpers
# -----------------------------
def get_shopify_headers() -> Dict[str, str]:
    return {"Content-Type": "application/json", "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN}

def cents_to_dollars(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    amount = value.get("amount")
    if amount is None:
        return None
    dollars = float(amount) / 100
    return f"{dollars:.2f}" if dollars > 0 else None

# -----------------------------
# Category resolver
# -----------------------------
def resolve_category(product: Dict[str, Any]) -> str:
    haystack = " ".join([product.get("title", ""), product.get("description", ""), " ".join(product.get("tags", []))]).lower()
    for top_level, subcats in CATEGORY_MAP.items():
        for subcat, keywords in subcats.items():
            for keyword in keywords:
                if keyword.lower() in haystack:
                    return f"{top_level} > {subcat}"
    return "Miscellaneous"

# -----------------------------
# Variants (all with valid price)
# -----------------------------
def format_variant(variant: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    price = cents_to_dollars(variant.get("price"))
    if not price or float(price) <= 0:
        return None
    compare_at = cents_to_dollars(variant.get("compareAtPrice"))

    options = [o.get("value") for o in variant.get("options", []) if o.get("value")]
    sku = variant.get("SKU") or (options[0] if options else "Default")

    payload = {
        "option1": options[0] if options else sku,
        "price": price,
        "sku": sku,
        "inventory_management": "shopify",
        "inventory_quantity": variant.get("availableForSale", True) and 10 or 0
    }
    if len(options) > 1:
        payload["option2"] = options[1]
    if len(options) > 2:
        payload["option3"] = options[2]
    if compare_at:
        payload["compare_at_price"] = compare_at
    return payload

# -----------------------------
# Images
# -----------------------------
def get_images(product: Dict[str, Any]) -> List[Dict[str, str]]:
    images = product.get("media") or product.get("images") or []
    variants_options = [v.get("options", []) for v in product.get("variants", [])]
    result = []
    for img in images:
        src = img.get("src") or img.get("url")
        alt = img.get("altText") or product.get("title") or "Product Image"
        if src:
            for opts in variants_options:
                for o in opts:
                    val = o.get("value")
                    if val and val.lower() in (src.lower() or ""):
                        alt = val
            result.append({"src": src, "alt": alt})
    if not result:
        result.append({"src": "https://via.placeholder.com/600x600?text=No+Image", "alt": "No Image"})
    return result

# -----------------------------
# Description
# -----------------------------
def combine_description(product: Dict[str, Any]) -> str:
    html = f"<p>{product.get('description', '')}</p>"
    if product.get("uniqueSellingPoint"):
        html += f"<p><strong>USP:</strong> {product['uniqueSellingPoint']}</p>"
    if product.get("topFeatures"):
        html += "<ul>" + "".join(f"<li>{f}</li>" for f in product["topFeatures"]) + "</ul>"
    if product.get("techSpecs"):
        html += "<ul>" + "".join(f"<li>{s}</li>" for s in product["techSpecs"]) + "</ul>"
    return html

# -----------------------------
# Shopify helpers
# -----------------------------
def find_product_by_sku(sku: str) -> Optional[Dict[str, Any]]:
    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2026-01/products.json?limit=250"
    resp = requests.get(url, headers=get_shopify_headers(), timeout=30)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch products for SKU {sku}")
        return None
    for p in resp.json().get("products", []):
        for v in p.get("variants", []):
            if v.get("sku") == sku:
                return p
    return None

def add_to_onsales_collection(product_id: str):
    collection_handle = "on-sales"
    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2026-01/custom_collections.json"
    resp = requests.get(url, headers=get_shopify_headers())
    collection_id = None
    if resp.status_code == 200:
        for c in resp.json().get("custom_collections", []):
            if c.get("handle") == collection_handle:
                collection_id = c["id"]
                break
    if not collection_id:
        payload = {"custom_collection": {"title": "OnSales", "handle": collection_handle}}
        resp = requests.post(url, headers=get_shopify_headers(), json=payload)
        if resp.status_code in (200, 201):
            collection_id = resp.json()["custom_collection"]["id"]
            print(f"✅ Created 'OnSales' collection")
        else:
            print(f"❌ Failed to create 'OnSales' collection: {resp.text}")
            return
    add_url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2026-01/collects.json"
    requests.post(add_url, headers=get_shopify_headers(), json={"collect": {"product_id": product_id, "collection_id": collection_id}})

# -----------------------------
# Upsert product
# -----------------------------
def upsert_product(product: Dict[str, Any]) -> bool:
    variants_payload = [v for v in (format_variant(v) for v in product.get("variants", [])) if v]
    if not variants_payload:
        print(f"⚠️ SKIP (invalid pricing): {product.get('title')}")
        return False

    title = product.get("title") or "Untitled Product"
    vendor = product.get("vendor") or "MCP Vendor"
    tags = list(set((product.get("tags") or []) + ["Sale"]))
    product_type = resolve_category(product)
    images = get_images(product)
    body_html = combine_description(product)
    sku_to_check = variants_payload[0]["sku"]
    existing = find_product_by_sku(sku_to_check)

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "variants": variants_payload,
            "images": images
        }
    }

    if existing:
        product_id = existing["id"]
        payload["product"]["id"] = product_id
        url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2026-01/products/{product_id}.json"
        resp = requests.put(url, headers=get_shopify_headers(), json=payload, timeout=30)
        if resp.status_code in (200, 201):
            print(f"🔄 Updated: {title} | SKU: {sku_to_check}")
        else:
            print(f"❌ Failed to update: {title} | {resp.status_code} | {resp.text}")
            return False
    else:
        url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2026-01/products.json"
        resp = requests.post(url, headers=get_shopify_headers(), json=payload, timeout=30)
        if resp.status_code in (200, 201):
            product_id = resp.json()["product"]["id"]
            print(f"✅ Added: {title} | SKU: {sku_to_check}")
        else:
            print(f"❌ Failed to add: {title} | {resp.status_code} | {resp.text}")
            return False

    add_to_onsales_collection(product_id)
    return True

# -----------------------------
# Main
# -----------------------------
def main():
    success = 0
    for product in products_on_sale:
        if upsert_product(product):
            success += 1
    print(f"\n📊 DONE: {success}/{len(products_on_sale)} products added/updated")

if __name__ == "__main__":
    main()
