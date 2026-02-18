import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Cookie
from fastapi.middleware.cors import CORSMiddleware

from ws_handler import on_connect
from db_ws_client import DbWsClient
from rabbit_consumer import start_rabbitmq_consumer
from auth_sessions import handle_auth_session_get, replay_auth_session
from connection_manager import manager
from user_session_store import add_update_listener

# ---------------- Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("websocket-saver")

# ---------------- FastAPI App ----------------
app = FastAPI(title="Centralized WebSocket Saver")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4011",
        "http://127.0.0.1:4011",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_ws_client: Optional[DbWsClient] = None

# ---------------- Event Routing ----------------
EVENT_HANDLERS = {
    "auth.session.get": handle_auth_session_get,
}

# ---------------- Broadcast ----------------
async def broadcast_user_update(session_id: str, payload: dict):
    conn = manager.active_connections.get(session_id)
    if not conn:
        return

    ws = conn["ws"]

    try:
        await ws.send_json(payload)
    except Exception:
        await manager.disconnect(session_id)

# ---------------- Store Listener ----------------
def register_store_listener():
    def listener(user_data: dict):
        session_id = user_data.get("session_id")
        user_id = user_data.get("user_id") or user_data.get("profile", {}).get("id")
        if not session_id or not user_id:
            return

        # session event
        session_payload = {
            "event": "auth.user.session",
            "data": user_data,
            "meta": {"replayed": user_data.get("_replayed", False), "source": "session_store"},
        }
        asyncio.create_task(broadcast_user_update(session_id, session_payload))

        # profile event – now send the full nested profile
        profile_data = user_data.get("profile", {})
        if profile_data:
            profile_payload = {
                "event": "auth.user.profile",
                "data": profile_data,
                "meta": {"replayed": user_data.get("_replayed", False), "source": "user_session_store"},
            }
            asyncio.create_task(broadcast_user_update(session_id, profile_payload))

    add_update_listener(listener)




# ---------------- WebSocket Endpoint ----------------
@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    sessionid: Optional[str] = Cookie(None),
):
    session_id = sessionid or f"anon_{id(ws)}"
    await ws.accept()

    logger.info("🔌 WS_CONNECTED | session_id=%s", session_id)

    try:
        await manager.connect(ws, session_id)

        # Use the new session replay method
        replayed = await replay_auth_session(ws, session_id)
        if not replayed:
            await handle_auth_session_get(ws, {"session_id": session_id})

        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            event = data.get("event")

            handler = EVENT_HANDLERS.get(event)
            if handler:
                await handler(ws, data)
                continue

            if event == "on.connect":
                await on_connect(manager, ws, data, db_ws_client)
                continue

            await ws.send_json({"event": "unknown", "data": data})

    except WebSocketDisconnect:
        logger.info("🔌 WS_DISCONNECTED | session_id=%s", session_id)
        await manager.disconnect(session_id)

    except Exception as e:
        logger.exception("⚠️ WS_ERROR | %s", e)
        await manager.disconnect(session_id)

# ---------------- Startup / Shutdown ----------------
@app.on_event("startup")
async def startup():
    global db_ws_client
    logger.info("🚀 WS Saver starting")

    db_ws_client = DbWsClient("ws://localhost:8011/ws")
    asyncio.create_task(db_ws_client.connect())

    asyncio.create_task(start_rabbitmq_consumer(manager, db_ws_client))

    register_store_listener()

@app.on_event("shutdown")
async def shutdown():
    logger.info("🛑 WS Saver shutting down")
    await manager.close_all()

# ---------------- Health ----------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "connections": len(manager.active_connections),
    }
