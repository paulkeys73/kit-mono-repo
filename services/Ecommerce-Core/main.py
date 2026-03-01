import os
import json
import re
import uuid
import requests
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --------------------------------------------------
# Load ENV
# --------------------------------------------------
load_dotenv()

SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")

AUTH_URL = "https://api.shopify.com/auth/access_token"
MCP_URL = "https://discover.shopifyapps.com/global/mcp"

if not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
    raise RuntimeError("Missing Shopify credentials in environment")

# --------------------------------------------------
# Constants
# --------------------------------------------------
GLOBAL_DEFAULTS = {
    "maxResultsPerKeyword": 10
}

SEARCH_CONFIG_DIR = "SEARCH-CONFIG"
OUTPUT_FILE = "MCP-Products.json"

# --------------------------------------------------
# FastAPI App
# --------------------------------------------------
app = FastAPI(
    title="Shopify Global Catalog Service",
    version="1.7.0",
)

# --------------------------------------------------
# Models
# --------------------------------------------------
class SearchProduct(BaseModel):
    name: str
    category: Optional[str] = None

class CatalogSearchRequest(BaseModel):
    products: Optional[List[SearchProduct]] = None

class CatalogSearchResponse(BaseModel):
    result: Dict[str, Any]

# --------------------------------------------------
# Auth
# --------------------------------------------------
def get_access_token() -> str:
    payload = {
        "client_id": SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }

    r = requests.post(AUTH_URL, json=payload, timeout=15)
    r.raise_for_status()

    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("No access_token returned by Shopify")

    return token

# --------------------------------------------------
# Helper: Normalize _gsid in URLs
# --------------------------------------------------
def normalize_gsid(url: str, gsid: Optional[str] = None) -> str:
    """
    Injects a dynamic _gsid query parameter into Shopify URLs.
    """
    if not url:
        return url

    gsid = gsid or str(uuid.uuid4()).replace("-", "")[:16]  # short random session id
    if "?_gsid=" in url:
        # replace existing _gsid
        url = re.sub(r"(_gsid=)[^&]+", f"_gsid={gsid}", url)
    else:
        # append _gsid
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}_gsid={gsid}"
    return url

# --------------------------------------------------
# Rating Extraction (PRODUCT LEVEL ONLY)
# --------------------------------------------------
def extract_rating(offer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rating = offer.get("rating")
    if not isinstance(rating, dict):
        return None

    try:
        value = float(rating.get("rating"))
        count = int(rating.get("count"))
    except (TypeError, ValueError):
        return None

    if value <= 0 or count <= 0:
        return None

    return {
        "value": value,
        "count": count
    }

# --------------------------------------------------
# Variant Count Extraction
# --------------------------------------------------
def extract_variant_count(offer: Dict[str, Any]) -> int:
    """
    MCP sometimes exposes variantCount directly.
    Fallback safely to len(variants) if present.
    """
    if isinstance(offer.get("variantCount"), int):
        return offer["variantCount"]

    variants = offer.get("variants")
    if isinstance(variants, list):
        return len(variants)

    return 0

# --------------------------------------------------
# MCP Search (RAW + NORMALIZED)
# --------------------------------------------------
def search_global_products(
    token: str,
    query: str,
    limit: int,
    context: str
) -> List[Dict[str, Any]]:

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 1,
        "params": {
            "name": "search_global_products",
            "arguments": {
                "query": query,
                "context": context,
                "limit": limit,
            },
        },
    }

    r = requests.post(
        MCP_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()
    results: List[Dict[str, Any]] = []

    # Generate a session _gsid for this run
    session_gsid = str(uuid.uuid4()).replace("-", "")[:16]

    for block in data.get("result", {}).get("content", []):
        text = block.get("text")
        if isinstance(text, str):
            try:
                text = json.loads(text)
            except json.JSONDecodeError:
                continue

        for offer in text.get("offers", []):
            # Normalize offer URL
            offer_lookup = normalize_gsid(offer.get("lookupUrl"), session_gsid)

            # Normalize variants URLs
            variants = offer.get("variants") or []
            for variant in variants:
                variant["variantUrl"] = normalize_gsid(variant.get("variantUrl"), session_gsid)
                variant["checkoutUrl"] = normalize_gsid(variant.get("checkoutUrl"), session_gsid)
                variant["lookupUrl"] = normalize_gsid(variant.get("lookupUrl"), session_gsid)

            results.append({
                "id": offer.get("id") or offer.get("productId"),
                "title": offer.get("title"),
                "description": offer.get("description"),
                "uniqueSellingPoint": offer.get("uniqueSellingPoint"),
                "topFeatures": offer.get("topFeatures") or [],
                "techSpecs": offer.get("techSpecs") or [],
                "attributes": offer.get("attributes") or [],
                "media": offer.get("media") or [],
                "priceRange": offer.get("priceRange"),
                "lookupUrl": offer_lookup,
                "vendor": offer.get("vendor"),
                "variant_count": extract_variant_count(offer),
                "rating": extract_rating(offer),
                "options": offer.get("options") or [],
                "variants": variants,
                "raw": offer
            })

    return results

# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/catalog/search", response_model=CatalogSearchResponse)
def catalog_search(payload: Optional[CatalogSearchRequest] = None):
    try:
        token = get_access_token()
        results: List[Dict[str, Any]] = []

        # ------------------------------------------
        # Determine queries
        # ------------------------------------------
        queries: List[SearchProduct] = []

        if payload and payload.products:
            queries = payload.products
        else:
            config_files = [
                f for f in os.listdir(SEARCH_CONFIG_DIR)
                if f.endswith(".json")
            ]

            for file_name in config_files:
                with open(
                    os.path.join(SEARCH_CONFIG_DIR, file_name),
                    "r",
                    encoding="utf-8"
                ) as f:
                    product_search = json.load(f)

                for _, categories in product_search.items():
                    for category, entries in categories.items():
                        for entry in entries:
                            queries.append(
                                SearchProduct(
                                    name=entry["keyword"],
                                    category=category
                                )
                            )

        # ------------------------------------------
        # Execute searches
        # ------------------------------------------
        for item in queries:
            keyword = item.name.strip()
            context = item.category or "general"

            search_results = search_global_products(
                token=token,
                query=keyword,
                limit=GLOBAL_DEFAULTS["maxResultsPerKeyword"],
                context=context,
            )

            results.extend(search_results)

        # ------------------------------------------
        # Persist MCP output
        # ------------------------------------------
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return {
            "result": {
                "total_products": len(results),
                "products": results,
            }
        }

    except requests.HTTPError as e:
        raise HTTPException(502, f"Shopify API error: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))
