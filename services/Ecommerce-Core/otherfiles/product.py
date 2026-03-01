from typing import Dict, Any, List

def normalize_product(raw: Any) -> List[Dict[str, Any]]:
    """
    Normalize product data to include only essential fields:
      - id
      - title
      - vendor (taken directly from product.shop.name if available)
      - variant_count
      - rating
    """
    normalized = []

    # Ensure products is a list
    products = raw if isinstance(raw, list) else [raw]

    for product in products:
        # --- Determine vendor from product.shop.name only ---
        shop_info = product.get("shop") or {}
        vendor_name = shop_info.get("name")  # no fallback

        # --- Determine variant count ---
        variants = product.get("variants") or []
        options = product.get("options") or []
        variant_count = len(variants) if variants else len(options)

        # --- Determine rating ---
        rating = product.get("rating") or {}
        rating_value = rating.get("rating") or rating.get("value") or 0
        rating_count = rating.get("count") or 0

        # --- Build normalized product dictionary ---
        normalized_product = {
            "id": product.get("id") or "",
            "title": product.get("displayName") or product.get("title") or "Unknown Product",
            "vendor": vendor_name,
            "variant_count": variant_count,
            "rating": {
                "value": rating_value,
                "count": rating_count
            }
        }

        normalized.append(normalized_product)

        # Debug log
        print(f"✅ Normalized product: {normalized_product['title']} | Vendor: {vendor_name} | Variants: {variant_count} | Rating: {rating_value} ({rating_count})")

    return normalized
