# E:\DB-Server\donationData.py

from fastapi import APIRouter, FastAPI, HTTPException, WebSocket
from pydantic import BaseModel
from typing import Optional, Dict
from decimal import Decimal
from datetime import datetime, date
import logging
import json
import uuid
import asyncio
import urllib.request

from service import db_service, donation_stats_service

# -----------------------------
# Loggers setup
# -----------------------------
logger = logging.getLogger("db-server")
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/donations", tags=["donations"])
app = FastAPI(title="Donation & Stats Server", version="2.0")
STATS_PUSH_URL = "http://127.0.0.1:8012/db/donation-stats/push"

# ----------------------------
# Pydantic donation model
# -----------------------------
class DonationPayload(BaseModel):
    id: Optional[str] = None
    user_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    full_name: Optional[str] = None
    user_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    card_type: Optional[str] = None
    network: Optional[str] = None
    network_reference_id: Optional[str] = None
    paypal_fee: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    tier_id: Optional[str] = None
    order_id: Optional[str] = None
    source: Optional[str] = None
    method: Optional[str] = None
    billing_full_name: Optional[str] = None
    billing_country: Optional[str] = None
    payment_type: Optional[str] = None
    extra_metadata: Optional[Dict] = None


class DonationTargetPayload(BaseModel):
    currency: str = "USD"
    month: Optional[str] = None  # YYYY-MM
    monthly_target: Decimal = Decimal("7000")

# -----------------------------
# Helpers
# -----------------------------
def convert_decimals(obj: Dict):
    for k, v in obj.items():
        if isinstance(v, Decimal):
            obj[k] = float(v)
        elif isinstance(v, dict):
            obj[k] = convert_decimals(v)
    return obj

def json_safe(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    return obj

def now():
    return datetime.utcnow().isoformat()


def _post_stats_snapshot(snapshot: dict) -> None:
    req = urllib.request.Request(
        STATS_PUSH_URL,
        data=json.dumps(snapshot).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        resp.read()


async def recalculate_and_push_stats(currency: str = "USD") -> Optional[dict]:
    """
    Recalculate donation stats from current DB state and push immediately
    to the stats websocket service.
    """
    try:
        stats = donation_stats_service.recalculate_current_stats(currency or "USD")
        stats = json_safe(stats)

        # Local broadcast (if any clients are connected here)
        await broadcast_stats(stats)

        # Cross-service push for stats/donationStats clients (WebSocket-Server relay)
        try:
            await asyncio.to_thread(_post_stats_snapshot, stats)
        except Exception as push_err:
            logger.warning("⚠️ Stats push skipped | reason=%s", push_err)

        return stats
    except Exception:
        logger.exception("🔥 Failed to recalculate/push donation stats")
        return None

# -----------------------------
# WS client registry & broadcast
# -----------------------------
clients: Dict[str, dict] = {}

def register_client(ws: WebSocket) -> str:
    client_id = str(uuid.uuid4())
    clients[client_id] = {
        "id": client_id,
        "ws": ws,
        "ip": ws.client.host if ws.client else "unknown",
        "connected_at": now(),
        "last_seen": now(),
        "messages_in": 0,
        "messages_out": 0,
        "last_event": None,
    }
    logger.info("🔌 CLIENT CONNECTED | id=%s | ip=%s | total=%d", client_id, clients[client_id]["ip"], len(clients))
    return client_id

def unregister_client(client_id: str, reason: str):
    client = clients.pop(client_id, None)
    if not client:
        return
    logger.info("❌ CLIENT DISCONNECTED | id=%s | ip=%s | reason=%s", client_id, client["ip"], reason)

async def broadcast_stats(stats: dict):
    dead = []
    for client_id, client in clients.items():
        try:
            await client["ws"].send_json({"event": "donation.stats.snapshot", "payload": stats})
            client["messages_out"] += 1
            client["last_seen"] = now()
        except Exception:
            dead.append(client_id)
    for cid in dead:
        unregister_client(cid, "broadcast_failure")
    logger.info("📡 BROADCAST COMPLETE | active_clients=%d", len(clients))

# -----------------------------
# Donation endpoints
# -----------------------------
@router.post("/", summary="Insert a new donation (upsert)")
async def post_donation(payload: DonationPayload):
    """
    Insert a new donation or update existing one if the ID already exists.
    This makes the operation idempotent and avoids duplicate primary key errors.
    """
    try:
        donation_data = convert_decimals(payload.dict())

        if not donation_data.get("id"):
            raise HTTPException(status_code=400, detail="Donation id is required")

        # Check if donation already exists
        existing = db_service.get_donation_by_id(donation_data["id"])
        if existing:
            # If it exists, update instead of inserting
            order_id = existing.order_id
            donation_data.pop("id", None)  # never update the PK
            db_service.update_donation_by_order_id(order_id, donation_data)
            logger.info("Donation already exists, updated instead | id=%s", existing.id)
            await recalculate_and_push_stats(str(donation_data.get("currency") or "USD"))
            return {"success": True, "donation_id": existing.id, "updated": True}

        # Otherwise, insert as new
        db_service.insert_donation(donation_data)
        logger.info("Donation inserted successfully | id=%s", donation_data["id"])
        await recalculate_and_push_stats(str(donation_data.get("currency") or "USD"))
        return {"success": True, "donation_id": donation_data["id"], "created": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error inserting/updating donation")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/update-by-order/{order_id}", summary="Update donation by order_id")
async def update_donation_by_order(order_id: str, payload: DonationPayload):
    """
    Update an existing donation by order_id. Fails if no fields provided or
    donation not found.
    """
    try:
        updates = convert_decimals(payload.dict(exclude_unset=True))

        # Prevent overwriting critical fields
        updates.pop("order_id", None)
        updates.pop("id", None)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields provided for update")

        updated = db_service.update_donation_by_order_id(order_id, updates)

        if not updated:
            raise HTTPException(
                status_code=404,
                detail=f"Donation with order_id {order_id} not found"
            )

        logger.info("Donation updated successfully | order_id=%s", order_id)
        await recalculate_and_push_stats(str(getattr(updated, "currency", "USD") or "USD"))
        return {"success": True, "order_id": order_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating donation by order_id")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------
# Donation Stats endpoint
# -----------------------------
@router.post("/stats/", summary="Upsert donation statistics")
async def update_donation_stats(payload: dict):
   

    try:
        month_start = payload.get("month_start")
        updated_at_str = payload.get("updated_at")
        month = month_start.split("T")[0][:7] if month_start else datetime.utcnow().strftime("%Y-%m")
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00")) if updated_at_str else datetime.utcnow()

        normalized = {
            "currency": str(payload.get("currency", "USD")),
            "today_date": datetime.utcnow().date(),
            "today_total": float(payload.get("total_raised", 0)),
            "today_count": int(payload.get("donations_count", 0)),
            "month": month,
            "monthly_target": float(payload.get("monthly_target", 0)),
            "monthly_total": float(payload.get("total_raised", 0)),
            "monthly_count": int(payload.get("donations_count", 0)),
            "percent": float(payload.get("percent", 0)),
            "remaining": float(payload.get("remaining", 0)),
            "updated_at": updated_at,
        }

        stats = donation_stats_service.upsert_stats(normalized)
        stats = json_safe(stats)

    except Exception as e:
        logger.exception("🔥 STATS UPSERT FAILED")
        raise HTTPException(status_code=500, detail=f"Donation stats update failed: {e}")

    # Broadcast to WS clients + push to stats websocket service
    await broadcast_stats(stats)
    try:
        await asyncio.to_thread(_post_stats_snapshot, stats)
    except Exception as push_err:
        logger.warning("⚠️ Stats push skipped | reason=%s", push_err)

    return {"status": "ok", "broadcasted": True, "updated_at": now()}


@router.post("/stats/target", summary="Set monthly target for donation stats")
async def set_monthly_target(payload: DonationTargetPayload):
    """
    Set monthly target (e.g. USD 7000) and immediately rebroadcast stats.
    """
    try:
        currency = str(payload.currency or "USD")[:7]
        current_stats = donation_stats_service.get_current_stats(currency)

        month = str(payload.month or current_stats.get("month") or datetime.utcnow().strftime("%Y-%m"))[:7]
        monthly_total = Decimal(str(current_stats.get("monthly_total", 0) or 0))
        monthly_count = int(current_stats.get("monthly_count", 0) or 0)
        today_total = Decimal(str(current_stats.get("today_total", 0) or 0))
        today_count = int(current_stats.get("today_count", 0) or 0)
        monthly_target = Decimal(str(payload.monthly_target or 0))
        remaining = max(monthly_target - monthly_total, Decimal("0"))
        percent = float((monthly_total / monthly_target) * 100) if monthly_target > 0 else 0.0

        normalized = {
            "currency": currency,
            "today_date": datetime.utcnow().date(),
            "today_total": today_total,
            "today_count": today_count,
            "month": month,
            "monthly_target": monthly_target,
            "monthly_total": monthly_total,
            "monthly_count": monthly_count,
            "percent": round(percent, 2),
            "remaining": remaining,
        }

        stats = donation_stats_service.upsert_stats(normalized)
        stats = json_safe(stats)

    except Exception as e:
        logger.exception("🔥 STATS TARGET UPDATE FAILED")
        raise HTTPException(status_code=500, detail=f"Donation target update failed: {e}")

    await broadcast_stats(stats)
    try:
        await asyncio.to_thread(_post_stats_snapshot, stats)
    except Exception as push_err:
        logger.warning("⚠️ Stats push skipped | reason=%s", push_err)

    return {"status": "ok", "target_set": True, "payload": stats, "updated_at": now()}

# -----------------------------
# Mount donation router
# -----------------------------
app.include_router(router)
