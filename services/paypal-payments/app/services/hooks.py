# hooks.py
import logging
from fastapi import Request
from datetime import datetime

# -----------------------------
# Setup loggings
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
    logger.info(
        f"[RESPONSE] {request.method} {request.url.path} | "
        f"Status: {response_status} | Body: {response_body}"
    )


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
