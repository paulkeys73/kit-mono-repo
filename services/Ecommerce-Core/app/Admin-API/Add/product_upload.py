import json
import logging
from pathlib import Path

from variant_resolver import build_shopify_variants_auto
from variant_helper import upsert_product

# Shopify Core (Single Source of Truth)
from shopify_core import (
    shopify_request,
    API_BASE,
    logger,
    location_id,
    dedupe_images
)

# ------------------------------
# Logging setup (Upload Context)
# ------------------------------
upload_logger = logging.getLogger("ShopifyUpload")
upload_logger.setLevel(logging.INFO)
if not upload_logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    upload_logger.addHandler(ch)

# ------------------------------
# Import helpers
# ------------------------------
from upload.product_detail import fetch_products
from upload.product_options import fetch_product_options
from upload.product_price import fetch_product_prices
from upload.product_link import fetch_product_links
from upload.product_image import fetch_product_media

# ------------------------------
# Local Config
# ------------------------------
BASE_DIR = Path(__file__).parent.resolve()
CATEGORY_FILE = BASE_DIR / "category.json"

with open(CATEGORY_FILE, "r", encoding="utf-8") as f:
    CATEGORIES = json.load(f)

# ------------------------------
# Helpers
# ------------------------------
def normalize_handle(title: str) -> str:
    import re
    h = title.lower()
    h = re.sub(r"[’']", "", h)
    h = re.sub(r"[^a-z0-9]+", "-", h)
    return re.sub(r"-+", "-", h).strip("-")

def get_existing_product(title):
    handle = normalize_handle(title)
    r = shopify_request("GET", f"{API_BASE}/products.json?handle={handle}")
    products = r.json().get("products", [])
    return products[0] if products else None

def resolve_category(product):
    title = (product.get("title") or "").lower()
    for gender, groups in CATEGORIES.items():
        for group, kws in groups.items():
            for kw in kws:
                if kw.lower() in title:
                    return {
                        "product_type": f"{gender} / {group}",
                        "tags": [gender, group]
                    }
    return {
        "product_type": "Uncategorized",
        "tags": ["Uncategorized"]
    }

# ------------------------------
# Main Orchestrator
# ------------------------------
def main():

    upload_logger.info("Shopify Product Upload | Running Helper Modules ⏳")

    # --------------------------
    # Step 0 — Fetch all data
    # --------------------------
    products = fetch_products(verbose=False)
    upload_logger.info("Product Detail Successful ✅")

    media_map = fetch_product_media(verbose=False)
    upload_logger.info("Product Images Successful ✅")

    options_map = fetch_product_options(verbose=False)
    upload_logger.info("Product Options Successful ✅")

    price_rows = fetch_product_prices(verbose=False)
    upload_logger.info("Product Price Successful ✅")

    link_rows = fetch_product_links(verbose=False)
    upload_logger.info("Product Links Successful ✅")

    upload_logger.info("\nAll Module Run Completed Successfully ✅\n")
    upload_logger.info("Starting Product updates | Add/Update\n")

    link_map = link_rows
    price_map = {p["title"]: p.get("variants", []) for p in price_rows}

    # --------------------------
    # Step 1 — Iterate Products
    # --------------------------
    for p in products:
        title = p["title"]
        category = resolve_category(p)
        option_defs = options_map.get(title, [])
        prices = price_map.get(title, [])
        links = link_map.get(title, {})

        # --------------------------
        # Build Shopify-safe variants automatically
        # --------------------------
        variants_dict = build_shopify_variants_auto([{
            "title": title,
            "variants": prices
        }])
        variants = variants_dict.get(title, [])

        upload_logger.info(f"Resolved {len(variants)} variants for '{title}':")
        for v in variants:
            opts = ", ".join(v.get(f"option{i}", "(empty)") for i in range(1, 4))
            upload_logger.info(
                f"  → SKU={v['sku']}, price={v['price']}, compare_at_price={v['compare_at_price']}, options=({opts})"
            )

        # --------------------------
        # Prepare product payload
        # --------------------------
        incoming = {
            "title": title,
            "handle": links.get("handle") or normalize_handle(title),
            "body_html": f"<p>{p.get('description','')}</p>",
            "vendor": links.get("vendor", "Unknown"),
            "product_type": category["product_type"],
            "tags": category["tags"],
            "images": dedupe_images(media_map.get(title, [])),
            "seo_title": links.get("seo_title"),
            "seo_description": links.get("seo_description"),
        }

        extra_details = {
            "title": title,
            "uniqueSellingPoint": p.get("uniqueSellingPoint"),
            "topFeatures": p.get("topFeatures"),
            "techSpecs": p.get("techSpecs"),
            "body_html": incoming["body_html"]
        }

        # --------------------------
        # Fetch existing Shopify product
        # --------------------------
        existing = get_existing_product(title)
        if existing:
            upload_logger.info(f"🔄 Updating {title}\n")
        else:
            upload_logger.info(f"{title} Not Found")
            upload_logger.info(f"🔄 Adding New Product {title}\n")

        # --------------------------
        # Upsert product + variants
        # --------------------------
        action = upsert_product(
            existing,
            incoming,
            variants,
            option_defs,
            extra_details
        )

        upload_logger.info(f"{title} {action} successfully to Shopify. ✅\n")

    upload_logger.info("All products uploaded successfully. ✅")

# ------------------------------
# Entry point
# ------------------------------
if __name__ == "__main__":
    main()
