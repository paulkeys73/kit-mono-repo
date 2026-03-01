from typing import Any, Dict, List

def normalize_product_details(raw: Any) -> List[Dict[str, Any]]:
    """
    Normalize extended product details:
      - title
      - description
      - uniqueSellingPoint
      - topFeatures
      - techSpecs
      - attributes
    """

    normalized = []

    products = raw if isinstance(raw, list) else [raw]

    for product in products:
        details = {
            "id": product.get("id"),
            "title": product.get("title") or product.get("displayName"),
            "description": product.get("description"),
            "uniqueSellingPoint": product.get("uniqueSellingPoint"),
            "topFeatures": product.get("topFeatures"),
            "techSpecs": product.get("techSpecs"),
            "attributes": product.get("attributes"),
        }

        normalized.append(details)

        print(
            f"📦 Product details normalized: "
            f"{details.get('title')}"
        )

    return normalized
