# hooks.py
import logging
from fastapi import Request
from datetime import datetime
import os
import json

# -----------------------------
# Setup logging
# -----------------------------
logger = logging.getLogger("paypal_hooks")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')

file_handler = logging.FileHandler("paypal_hooks.log")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# -----------------------------
# Track logged orders to prevent duplicate logging
# -----------------------------
_logged_orders = set()

def clear_logged_orders():
    """Clear the set of already-logged PayPal orders."""
    global _logged_orders
    _logged_orders.clear()

# -----------------------------
# Middleware hooks
# -----------------------------
async def log_request(request: Request):
    """
    Log incoming requests: method, path, body.
    """
    try:
        body = await request.json()
    except Exception:
        body = "Unable to parse body"

    logger.info(
        f"[REQUEST] {request.method} {request.url.path} | Body: {body}"
    )


async def log_response(request: Request, response_status: int, response_body: dict):
    """
    Log outgoing responses: status, body.
    """
    # Only log once per PayPal order
    paypal_order_id = response_body.get("order_id") if isinstance(response_body, dict) else None
    if paypal_order_id and paypal_order_id not in _logged_orders:
        logger.info(
            f"[RESPONSE] {request.method} {request.url.path} | "
            f"Status: {response_status} | Body: {json.dumps(response_body)}"
        )
        _logged_orders.add(paypal_order_id)


async def log_error(request: Request, exc: Exception):
    """
    Log exceptions raised during processing.
    """
    logger.error(
        f"[ERROR] {request.method} {request.url.path} | Exception: {exc}"
    )


# -----------------------------
# Helper for timestamp and debug ID
# -----------------------------
def extract_debug_info(paypal_response: dict):
    """
    Extract timestamp, HTTP status, and PayPal debug ID from capture response.
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    status = paypal_response.get("status", "N/A")
    debug_id = paypal_response.get("debug_id", "N/A")
    return {
        "timestamp": timestamp,
        "status": status,
        "debug_id": debug_id
    }
