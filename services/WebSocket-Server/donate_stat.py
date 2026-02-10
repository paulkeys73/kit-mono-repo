# E:\WebSocket-Server\donate_stat.py

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import websockets
from datetime import datetime

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("donate-stat-ws")

# -------------------------------------------------
# FastAPI app
# -------------------------------------------------
app = FastAPI(title="Donation Stats Relay")

# -------------------------------------------------
# In-memory latest stats (authoritative cache)
# -------------------------------------------------
LATEST_STATS: Optional[dict] = None

# -------------------------------------------------
# Config
# -------------------------------------------------
DB_WS_URL = "ws://127.0.0.1:8012/db/donation-stats/ws"
RECONNECT_DELAY = 5
PING_INTERVAL = 20
PING_TIMEOUT = 20

# -------------------------------------------------
# Frontend Connection Manager
# -------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        logger.info("🔌 Frontend connected | total=%d", len(self.active_connections))

        if LATEST_STATS:
            await websocket.send_text(json.dumps(LATEST_STATS))
            logger.info("📤 Sent cached stats to new frontend client")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("❌ Frontend disconnected | total=%d", len(self.active_connections))

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
    global LATEST_STATS

    if data.get("event") != "donation.stats.snapshot":
        return

    payload = data["payload"]

    LATEST_STATS = {
        "event": "donation.stats.update",
        "payload": {
            "progress": {
                "monthly_target": payload["monthly_target"],
                "currency": payload["currency"],
                "total_raised": payload["monthly_total"],
                "remaining": payload["remaining"],
                "percent": payload["percent"],
            },
            "today": {
                "total_today": payload["today_total"],
                "donations_count": payload["today_count"],
                "currency": payload["currency"],
            },
            "raw": payload,
        },
    }

    logger.info("📡 Stats refreshed → broadcasting")
    await manager.broadcast(LATEST_STATS)

# -------------------------------------------------
# Persistent background listener (self-healing)
# -------------------------------------------------
async def stats_listener_loop():
    while True:
        try:
            logger.info("🚀 Connecting to DB WebSocket → %s", DB_WS_URL)

            async with websockets.connect(
                DB_WS_URL,
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_TIMEOUT,
            ) as ws:
                logger.info("✅ Connected to DB WebSocket")

                # Initial snapshot from server
                initial = await ws.recv()
                await handle_stats_message(json.loads(initial))

                # Explicit fetch request (redundant but safe)
                await ws.send(json.dumps({
                    "event": "donation.stats.get",
                    "currency": "USD",
                }))

                async for message in ws:
                    await handle_stats_message(json.loads(message))

        except asyncio.TimeoutError:
            logger.warning("⏱️ WS timeout")
        except (
            websockets.WebSocketException,
            ConnectionRefusedError,
            OSError,
        ) as e:
            logger.error("❌ WS error: %s", e)

        logger.info("🔄 Reconnecting in %ds...", RECONNECT_DELAY)
        await asyncio.sleep(RECONNECT_DELAY)

# -------------------------------------------------
# Frontend WebSocket Endpoint
# -------------------------------------------------
@app.websocket("/donation-stats/ws")
async def donation_stats_ws(websocket: WebSocket):
    logger.info("🌍 WS Origin: %s", websocket.headers.get("origin"))
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
        logger.exception("🔥 Frontend WS error")
        manager.disconnect(websocket)

# -------------------------------------------------
# Startup
# -------------------------------------------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(stats_listener_loop())
