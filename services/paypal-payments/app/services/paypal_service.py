#E:\paypal-payments\app\services\paypal_service.py


import base64
import requests
from app.config import settings
import logging

# -----------------------------
# Access Token
# -----------------------------
def get_access_token():
    auth = base64.b64encode(
        f"{settings.PAYPAL_CLIENT_ID}:{settings.PAYPAL_SECRET}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials"}

    resp = requests.post(f"{settings.PAYPAL_BASE_URL}/v1/oauth2/token", headers=headers, data=data)
    resp.raise_for_status()
    return resp.json()["access_token"]

# -----------------------------
# Create Order
# -----------------------------
def create_order(amount: str, currency: str = "USD"):
    token = get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {"currency_code": currency, "value": amount}
            }
        ]
    }

    resp = requests.post(f"{settings.PAYPAL_BASE_URL}/v2/checkout/orders", json=data, headers=headers)
    resp.raise_for_status()
    return resp.json()

# -----------------------------
# Capture Order (Standard Flow)
# -----------------------------
def capture_order(order_id: str):
    token = get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    resp = requests.post(
        f"{settings.PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()

# -----------------------------
# Capture Order With Card (Manual Card Entry)
# -----------------------------
def capture_order_with_card(
    order_id: str,
    card_number: str,
    card_expiry: str,
    card_cvv: str,
    full_name: str,
    billing_country: str = None   # <-- accepted but unused
):
    """
    Capture a PayPal order using manually entered card information.
    The billing_country is stored in Order JSON (frontend) and ignored here.
    """
    token = get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    # Split expiry into month/year
    exp_month, exp_year = card_expiry.split("/")
    exp_year = "20" + exp_year if len(exp_year) == 2 else exp_year

    data = {
        "payment_source": {
            "card": {
                "number": card_number,
                "expiry": f"{exp_year}-{exp_month}",
                "security_code": card_cvv,
                "name": full_name
            }
        }
    }

    resp = requests.post(
        f"{settings.PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
        json=data,
        headers=headers
    )
    resp.raise_for_status()
    return resp.json()


def extract_paypal_card_details(capture_response):
    """
    Extract all card and network info safely and log the extracted details.
    """
    try:
        captures = (
            (capture_response.get("purchase_units") or [{}])[0]
            .get("payments", {})
            .get("captures", [{}])
        )
        capture = captures[0] if captures else {}

        card_src = capture_response.get("payment_source", {}).get("card", {})
        network_ref = (
            (capture.get("network_transaction_reference") or {}).get("id")
            or (capture.get("processor_response") or {}).get("network_transaction_id")
            or None
        )
        network = (
            (capture.get("network_transaction_reference") or {}).get("network")
            or card_src.get("brand")
            or (capture.get("processor_response") or {}).get("network")
            or None
        )
        seller_breakdown = capture.get("seller_receivable_breakdown", {})

        extracted = {
            "card_last4": card_src.get("last_digits"),
            "card_brand": card_src.get("brand"),
            "card_type": card_src.get("type"),
            "paypal_fee": seller_breakdown.get("paypal_fee", {}).get("value"),
            "net_amount": seller_breakdown.get("net_amount", {}).get("value"),
            "network_reference_id": network_ref,
            "network": network,
            "full_name": card_src.get("name"),
            "amount": capture.get("amount", {}).get("value")
        }

        # Log extracted details
        logger.info("Extracted PayPal Card/Network Info:\n%s", extracted)

        return extracted

    except Exception as e:
        logger.error("Failed to extract PayPal card details: %s", e)
        return {
            "card_last4": None,
            "card_brand": None,
            "card_type": None,
            "paypal_fee": None,
            "net_amount": None,
            "network_reference_id": None,
            "network": None,
            "full_name": None,
            "amount": None
        }





# -----------------------------
# Get PayPal Order Details
# -----------------------------
def get_order_details(order_id: str) -> dict:
    """
    Fetch PayPal order details by order ID.
    """
    token = get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    resp = requests.get(
        f"{settings.PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}",
        headers=headers
    )
    resp.raise_for_status()
    return resp.json()
        



# -----------------------------
# Python Logging Setup
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# -----------------------------
# Wrap PayPal functions for logging
# -----------------------------
def log_response(func):
    """
    Decorator to log the JSON response of PayPal API calls.
    """
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        logger.info("PayPal Response from %s:\n%s", func.__name__, result)
        return result
    return wrapper


# Apply decorator to all main API functions
create_order = log_response(create_order)
capture_order = log_response(capture_order)
capture_order_with_card = log_response(capture_order_with_card)
get_order_details = log_response(get_order_details)