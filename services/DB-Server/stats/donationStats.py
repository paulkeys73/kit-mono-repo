from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict
from decimal import Decimal
from datetime import datetime, date
import logging
import json
import uvicorn
import uuid

from service import donation_stats_service

# -------------------------------------------------
# Loggings
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
def now():
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
        "🔌 CLIENT CONNECTED | id=%s | ip=%s | total=%d",
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
        "❌ CLIENT DISCONNECTED | id=%s | ip=%s | in=%d | out=%d | reason=%s",
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

# -------------------------------------------------
# Broadcastings
# ------------------------------------------------
async def broadcast_stats(stats: dict):
    dead = []

    # Log the full snapshot
    logger.info("📤 BROADCASTING SNAPSHOT → %s", json.dumps(stats, indent=2))

    for client_id, client in clients.items():
        try:
            await client["ws"].send_json({
                "event": "donation.stats.snapshot",
                "payload": stats,
            })
            client["messages_out"] += 1
            client["last_seen"] = now()
            logger.info("📤 BROADCAST → client=%s ip=%s", client_id, client["ip"])
        except Exception as e:
            logger.warning(
                "⚠️ BROADCAST FAILED → client=%s error=%s",
                client_id,
                str(e),
            )
            dead.append(client_id)

    for client_id in dead:
        unregister_client(client_id, "broadcast_failure")

    logger.info("📡 BROADCAST COMPLETE | active_clients=%d", len(clients))

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

        await ws.send_json({
            "event": "donation.stats.snapshot",
            "payload": stats,
        })
        clients[client_id]["messages_out"] += 1
        logger.info("📤 INIT SNAPSHOT → client=%s", client_id)
        logger.info("📤 SNAPSHOT SENT → %s", json.dumps(stats, indent=2))

        while True:
            raw = await ws.receive_text()
            clients[client_id]["messages_in"] += 1
            clients[client_id]["last_seen"] = now()

            msg = json.loads(raw)
            event = msg.get("event")
            clients[client_id]["last_event"] = event

            # Read-only fetch
            if event == "donation.stats.get":
                currency = msg.get("currency", "USD")
                stats = donation_stats_service.get_current_stats(currency)
                stats = json_safe(stats)

                await ws.send_json({
                    "event": "donation.stats.snapshot",
                    "payload": stats,
                })
                clients[client_id]["messages_out"] += 1
                logger.info(
                    "📤 SNAPSHOT → client=%s currency=%s",
                    client_id,
                    currency,
                )
                logger.info("📤 SNAPSHOT SENT → %s", json.dumps(stats, indent=2))
            else:
                logger.warning(
                    "⚠️ UNKNOWN EVENT → client=%s event=%s",
                    client_id,
                    event,
                )

    except WebSocketDisconnect:
        unregister_client(client_id, "ws_disconnect")
    except Exception as e:
        logger.exception("🔥 WS ERROR → client=%s", client_id)
        unregister_client(client_id, f"exception:{e}")
        
        
        
# -------------------------------------------------
# Background polling task
# -------------------------------------------------
import asyncio

POLL_INTERVAL = 5  # seconds

async def stats_updater_loop():
    """
    Polls the DB every POLL_INTERVAL seconds and broadcasts
    new stats to all connected clients.
    """
    last_snapshot = None

    while True:
        try:
            stats = donation_stats_service.get_current_stats("USD")
            stats = json_safe(stats)

            # Only broadcast if something changed
            if stats != last_snapshot:
                last_snapshot = stats
                logger.info("📡 NEW STATS DETECTED → broadcasting")
                await broadcast_stats(stats)

        except Exception as e:
            logger.exception("🔥 Error in stats updater loop: %s", e)

        await asyncio.sleep(POLL_INTERVAL)

# -------------------------------------------------
# Startup
# -------------------------------------------------
@app.on_event("startup")
async def startup_event():
    # Start background polling loop
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
