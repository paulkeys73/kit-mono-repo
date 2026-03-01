# E:\Ecommerce-Core\app\Admin-API\Add\upload\variant_resolver.py

import logging
from itertools import product  # keep this import

# ------------------------------
# Logger setup
# ------------------------------
logger = logging.getLogger("variant_resolver")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(ch)


def build_shopify_variants_auto(products_prices: list[dict]) -> dict[str, list[dict]]:
    """
    Automatically build Shopify variants from product_price output.
    - Detects option1/2/3 values from variants
    - Resolves price and compare_at_price safely
    - Ensures unique SKUs
    - Respects Shopify max variants limit (100)
    
    Returns:
        dict mapping product title -> list of variants
    """
    
    def safe_price(val):
        """Convert value to Shopify-friendly string in dollars."""
        try:
            if isinstance(val, dict) and "amount" in val:
                amt = float(val["amount"])
            else:
                amt = float(val)
            if amt >= 1000:  # cents -> dollars
                amt /= 100
            return f"{amt:.2f}" if amt > 0 else None
        except Exception:
            return None

    def variant_key_from_combo(combo):
        return "|".join(str(o).lower() for o in combo if o) or "default"

    result = {}

    for prod in products_prices:  # rename variable from 'product' -> 'prod'
        variants_data = prod.get("variants") or []
        if not variants_data:
            logger.warning(f"No variants found for product '{prod['title']}'")
            continue

        # Automatically detect option values (up to 3 options)
        option_values = []
        for i in range(3):
            vals = list({v["options"].get(f"option{i+1}") or "Default" for v in variants_data})
            option_values.append(vals or ["Default"])

        all_combinations = list(product(*option_values))  # now calls itertools.product correctly
        seen_keys, used_skus, variants = set(), set(), []
        max_variants = 100

        # Build lookup for prices by normalized key
        price_lookup = {v["key"]: v for v in variants_data}

        for idx, combo in enumerate(all_combinations, start=1):
            if len(variants) >= max_variants:
                break

            key = variant_key_from_combo(combo)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            price_info = price_lookup.get(key, {})
            price = safe_price(price_info.get("price") or price_info) or "10.00"
            compare_at_price = safe_price(price_info.get("compare_at_price") or price_info)

            # Ensure unique SKU
            base_sku = str(price_info.get("sku") or f"SKU-{idx}").strip()
            sku = base_sku
            counter = 1
            while sku in used_skus:
                sku = f"{base_sku}-{counter}"
                counter += 1
            used_skus.add(sku)

            # Build variant dict
            variant = {
                "price": price,
                "compare_at_price": compare_at_price,
                "sku": sku,
                "option1": combo[0] or "Default",
                "option2": combo[1] or "Default",
            }
            if combo[2] != "Default" or combo[0] == "Default" or combo[1] == "Default":
                variant["option3"] = combo[2] or "Default"

            logger.info(f"Variant built for '{prod['title']}': {variant}")
            variants.append(variant)

        result[prod["title"]] = variants

    return result
