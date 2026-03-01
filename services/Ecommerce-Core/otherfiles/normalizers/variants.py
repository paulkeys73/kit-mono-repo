from typing import Dict, Any, List

def normalize_variants(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    variants = []

    for v in raw.get("variants", []):
        # Normalize availability
        available = v.get("availableForSale")
        if available is None:
            available = False

        # Normalize options to a dictionary
        options_list = v.get("options", [])
        options = {o.get("name"): o.get("value") for o in options_list if "name" in o and "value" in o}

        # Use variantId as source_variant_id if missing
        source_variant_id = v.get("source_variant_id") or v.get("id")

        variant = {
            "price": v.get("price") or {"amount": 0, "currency": "USD"},
            "available": available,
            "options": options,
            "source_variant_id": source_variant_id,
            "shop": v.get("shop") or {},
            "variant_url": v.get("variantUrl") or "",
        }
        variants.append(variant)

    return variants
