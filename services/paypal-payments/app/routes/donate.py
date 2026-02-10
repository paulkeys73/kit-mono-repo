from fastapi import APIRouter, HTTPException, Request, Response
from typing import Optional, Dict, Any, Union
from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from psycopg2.extras import Json

from app.config import settings
from app.services.paypal_service import (
    create_order,
    capture_order,
    capture_order_with_card,
    extract_paypal_card_details,
    get_order_details,
)
from app.services import hooks

router = APIRouter(tags=["Donations"])  # no prefix


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def d(value: Any, default="0.00") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def s(value: Any, default: str = "Unknown") -> str:
    return str(value).strip() if value not in (None, "") else default


# -------------------------------------------------
# Pydantic models
# -------------------------------------------------
class CreateOrderRequest(BaseModel):
    amount: Union[str, float]
    currency: str
    user_id: int
    username: Optional[str] = ""
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    email: Optional[str] = ""


class CaptureWithCardRequest(BaseModel):
    card_number: str
    card_expiry: str
    card_cvv: str
    full_name: Optional[str] = ""
    user_email: Optional[str] = ""
    user_name: Optional[str] = ""
    billing_country: Optional[str] = "Unknown"


class CaptureOrderResponse(BaseModel):
    success: bool
    order_id: str
    original_amount: float
    fee_deducted: float
    net_amount: float
    status: str
    capture_response: dict
    donation_info: dict


# -------------------------------------------------
# DB helpers
# -------------------------------------------------
def db():
    return settings.get_db_connection()


def insert_donation(payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO donations (
                    id, user_id, amount, currency, status,
                    full_name, user_name, first_name, last_name, email,
                    card_last4, card_brand, card_type,
                    paypal_fee, net_amount,
                    network, network_reference_id,
                    order_id, source, method, billing_full_name, billing_country, payment_type,
                    metadata, created_at
                ) VALUES (
                    %(id)s, %(user_id)s, %(amount)s, %(currency)s, %(status)s,
                    %(full_name)s, %(user_name)s, %(first_name)s, %(last_name)s, %(email)s,
                    %(card_last4)s, %(card_brand)s, %(card_type)s,
                    %(paypal_fee)s, %(net_amount)s,
                    %(network)s, %(network_reference_id)s,
                    %(order_id)s, %(source)s, %(method)s, %(billing_full_name)s, %(billing_country)s, %(payment_type)s,
                    %(metadata)s, %(created_at)s
                ) RETURNING *
                """,
                payload,
            )
            return cur.fetchone()
    finally:
        conn.close()


def update_donation(order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    conn = db()
    try:
        with conn, conn.cursor() as cur:
            sets = ", ".join(f"{k} = %({k})s" for k in updates)
            updates["order_id"] = order_id
            cur.execute(
                f"""
                UPDATE donations
                SET {sets}
                WHERE order_id = %(order_id)s
                RETURNING *
                """,
                updates,
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Donation not found")
            return row
    finally:
        conn.close()


def fetch_donation_by_order(order_id: str) -> Dict[str, Any]:
    conn = db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM donations WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Donation not found")
            return row
    finally:
        conn.close()


# -------------------------------------------------
# Progress / Stats
# -------------------------------------------------
@router.get("/progress")
async def get_progress():
    conn = db()
    now = now_utc()
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
                FROM donations
                WHERE status = 'COMPLETED' AND created_at >= %s
                """,
                (month_start,),
            )
            row = cur.fetchone()
        return {
            "month_start": month_start.isoformat(),
            "total_raised": float(row["total"]),
            "donations_count": row["count"],
        }
    finally:
        conn.close()


# -------------------------------------------------
# Create Order Endpoint
# -------------------------------------------------
@router.post("/orders/create-order")
async def create_order_endpoint(req: CreateOrderRequest, response: Response, request: Request):
    try:
        original_amount = d(req.amount)
        order = create_order(str(original_amount), req.currency)

        await hooks.log_request(request)

        first_name = s(req.first_name, "Anonymous")
        last_name = s(req.last_name, "Anonymous")
        full_name = f"{first_name} {last_name}".strip()
        username = s(req.username, "anonymous")
        email = s(req.email, "unknown@example.com")

        donation_payload = {
            "id": str(uuid.uuid4()),
            "user_id": req.user_id,
            "amount": original_amount,
            "currency": req.currency,
            "status": "CREATING",
            "full_name": full_name,
            "user_name": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "card_last4": "0000",
            "card_brand": "UNKNOWN",
            "card_type": "UNKNOWN",
            "paypal_fee": Decimal("0.00"),
            "net_amount": original_amount,
            "network": "paypal",
            "network_reference_id": "",
            "order_id": s(order.get("id")),
            "source": "paypal",
            "method": "pre-capture",
            "billing_full_name": full_name,
            "billing_country": "Unknown",
            "payment_type": "UNKNOWN",
            "metadata": Json({
                "order_id": s(order.get("id")),
                "source": "paypal",
                "method": "pre-capture",
                "billing_country": "Unknown",
                "full_name": full_name,
            }),
            "created_at": now_utc(),
        }

        insert_donation(donation_payload)

        response.set_cookie(
            key="donation_order_id",
            value=s(order.get("id")),
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=3600,
        )

        await hooks.log_response(request, 200, order)

        return {
            "success": True,
            "order_id": s(order.get("id")),
            "approve_link": order["links"][1]["href"],
            "original_amount": float(original_amount),
        }

    except Exception as e:
        await hooks.log_error(request, e)
        raise HTTPException(400, str(e))


# -------------------------------------------------
# Capture Order Endpoint
# -------------------------------------------------
@router.post("/orders/capture-order/{order_id}", response_model=CaptureOrderResponse)
async def capture_order_endpoint(order_id: str, request: Request, card: Optional[CaptureWithCardRequest] = None):
    try:
        donation = fetch_donation_by_order(order_id)

        if donation["status"] == "COMPLETED":
            return CaptureOrderResponse(
                success=True,
                order_id=order_id,
                original_amount=float(donation["amount"]),
                fee_deducted=float(donation["paypal_fee"]),
                net_amount=float(donation["net_amount"]),
                status="COMPLETED",
                capture_response={"info": "Already captured"},
                donation_info=donation,
            )

        # Capture the payment
        if card:
            capture_response = capture_order_with_card(
                order_id=order_id,
                card_number=card.card_number,
                card_expiry=card.card_expiry,
                card_cvv=card.card_cvv,
                full_name=s(card.full_name, "Anonymous"),
                billing_country=s(card.billing_country, "Unknown"),
            )
        else:
            details = get_order_details(order_id)
            if details.get("status") != "APPROVED":
                raise HTTPException(400, "Order not approved")
            capture_response = capture_order(order_id)

        # Extract capture-specific info
        card_info = extract_paypal_card_details(capture_response)
        
        billing_country = (
    s(card_info.get("billing_country"))
    or s(card_info.get("card_country"))  # fallback from card info if available
    or "Unknown"
)

        # Fill capture-specific fields
        capture_fields = {
            "amount": d(card_info.get("amount", "0.00")),
            "paypal_fee": d(card_info.get("paypal_fee", "0.00")),
            "net_amount": d(card_info.get("net_amount", "0.00")),
            "card_last4": s(card_info.get("card_last4"), "0000"),
            "card_brand": s(card_info.get("card_brand"), "UNKNOWN"),
            "card_type": s(card_info.get("card_type"), "UNKNOWN"),
            "network": s(card_info.get("network"), "UNKNOWN"),
            "network_reference_id": s(card_info.get("network_reference_id"), "UNKNOWN"),
            "billing_full_name": s(card_info.get("full_name"), donation["full_name"]),
            "billing_country": s(card_info.get("billing_country"), "Unknown"),
            "status": "COMPLETED",
            "method": s(card_info.get("method"), "paypal"),
            "source": s(card_info.get("source"), "paypal"),
            "payment_type": s(card_info.get("card_type"), "UNKNOWN"),
            "metadata": Json({
                **donation["metadata"],  # retain original donor info
                "billing_country": s(card_info.get("billing_country"), "Unknown"),
                "method": s(card_info.get("method"), "paypal"),
                "source": s(card_info.get("source"), "paypal"),
                "capture_amount": str(card_info.get("amount", "0.00")),
                "paypal_fee": str(card_info.get("paypal_fee", "0.00")),
                "net_amount": str(card_info.get("net_amount", "0.00")),
                "card_last4": s(card_info.get("card_last4"), "0000"),
                "card_brand": s(card_info.get("card_brand"), "UNKNOWN"),
                "card_type": s(card_info.get("card_type"), "UNKNOWN"),
                "network": s(card_info.get("network"), "UNKNOWN"),
                "network_reference_id": s(card_info.get("network_reference_id"), "UNKNOWN"),
            }),
        }

        updated = update_donation(order_id, capture_fields)

        return CaptureOrderResponse(
            success=True,
            order_id=order_id,
            original_amount=float(updated["amount"]),
            fee_deducted=float(updated["paypal_fee"]),
            net_amount=float(updated["net_amount"]),
            status="COMPLETED",
            capture_response=capture_response,
            donation_info=updated,
        )

    except HTTPException:
        raise
    except Exception as e:
        await hooks.log_error(request, e)
        raise HTTPException(400, f"Failed to capture order: {e}")

