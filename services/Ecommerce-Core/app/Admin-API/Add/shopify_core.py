# E:\Ecommerce-Core\app\Admin-API\Add\shopify_core.py

import os
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv
import time
from requests.exceptions import ReadTimeout, RequestException

# ------------------------------
# Logging
# ------------------------------
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ShopifyCore")

# ------------------------------
# Environment / Config
# ------------------------------
BASE_DIR = Path(__file__).parent.resolve()
ENV_PATH = "/mnt/e/Ecommerce-Core/.env"
load_dotenv(ENV_PATH)

SHOPIFY_STORE_DOMAIN = os.getenv("MY_STORE_DOMAIN")
SHOPIFY_ADMIN_TOKEN = os.getenv("MY_SHOPIFY_ADMIN_TOKEN")

if not SHOPIFY_STORE_DOMAIN or not SHOPIFY_ADMIN_TOKEN:
    raise RuntimeError("Missing Shopify credentials")

API_VERSION = "2026-01"
API_BASE = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{API_VERSION}"
SHOPIFY_MAX_IMAGES = 50

# ------------------------------
# Shopify Headers
# ------------------------------
def shopify_headers():
    return {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN
    }

# ------------------------------
# Shopify Request Wrapper
# ------------------------------
def shopify_request(method, url, retries=3, backoff=2, **kwargs):
    """
    Central Shopify HTTP client with:
    - Retry handling
    - Timeout protection
    - Rate-limit resilience
    - Consistent logging
    """

    for attempt in range(1, retries + 1):

        try:
            response = requests.request(
                method,
                url,
                headers=shopify_headers(),
                timeout=60,
                **kwargs
            )

            # Shopify Rate Limit Handling
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", backoff * attempt))
                logger.warning(f"Shopify rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response

        except ReadTimeout:
            if attempt == retries:
                raise
            logger.warning(f"Shopify timeout retry ({attempt}/{retries}) ⏳")
            time.sleep(backoff * attempt)

        except RequestException as e:
            if attempt == retries:
                logger.error(f"Shopify request failed: {e}")
                raise
            logger.warning(f"Retrying Shopify request ({attempt}/{retries})...")
            time.sleep(backoff * attempt)


# ------------------------------
# Price Normalization
# ------------------------------
def normalize_price(value):
    """
    Normalize Shopify price values safely.

    Supports:
    - int
    - float
    - string
    - dict {amount, currency}

    Returns:
        string decimal "xx.xx"
    """

    if value is None:
        return "0.00"

    try:
        if isinstance(value, dict):
            amount = value.get("amount")
            if amount is None:
                return "0.00"

            amount = float(amount)

            # Assume cents if value is large
            if amount > 999:
                amount = amount / 100

            return f"{amount:.2f}"

        amount = float(value)

        if amount > 999:
            amount = amount / 100

        return f"{amount:.2f}"

    except Exception:
        logger.warning(f"Invalid price value encountered: {value}")
        return "0.00"


# ------------------------------
# Inventory Management
# ------------------------------
def set_inventory(inventory_item_id, location_id, quantity):
    """
    Set Shopify inventory level safely.
    """

    shopify_request(
        "POST",
        f"{API_BASE}/inventory_levels/set.json",
        json={
            "inventory_item_id": inventory_item_id,
            "location_id": location_id,
            "available": int(quantity)
        }
    )


# ------------------------------
# Image Deduplication
# ------------------------------
def dedupe_images(images):
    """
    Remove duplicate Shopify images and enforce platform limits.
    """

    seen = set()
    cleaned = []

    for img in images or []:
        src = img.get("src")
        if src and src not in seen:
            seen.add(src)
            cleaned.append(img)

    return cleaned[:SHOPIFY_MAX_IMAGES]


# ------------------------------
# Location Resolution
# ------------------------------
def get_primary_location_id():
    """
    Resolve best Shopify location for inventory operations.
    """

    try:
        response = shopify_request("GET", f"{API_BASE}/locations.json")
        locations = response.json().get("locations", [])

    except Exception as e:
        raise RuntimeError(f"Failed to fetch Shopify locations: {e}")

    if not locations:
        raise RuntimeError("No Shopify locations found")

    logger.info("Shopify Locations Detected:")

    for loc in locations:
        logger.info(
            f"- {loc.get('name')} | ID={loc.get('id')} | "
            f"Active={loc.get('active')} | "
            f"Online={loc.get('fulfills_online_orders')}"
        )

    # Priority 1 — Active + Online Fulfillment
    for loc in locations:
        if loc.get("active") and loc.get("fulfills_online_orders"):
            logger.info(f"Primary location selected → {loc['name']} ({loc['id']})")
            return loc["id"]

    # Priority 2 — Any Active Location
    for loc in locations:
        if loc.get("active"):
            logger.warning(f"Fallback active location → {loc['name']} ({loc['id']})")
            return loc["id"]

    # Priority 3 — Absolute Fallback
    fallback = locations[0]
    logger.warning(f"Using fallback location → {fallback['name']} ({fallback['id']})")
    return fallback["id"]


# ------------------------------
# Initialize Primary Location
# ------------------------------
location_id = get_primary_location_id()
