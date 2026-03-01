from typing import Dict, Any, List

def build_metafields(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    metafields = []

    if raw.get("rating"):
        metafields.append({
            "namespace": "reviews",
            "key": "rating",
            "type": "json",
            "value": raw["rating"]
        })

    metafields.append({
        "namespace": "source",
        "key": "lookup_url",
        "type": "single_line_text_field",
        "value": raw.get("lookupUrl", "")
    })

    return metafields
