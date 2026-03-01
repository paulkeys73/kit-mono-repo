# E:\Ecommerce-Core\app\Admin-API\Add\variant_helper.py

import time
from shopify_core import shopify_request, set_inventory, API_BASE, logger, location_id

# -----------------------------
# SAFE PRICE NORMALIZER
# -----------------------------
def safe_price(price_field):
    if price_field is None:
        return None
    try:
        # Dict price format
        if isinstance(price_field, dict):
            amt = float(price_field.get("amount", 0))
        else:
            amt = float(price_field)

        # Assume cents if value is suspiciously large
        if amt >= 1000:
            amt = amt / 100

        return f"{amt:.2f}" if amt > 0 else None
    except Exception:
        return None


# -----------------------------
# HTML BLOCK MERGE
# -----------------------------
def _merge_body_html(original_html, extra_details):
    USP_MARKER = "<!-- USP_BLOCK -->"
    FEATURES_MARKER = "<!-- FEATURES_BLOCK -->"
    SPECS_MARKER = "<!-- SPECS_BLOCK -->"

    def strip_block(html, marker):
        parts = html.split(marker)
        if len(parts) >= 3:
            return parts[0] + parts[-1]
        return html

    clean_html = original_html or ""
    for marker in (USP_MARKER, FEATURES_MARKER, SPECS_MARKER):
        clean_html = strip_block(clean_html, marker)

    blocks = ""
    if not extra_details:
        return clean_html

    if extra_details.get("uniqueSellingPoint"):
        blocks += f"""{USP_MARKER}
<div style="padding:12px;margin-bottom:16px;border-left:4px solid #000;">
<strong>Why you’ll love it</strong><br>
{extra_details['uniqueSellingPoint']}
</div>
{USP_MARKER}
"""

    if extra_details.get("topFeatures"):
        blocks += f"""{FEATURES_MARKER}
<h3>Top Features</h3>
<ul>{''.join(f'<li>{f}</li>' for f in extra_details['topFeatures'])}</ul>
{FEATURES_MARKER}
"""

    if extra_details.get("techSpecs"):
        blocks += f"""{SPECS_MARKER}
<h3>Tech Specs</h3>
<ul>{''.join(f'<li>{s}</li>' for s in extra_details['techSpecs'])}</ul>
{SPECS_MARKER}
"""

    return blocks + clean_html


# -----------------------------
# UPSERT PRODUCT
# -----------------------------
def upsert_product(existing, incoming, variants, option_defs, extra_details=None):
    product_id = existing["id"] if existing else None
    action = "Updated" if existing else "Added"

    # -----------------------------
    # BODY HTML MERGE
    # -----------------------------
    incoming["body_html"] = _merge_body_html(
        incoming.get("body_html", ""),
        extra_details
    )

    # -----------------------------
    # OPTIONS — only on create
    # -----------------------------
    max_options = len(option_defs[:3]) if option_defs else 0
    if not existing and max_options:
        incoming["options"] = [
            {"name": opt.get("name", f"Option{i+1}")}
            for i, opt in enumerate(option_defs[:3])
        ]

    # -----------------------------
    # Shopify requires at least one valid variant
    # -----------------------------
    if not existing and variants:
        valid_seed = None
        for v in variants:
            p = safe_price(v.get("price"))
            if p:
                valid_seed = v
                break
        if not valid_seed:
            raise ValueError("No valid variant with price > 0 found.")

        seed_price = safe_price(valid_seed.get("price"))
        incoming["variants"] = [{
            "price": seed_price,
            "sku": valid_seed.get("sku") or "SEED-SKU",
            "inventory_management": "shopify"
        }]

    # -----------------------------
    # CREATE / UPDATE PRODUCT
    # -----------------------------
    logger.info("Uploading Product Details ⏳...")
    resp = shopify_request(
        "PUT" if existing else "POST",
        f"{API_BASE}/products/{product_id}.json" if existing else f"{API_BASE}/products.json",
        json={"product": incoming}
    )
    product = resp.json()["product"]
    product_id = product["id"]
    logger.info(f"Product Details {action} successfully\n")
    time.sleep(0.5)

    # -----------------------------
    # REFRESH PRODUCT DATA
    # -----------------------------
    product = shopify_request(
        "GET",
        f"{API_BASE}/products/{product_id}.json"
    ).json()["product"]

    existing_variants = {
        tuple(v.get(f"option{i+1}", "Default") or "Default" for i in range(3)): v
        for v in product.get("variants", [])
    }

    used_skus = {v.get("sku") for v in product.get("variants", []) if v.get("sku")}
    inventory_jobs = []
    seen_keys = set()

    logger.info("Updating Product Variants ⏳...")

    # -----------------------------
    # UPSERT VARIANTS
    # -----------------------------
    for idx, v in enumerate(variants, start=1):
        key = tuple(v.get(f"option{i+1}", "Default") or "Default" for i in range(3))
        # Only keep options that exist in product
        key = key[:max_options] + ("Default",) * (max_options - len(key))

        if key in seen_keys:
            continue
        seen_keys.add(key)

        price = safe_price(v.get("price"))
        if not price:
            logger.warning(f"Skipping variant {key} due to invalid price")
            continue
        compare_at = safe_price(v.get("compare_at_price"))

        # -----------------------------
        # SKU Normalization
        # -----------------------------
        sku = v.get("sku") or f"SKU-{product_id}-{idx}"
        base_sku = sku
        counter = 1
        while sku in used_skus:
            sku = f"{base_sku}-{counter}"
            counter += 1
        used_skus.add(sku)

        qty = int(v.get("inventory_quantity", 0))
        variant_options = {f"option{i+1}": o for i, o in enumerate(key[:max_options])}

        # -----------------------------
        # UPDATE EXISTING VARIANT
        # -----------------------------
        if key in existing_variants:
            ev = existing_variants[key]
            logger.info(f"Updating variant {key} → {price}")
            shopify_request(
                "PUT",
                f"{API_BASE}/variants/{ev['id']}.json",
                json={"variant": {
                    "price": price,
                    "compare_at_price": compare_at,
                    "sku": sku,
                    **variant_options
                }}
            )
            inventory_jobs.append((ev["inventory_item_id"], qty))

        # -----------------------------
        # CREATE NEW VARIANT
        # -----------------------------
        else:
            logger.info(f"Creating variant {key} → {price}")
            r = shopify_request(
                "POST",
                f"{API_BASE}/products/{product_id}/variants.json",
                json={"variant": {
                    **variant_options,
                    "price": price,
                    "compare_at_price": compare_at,
                    "sku": sku,
                    "inventory_management": "shopify"
                }}
            )
            inventory_jobs.append((r.json()["variant"]["inventory_item_id"], qty))

        time.sleep(0.2)

    # -----------------------------
    # INVENTORY UPDATE
    # -----------------------------
    for inventory_item_id, qty in inventory_jobs:
        set_inventory(inventory_item_id, location_id, qty)
        time.sleep(0.2)

    logger.info(f"Product Variants & Inventory {action} successfully\n")
    return action
