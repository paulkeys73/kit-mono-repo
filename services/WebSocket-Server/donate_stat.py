import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
import websockets

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("donation-stats-relay")
logger.setLevel(getattr(logging, os.getenv("WS_LOG_LEVEL", "WARNING").upper(), logging.WARNING))
logging.getLogger("websockets.server").setLevel(logging.WARNING)
logging.getLogger("uvicorn.protocols.websockets.websockets_impl").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

# -------------------------------------------------
# FastAPI app
# -------------------------------------------------
app = FastAPI(title="Donation Stats Relay")

# -------------------------------------------------
# In-memory latest stats (authoritative cache)
# -------------------------------------------------
LATEST_STATS: Optional[dict] = None
LATEST_FINGERPRINT: Optional[str] = None

# -------------------------------------------------
# Config
# -------------------------------------------------
DB_WS_URL = os.getenv("DB_DONATION_STATS_WS_URL", "ws://127.0.0.1:8012/db/donation-stats/ws")
RECONNECT_DELAY = 5
PING_INTERVAL = 20
PING_TIMEOUT = 20


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _payload_fingerprint(payload: dict) -> str:
    stable = {
        "currency": payload.get("currency"),
        "today_date": payload.get("today_date"),
        "today_total": payload.get("today_total"),
        "today_count": payload.get("today_count"),
        "month": payload.get("month"),
        "monthly_target": payload.get("monthly_target"),
        "monthly_total": payload.get("monthly_total"),
        "monthly_count": payload.get("monthly_count"),
        "percent": payload.get("percent"),
        "remaining": payload.get("remaining"),
        "net_raised": payload.get("net_raised"),
    }
    return json.dumps(stable, sort_keys=True, separators=(",", ":"))


def _payload_summary(payload: dict) -> str:
    return (
        "currency={currency} month={month} monthly_total={monthly_total} "
        "monthly_count={monthly_count} today_total={today_total} "
        "today_count={today_count} percent={percent}"
    ).format(
        currency=payload.get("currency"),
        month=payload.get("month"),
        monthly_total=payload.get("monthly_total"),
        monthly_count=payload.get("monthly_count"),
        today_total=payload.get("today_total"),
        today_count=payload.get("today_count"),
        percent=payload.get("percent"),
    )


# -------------------------------------------------
# Frontend Connection Manager
# -------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        logger.info("FRONTEND CONNECTED | total=%d", len(self.active_connections))

        if LATEST_STATS:
            await websocket.send_text(json.dumps(LATEST_STATS))
            logger.info("CACHED SNAPSHOT SENT | total=%d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("FRONTEND DISCONNECTED | total=%d", len(self.active_connections))

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return

        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# -------------------------------------------------
# Upstream message handler
# -------------------------------------------------
async def handle_stats_message(data: dict):
    global LATEST_STATS, LATEST_FINGERPRINT

    if data.get("event") != "donation.stats.snapshot":
        return

    payload = data.get("payload") or {}
    fingerprint = _payload_fingerprint(payload)

    if fingerprint == LATEST_FINGERPRINT:
        return

    LATEST_FINGERPRINT = fingerprint

    LATEST_STATS = {
        "event": "donation.stats.update",
        "payload": {
            "progress": {
                "monthly_target": payload.get("monthly_target"),
                "currency": payload.get("currency"),
                "total_raised": payload.get("monthly_total"),
                "remaining": payload.get("remaining"),
                "percent": payload.get("percent"),
            },
            "today": {
                "total_today": payload.get("today_total"),
                "donations_count": payload.get("today_count"),
                "currency": payload.get("currency"),
            },
            "raw": payload,
        },
    }

    await manager.broadcast(LATEST_STATS)
    logger.info(
        "RELAY BROADCAST COMPLETE | active_clients=%d | %s",
        len(manager.active_connections),
        _payload_summary(payload),
    )


# -------------------------------------------------
# Persistent background listener (self-healing)
# -------------------------------------------------
async def stats_listener_loop():
    while True:
        try:
            logger.info("UPSTREAM CONNECTING | url=%s", DB_WS_URL)

            async with websockets.connect(
                DB_WS_URL,
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_TIMEOUT,
            ) as ws:
                logger.info("UPSTREAM CONNECTED")

                # Initial snapshot from server
                initial = await ws.recv()
                await handle_stats_message(json.loads(initial))

                # Explicit fetch request (redundant but safe)
                await ws.send(
                    json.dumps(
                        {
                            "event": "donation.stats.get",
                            "currency": "USD",
                        }
                    )
                )

                async for message in ws:
                    await handle_stats_message(json.loads(message))

        except asyncio.TimeoutError:
            logger.warning("UPSTREAM TIMEOUT")
        except (websockets.WebSocketException, ConnectionRefusedError, OSError) as e:
            logger.error("UPSTREAM ERROR | %s", e)

        logger.info("UPSTREAM RECONNECTING | delay_seconds=%d", RECONNECT_DELAY)
        await asyncio.sleep(RECONNECT_DELAY)


# -------------------------------------------------
# Frontend health/info endpoints
# -------------------------------------------------
def build_health_snapshot() -> dict:
    return {
        "status": "ok",
        "service": "donation-stats-relay",
        "frontend_clients": len(manager.active_connections),
        "has_cached_snapshot": LATEST_STATS is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    return build_health_snapshot()


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
async def ws_health(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            await websocket.send_json(
                {
                    "event": "health.update",
                    "payload": build_health_snapshot(),
                }
            )
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=10)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return


@app.get("/ws/status")
async def ws_status_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/status or /donation-stats/ws",
        },
        headers={"Upgrade": "websocket"},
    )


# -------------------------------------------------
# Frontend WebSocket Endpoint
# -------------------------------------------------
@app.websocket("/ws/status")
@app.websocket("/donation-stats/ws")
async def donation_stats_ws(websocket: WebSocket):
    logger.info("FRONTEND ORIGIN | origin=%s", websocket.headers.get("origin"))
    await manager.connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("event") == "refresh" and LATEST_STATS:
                await websocket.send_text(json.dumps(LATEST_STATS))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("FRONTEND WS ERROR")
        manager.disconnect(websocket)


# -------------------------------------------------
# Startup
# -------------------------------------------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(stats_listener_loop())
