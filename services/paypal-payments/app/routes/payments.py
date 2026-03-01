from fastapi import APIRouter, HTTPException, Request, Response, Query
from typing import Optional, Dict, Any, Union
from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid
import os
import aiohttp

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
from app.routes.rabbitmq import emit_event

router = APIRouter(tags=["Paymentss"])  # no prefix

DONATION_STATS_PUSH_URL = os.getenv(
    "DONATION_STATS_PUSH_URL",
    "http://127.0.0.1:8012/db/donation-stats/push",
)


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


async def emit_payment_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Fire-and-forget style emitter guard so payment endpoints do not fail
    when RabbitMQ is temporarily unavailable.
    """
    try:
        await emit_event(event_type, data)
    except Exception as exc:
        hooks.logger.warning("Rabbit emit failed | event=%s | error=%s", event_type, exc)


async def trigger_stats_refresh(reason: str, order_id: str) -> None:
    """
    Notify stats service to recalculate/broadcast immediately after payment completion.
    This is best-effort and must never fail the payment flow.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(DONATION_STATS_PUSH_URL) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    hooks.logger.warning(
                        "Stats refresh failed | reason=%s | order_id=%s | status=%s | body=%s",
                        reason,
                        order_id,
                        resp.status,
                        body[:300],
                    )
                else:
                    hooks.logger.info(
                        "Stats refresh triggered | reason=%s | order_id=%s",
                        reason,
                        order_id,
                    )
    except Exception as exc:
        hooks.logger.warning(
            "Stats refresh skipped | reason=%s | order_id=%s | error=%s",
            reason,
            order_id,
            exc,
        )


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
                INSERT INTO payments (
                    user_id, amount, currency, status,
                    full_name, user_name, first_name, last_name, email,
                    card_last4, card_brand, card_type,
                    paypal_fee, net_amount,
                    network, network_reference_id,
                    paypal_order_id, source, method, billing_full_name, billing_country, payment_type,
                    metadata, created_at
                ) VALUES (
                    %(user_id)s, %(amount)s, %(currency)s, %(status)s,
                    %(full_name)s, %(user_name)s, %(first_name)s, %(last_name)s, %(email)s,
                    %(card_last4)s, %(card_brand)s, %(card_type)s,
                    %(paypal_fee)s, %(net_amount)s,
                    %(network)s, %(network_reference_id)s,
                    %(paypal_order_id)s, %(source)s, %(method)s, %(billing_full_name)s, %(billing_country)s, %(payment_type)s,
                    %(metadata)s, %(created_at)s
                ) RETURNING *
                """,
                payload,
            )
            return cur.fetchone()
    finally:
        conn.close()



def update_donation(paypal_order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a donation/payment record using PayPal order ID.
    Returns the updated row. Raises 404 if not found.
    """
    conn = db()
    try:
        with conn, conn.cursor() as cur:
            # Build dynamic SET clause
            set_clause = ", ".join(f"{k} = %({k})s" for k in updates)
            updates["paypal_order_id"] = paypal_order_id
            cur.execute(
                f"""
                UPDATE payments
                SET {set_clause}
                WHERE paypal_order_id = %(paypal_order_id)s
                RETURNING *
                """,
                updates
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"Donation with PayPal order {paypal_order_id} not found")
            return row
    finally:
        conn.close()





# -------------------------------------------------
# DB Helpers (paypal_order_id aligned)
# -------------------------------------------------

def fetch_donation_by_order(paypal_order_id: str) -> Dict[str, Any]:
    """
    Fetch a donation/payment record using the PayPal order ID.
    Raises 404 if not found.
    """
    conn = db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM payments WHERE paypal_order_id = %s",
                (paypal_order_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"Donation with PayPal order {paypal_order_id} not found")
            return row
    finally:
        conn.close()



# -------------------------------------------------
# Progress / Stats
# -------------------------------------------------
@router.get("/progress")
async def get_progress(currency: str = Query("USD", description="Currency code (e.g. USD)")):
    conn = db()
    now = now_utc()
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    normalized_currency = (currency or "USD").strip().upper()

    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS count,
                    COALESCE(SUM(amount), 0) AS total,
                    COALESCE(SUM(COALESCE(net_amount, amount)), 0) AS net_total
                FROM payments
                WHERE status = 'COMPLETED'
                  AND currency = %s
                  AND created_at >= %s
                  AND created_at < %s
                """,
                (normalized_currency, month_start, month_end),
            )
            row = cur.fetchone()

            monthly_target = Decimal("0.00")
            cur.execute("SELECT to_regclass('public.donation_stats') AS table_name")
            table_info = cur.fetchone() or {}
            if table_info.get("table_name"):
                cur.execute(
                    """
                    SELECT monthly_target
                    FROM donation_stats
                    WHERE currency = %s AND month = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (normalized_currency, month_start.strftime("%Y-%m")),
                )
                target_row = cur.fetchone()
                if target_row and target_row.get("monthly_target") is not None:
                    monthly_target = d(target_row["monthly_target"])

            monthly_total = d(row["total"])
            remaining = max(monthly_target - monthly_total, Decimal("0.00"))
            percent = float((monthly_total / monthly_target) * 100) if monthly_target > 0 else 0.0

        return {
            "currency": normalized_currency,
            "month": month_start.strftime("%Y-%m"),
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "monthly_target": float(monthly_target),
            "monthly_total": float(monthly_total),
            "net_raised": float(d(row["net_total"])),
            "percent": round(percent, 2),
            "remaining": float(remaining),
            "total_raised": float(monthly_total),
            "payments": row["count"],
            "monthly_count": row["count"],
        }
    finally:
        conn.close()


# -------------------------------------------------
# Create Order Endpoint (fixed with logging)
# -------------------------------------------------
@router.post("/orders/create-order")
async def create_order_endpoint(req: CreateOrderRequest, response: Response, request: Request):
    try:
        await emit_payment_event("paypal.order.create.requested", {
            "user_id": req.user_id,
            "amount": req.amount,
            "currency": req.currency,
            "email": req.email,
        })

        # Convert amount safely
        original_amount = d(req.amount)

        # Create PayPal order
        order = create_order(str(original_amount), req.currency)
        paypal_order_id = str(order.get("id")) if isinstance(order, dict) and "id" in order else None
        if not paypal_order_id:
            raise HTTPException(400, "PayPal order ID missing")

        # Log incoming request
        await hooks.log_request(request)
        hooks.logger.info(f"PayPal order created | Order ID: {paypal_order_id} | Amount: {original_amount} {req.currency}")

        # Prepare user info
        first_name = s(req.first_name, "Anonymous")
        last_name = s(req.last_name, "Anonymous")
        full_name = f"{first_name} {last_name}".strip()
        username = s(req.username, "anonymous")
        email = s(req.email, "unknown@example.com")

        # Prepare donation payload
        donation_payload = {
            "user_id": req.user_id,
            "amount": original_amount,
            "currency": req.currency,
            "status": "CREATING",  # log initial status
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
            "paypal_order_id": paypal_order_id,
            "source": "paypal",
            "method": "pre-capture",
            "billing_full_name": full_name,
            "billing_country": "Unknown",
            "payment_type": "UNKNOWN",
            "metadata": Json({
                "paypal_order_id": paypal_order_id,
                "source": "paypal",
                "method": "pre-capture",
                "billing_country": "Unknown",
                "full_name": full_name,
            }),
            "created_at": now_utc(),
        }

        # Insert into DB
        insert_donation(donation_payload)
        hooks.logger.info(f"Donation record inserted with status='CREATING' | PayPal Order ID: {paypal_order_id}")

        await emit_payment_event("paypal.order.created", {
            "order_id": paypal_order_id,
            "user_id": req.user_id,
            "amount": str(original_amount),
            "currency": req.currency,
            "status": "CREATING",
            "email": email,
        })

        # Set donation cookie
        response.set_cookie(
            key="donation_order_id",
            value=paypal_order_id,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=3600,
        )

        # Log response
        await hooks.log_response(request, 200, order)
        hooks.logger.info(f"Create order response sent | Order ID: {paypal_order_id}")

        # Return response
        return {
            "success": True,
            "order_id": paypal_order_id,
            "approve_link": order["links"][1]["href"],
            "original_amount": float(original_amount),
        }

    except Exception as e:
        await hooks.log_error(request, e)
        hooks.logger.error(f"Failed to create donation record | Error: {str(e)}")
        await emit_payment_event("paypal.order.create.failed", {
            "user_id": req.user_id,
            "amount": req.amount,
            "currency": req.currency,
            "email": req.email,
            "error": str(e),
        })
        raise HTTPException(400, str(e))




# -------------------------------------------------
# Capture Order Endpoint (paypal_order_id aligned)
# -------------------------------------------------
@router.post("/orders/capture-order/{paypal_order_id}", response_model=CaptureOrderResponse)
async def capture_order_endpoint(
    paypal_order_id: str, request: Request, card: Optional[CaptureWithCardRequest] = None
):
    donation: Optional[Dict[str, Any]] = None
    try:
        await emit_payment_event("paypal.order.capture.requested", {
            "order_id": paypal_order_id,
            "capture_method": "card" if card else "paypal",
        })

        # Fetch donation using PayPal order ID
        donation = fetch_donation_by_order(paypal_order_id)

        # Return immediately if already captured
        if donation["status"] == "COMPLETED":
            await emit_payment_event("paypal.order.capture.skipped", {
                "order_id": paypal_order_id,
                "reason": "already_completed",
                "user_id": donation.get("user_id"),
                "status": donation.get("status"),
            })
            return CaptureOrderResponse(
                success=True,
                order_id=paypal_order_id,
                original_amount=float(donation["amount"]),
                fee_deducted=float(donation["paypal_fee"]),
                net_amount=float(donation["net_amount"]),
                status="COMPLETED",
                capture_response={"info": "Already captured"},
                donation_info=donation,
            )

        # Capture payment
        if card:
            capture_response = capture_order_with_card(
                order_id=paypal_order_id,
                card_number=card.card_number,
                card_expiry=card.card_expiry,
                card_cvv=card.card_cvv,
                full_name=s(card.full_name, donation["full_name"]),
                billing_country=s(card.billing_country, "Unknown"),  # frontend value
            )
        else:
            details = get_order_details(paypal_order_id)
            if details.get("status") != "APPROVED":
                raise HTTPException(400, "Order not approved")
            capture_response = capture_order(paypal_order_id)

        # Extract card info from PayPal capture (fees, net, last4, brand, etc.)
        card_info = extract_paypal_card_details(capture_response)

        # Use frontend-provided billing_country directly
        billing_country = s(card.billing_country, "Unknown") if card else donation.get("billing_country", "Unknown")

        # Prepare fields to update donation record
        capture_fields = {
            "amount": d(card_info.get("amount", "0.00")),
            "paypal_fee": d(card_info.get("paypal_fee", "0.00")),
            "net_amount": d(card_info.get("net_amount", "0.00")),
            "card_last4": s(card_info.get("card_last4"), "0000"),
            "card_brand": s(card_info.get("card_brand"), "UNKNOWN"),
            "card_type": s(card_info.get("card_type"), "UNKNOWN"),
            "network": s(card_info.get("network"), "UNKNOWN"),
            "network_reference_id": s(card_info.get("network_reference_id"), "UNKNOWN"),
            "billing_full_name": s(card.full_name, donation["full_name"]) if card else donation["full_name"],
            "billing_country": billing_country,
            "status": "COMPLETED",
            "method": s(card_info.get("method"), "paypal"),
            "source": s(card_info.get("source"), "paypal"),
            "payment_type": s(card_info.get("card_type"), "UNKNOWN"),
            "metadata": Json({
                **donation["metadata"],  # preserve original info
                "billing_country": billing_country,
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

        # Update donation in DB
        updated = update_donation(paypal_order_id, capture_fields)

        await emit_payment_event("paypal.order.captured", {
            "order_id": paypal_order_id,
            "user_id": updated.get("user_id"),
            "amount": updated.get("amount"),
            "paypal_fee": updated.get("paypal_fee"),
            "net_amount": updated.get("net_amount"),
            "currency": updated.get("currency"),
            "status": updated.get("status"),
            "capture_method": "card" if card else "paypal",
            "card_last4": updated.get("card_last4"),
            "card_brand": updated.get("card_brand"),
            "network_reference_id": updated.get("network_reference_id"),
        })
        await trigger_stats_refresh("paypal.order.captured", paypal_order_id)

        # Return response
        return CaptureOrderResponse(
            success=True,
            order_id=paypal_order_id,
            original_amount=float(updated["amount"]),
            fee_deducted=float(updated["paypal_fee"]),
            net_amount=float(updated["net_amount"]),
            status="COMPLETED",
            capture_response=capture_response,
            donation_info=updated,
        )

    except HTTPException as e:
        await emit_payment_event("paypal.order.capture.failed", {
            "order_id": paypal_order_id,
            "user_id": donation.get("user_id") if donation else None,
            "capture_method": "card" if card else "paypal",
            "error": str(e.detail),
            "status_code": e.status_code,
        })
        raise
    except Exception as e:
        await hooks.log_error(request, e)
        await emit_payment_event("paypal.order.capture.failed", {
            "order_id": paypal_order_id,
            "user_id": donation.get("user_id") if donation else None,
            "capture_method": "card" if card else "paypal",
            "error": str(e),
            "status_code": 400,
        })
        raise HTTPException(400, f"Failed to capture order: {e}")



