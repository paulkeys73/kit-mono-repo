from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from typing import Dict
from decimal import Decimal
from datetime import datetime, date
import asyncio
import json
import logging
import uuid

import uvicorn

from service import donation_stats_service

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("donation-stats-ws")

# -------------------------------------------------
# FastAPI app
# -------------------------------------------------
app = FastAPI(
    title="Donation Stats DB Server",
    version="1.3.0",
)

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def now() -> str:
    return datetime.utcnow().isoformat()


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


def _stats_fingerprint(stats: dict) -> str:
    """
    Build a stable fingerprint for change detection.
    Ignore volatile fields like id and updated_at.
    """
    stable = {
        "currency": stats.get("currency"),
        "today_date": stats.get("today_date"),
        "today_total": stats.get("today_total"),
        "today_count": stats.get("today_count"),
        "month": stats.get("month"),
        "monthly_target": stats.get("monthly_target"),
        "monthly_total": stats.get("monthly_total"),
        "monthly_count": stats.get("monthly_count"),
        "percent": stats.get("percent"),
        "remaining": stats.get("remaining"),
        "net_raised": stats.get("net_raised"),
    }
    return json.dumps(json_safe(stable), sort_keys=True, separators=(",", ":"))


def _stats_summary(stats: dict) -> str:
    return (
        "currency={currency} month={month} monthly_total={monthly_total} "
        "monthly_count={monthly_count} today_total={today_total} "
        "today_count={today_count} percent={percent}"
    ).format(
        currency=stats.get("currency"),
        month=stats.get("month"),
        monthly_total=stats.get("monthly_total"),
        monthly_count=stats.get("monthly_count"),
        today_total=stats.get("today_total"),
        today_count=stats.get("today_count"),
        percent=stats.get("percent"),
    )


# -------------------------------------------------
# Client Registry
# -------------------------------------------------
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
    logger.info(
        "CLIENT CONNECTED | id=%s | ip=%s | total=%d",
        client_id,
        clients[client_id]["ip"],
        len(clients),
    )
    return client_id


def unregister_client(client_id: str, reason: str):
    client = clients.pop(client_id, None)
    if not client:
        return
    logger.info(
        "CLIENT DISCONNECTED | id=%s | ip=%s | in=%d | out=%d | reason=%s",
        client_id,
        client["ip"],
        client["messages_in"],
        client["messages_out"],
        reason,
    )


# ------------------------------------------------
# Health
# -------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "donation-stats-ws",
        "clients_connected": len(clients),
        "ts": now(),
    }


@app.get("/ws/health")
async def ws_health_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/health",
        },
        headers={"Upgrade": "websocket"},
    )


@app.websocket("/ws/health")
async def ws_health(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(
                {
                    "event": "health.update",
                    "payload": await health(),
                }
            )
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=10)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return


# -------------------------------------------------
# Broadcasting
# ------------------------------------------------
async def broadcast_stats(stats: dict):
    if not clients:
        logger.info("BROADCAST SKIPPED | reason=no_clients | %s", _stats_summary(stats))
        return

    dead = []
    sent = 0

    for client_id, client in clients.items():
        try:
            await client["ws"].send_json(
                {
                    "event": "donation.stats.snapshot",
                    "payload": stats,
                }
            )
            client["messages_out"] += 1
            client["last_seen"] = now()
            sent += 1
        except Exception as e:
            logger.warning("BROADCAST FAILED | client=%s | error=%s", client_id, str(e))
            dead.append(client_id)

    for client_id in dead:
        unregister_client(client_id, "broadcast_failure")

    logger.info(
        "BROADCAST COMPLETE | sent=%d | failed=%d | active_clients=%d | %s",
        sent,
        len(dead),
        len(clients),
        _stats_summary(stats),
    )


# -------------------------------------------------
# WebSocket Endpoint
# -------------------------------------------------
@app.websocket("/db/donation-stats/ws")
async def ws_donation_stats(ws: WebSocket):
    await ws.accept()
    client_id = register_client(ws)

    try:
        # Initial snapshot (DB only)
        stats = donation_stats_service.get_current_stats("USD")
        stats = json_safe(stats)

        await ws.send_json(
            {
                "event": "donation.stats.snapshot",
                "payload": stats,
            }
        )
        clients[client_id]["messages_out"] += 1
        logger.info("INIT SNAPSHOT SENT | client=%s | %s", client_id, _stats_summary(stats))

        while True:
            raw = await ws.receive_text()
            clients[client_id]["messages_in"] += 1
            clients[client_id]["last_seen"] = now()

            msg = json.loads(raw)
            event = msg.get("event")
            clients[client_id]["last_event"] = event

            if event == "donation.stats.get":
                currency = msg.get("currency", "USD")
                stats = donation_stats_service.get_current_stats(currency)
                stats = json_safe(stats)

                await ws.send_json(
                    {
                        "event": "donation.stats.snapshot",
                        "payload": stats,
                    }
                )
                clients[client_id]["messages_out"] += 1
                logger.info(
                    "SNAPSHOT SENT | client=%s | currency=%s | %s",
                    client_id,
                    currency,
                    _stats_summary(stats),
                )
            else:
                logger.warning("UNKNOWN EVENT | client=%s | event=%s", client_id, event)

    except WebSocketDisconnect:
        unregister_client(client_id, "ws_disconnect")
    except Exception as e:
        logger.exception("WS ERROR | client=%s", client_id)
        unregister_client(client_id, f"exception:{e}")


@app.post("/db/donation-stats/push")
async def push_stats_now(payload: dict | None = None):
    """
    Force an immediate stats broadcast.
    If payload is provided, broadcast it directly.
    Otherwise recalculate from DB and broadcast.
    """
    if payload:
        stats = json_safe(payload)
    else:
        stats = json_safe(donation_stats_service.recalculate_current_stats("USD"))

    await broadcast_stats(stats)
    return {"status": "ok", "clients": len(clients), "ts": now()}


# -------------------------------------------------
# Background polling task
# -------------------------------------------------
POLL_INTERVAL = 5


async def stats_updater_loop():
    """
    Polls the DB and broadcasts only when business-relevant values changed.
    """
    last_fingerprint = None

    while True:
        try:
            # Recalculate from payments each cycle so stats stay fresh even when
            # payments are completed by external services (e.g. paypal-payments).
            stats = donation_stats_service.recalculate_current_stats("USD")
            stats = json_safe(stats)
            fingerprint = _stats_fingerprint(stats)

            if fingerprint != last_fingerprint:
                last_fingerprint = fingerprint
                logger.info("STATS CHANGED | source=polling | %s", _stats_summary(stats))
                await broadcast_stats(stats)

        except Exception as e:
            logger.exception("STATS UPDATER ERROR | %s", e)

        await asyncio.sleep(POLL_INTERVAL)


# -------------------------------------------------
# Startup
# -------------------------------------------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(stats_updater_loop())


# -------------------------------------------------
# Run
# -------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "donationStats:app",
        host="0.0.0.0",
        port=8012,
        reload=True,
    )

