import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import websockets
from fastapi import Cookie, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketState

from auth_sessions import handle_auth_session_get, replay_auth_session
from connection_manager import manager
from db_ws_client import DbWsClient
from rabbit_consumer import start_rabbitmq_consumer, start_support_rabbitmq_consumer
from user_session_store import add_update_listener
from ws_handler import on_connect

# ---------------- Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("websocket-saver")
logger.setLevel(getattr(logging, os.getenv("WS_LOG_LEVEL", "WARNING").upper(), logging.WARNING))
logging.getLogger("profile-ws").setLevel(logging.WARNING)
logging.getLogger("ws-manager").setLevel(logging.WARNING)
logging.getLogger("rabbit-consumer").setLevel(logging.INFO)
logging.getLogger("websockets.server").setLevel(logging.WARNING)
logging.getLogger("uvicorn.protocols.websockets.websockets_impl").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

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

HEALTH_WS_INTERVAL_SECONDS = float(os.getenv("HEALTH_WS_INTERVAL_SECONDS", "10"))
HEALTH_UPSTREAM_RECONNECT_SECONDS = float(os.getenv("HEALTH_UPSTREAM_RECONNECT_SECONDS", "5"))
SERVICE_HEALTH_WS_URLS = {
    "db_server": os.getenv("DB_SERVER_HEALTH_WS_URL", "ws://127.0.0.1:8011/ws/health"),
    "db_stats": os.getenv("DB_STATS_HEALTH_WS_URL", "ws://127.0.0.1:8012/ws/health"),
    "paypal_payments": os.getenv("PAYPAL_HEALTH_WS_URL", "ws://127.0.0.1:8800/ws/health"),
    "support": os.getenv("SUPPORT_HEALTH_WS_URL", "ws://127.0.0.1:8099/ws/health"),
    "ws_stats": os.getenv("WS_STATS_HEALTH_WS_URL", "ws://127.0.0.1:8008/ws/health"),
}

health_stream_subscribers: set[WebSocket] = set()
service_health_state: dict[str, Any] = {}

SUPPORT_WS_REPLAY_LIMIT = max(1, int(os.getenv("SUPPORT_WS_REPLAY_LIMIT", "50")))
support_stream_subscribers: set[WebSocket] = set()
support_stream_filters: dict[int, dict[str, str]] = {}
support_event_buffer: list[dict[str, Any]] = []

# ---------------- Event Routing ----------------
EVENT_HANDLERS = {
    "auth.session.get": handle_auth_session_get,
}


def _is_payload_ok(payload: dict[str, Any]) -> bool:
    status_value = str(payload.get("status", "")).lower()
    database_value = str(payload.get("database", "")).lower()

    if status_value in {"ok", "healthy"}:
        return True
    if status_value == "degraded" and database_value in {"connected", "ok"}:
        return True
    return False


def _aggregated_health_snapshot() -> dict[str, Any]:
    services: dict[str, Any] = {}
    for name, url in SERVICE_HEALTH_WS_URLS.items():
        entry = service_health_state.get(name)
        if entry:
            services[name] = entry
        else:
            services[name] = {
                "service": name,
                "url": url,
                "ok": False,
                "status": "unknown",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    all_ok = all(item.get("ok", False) for item in services.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }


async def _broadcast_health_snapshot() -> None:
    if not health_stream_subscribers:
        return

    payload = _aggregated_health_snapshot()
    dead: list[WebSocket] = []

    for ws in health_stream_subscribers:
        try:
            await ws.send_json({"event": "services.health", "payload": payload})
        except Exception:
            dead.append(ws)

    for ws in dead:
        health_stream_subscribers.discard(ws)


async def consume_service_health_stream(name: str, ws_url: str) -> None:
    while True:
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
            ) as upstream:
                logger.info("HEALTH_UPSTREAM_CONNECTED | service=%s | url=%s", name, ws_url)

                service_health_state[name] = {
                    "service": name,
                    "url": ws_url,
                    "ok": True,
                    "status": "connected",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                await _broadcast_health_snapshot()

                async for raw in upstream:
                    try:
                        message = json.loads(raw)
                    except json.JSONDecodeError:
                        message = {"payload": {"raw": raw[:512], "status": "unknown"}}

                    payload = message.get("payload") or message
                    payload = payload if isinstance(payload, dict) else {"raw": str(payload)}

                    service_health_state[name] = {
                        "service": name,
                        "url": ws_url,
                        "ok": _is_payload_ok(payload),
                        "status": str(payload.get("status", "unknown")).lower(),
                        "payload": payload,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await _broadcast_health_snapshot()

        except Exception as exc:
            logger.warning("HEALTH_UPSTREAM_ERROR | service=%s | error=%s", name, exc)
            service_health_state[name] = {
                "service": name,
                "url": ws_url,
                "ok": False,
                "status": "error",
                "error": str(exc),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await _broadcast_health_snapshot()
            await asyncio.sleep(HEALTH_UPSTREAM_RECONNECT_SECONDS)


# ---------------- Support WS ----------------
def _normalize_filter_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("ticket")
    return nested if isinstance(nested, dict) else {}


def _support_lookup_values(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    ticket = _extract_ticket(payload)

    return {
        "project_id": _normalize_filter_value(payload.get("project_id") or ticket.get("project_id")),
        "user_id": _normalize_filter_value(payload.get("user_id") or ticket.get("user_id")),
        "ticket_id": _normalize_filter_value(payload.get("ticket_id") or ticket.get("id") or payload.get("ticket_id")),
    }


def _support_event_matches_filters(message: dict[str, Any], filters: dict[str, str]) -> bool:
    if not filters:
        return True

    lookup = _support_lookup_values(message)
    for key in ("project_id", "user_id", "ticket_id"):
        expected = _normalize_filter_value(filters.get(key))
        if expected and lookup.get(key) != expected:
            return False
    return True


def _store_support_event(message: dict[str, Any]) -> None:
    support_event_buffer.append(message)
    overflow = len(support_event_buffer) - SUPPORT_WS_REPLAY_LIMIT
    if overflow > 0:
        del support_event_buffer[:overflow]


async def _send_support_snapshot(ws: WebSocket, filters: dict[str, str]) -> None:
    events = [event for event in support_event_buffer if _support_event_matches_filters(event, filters)]
    await ws.send_json(
        {
            "event": "support.snapshot",
            "namespace": "support",
            "payload": {
                "events": events,
                "count": len(events),
                "filters": filters,
            },
            "meta": {"replayed": True, "ts": datetime.now(timezone.utc).isoformat()},
        }
    )


async def _broadcast_support_event(message: dict[str, Any]) -> None:
    if not support_stream_subscribers:
        return

    dead: list[WebSocket] = []
    for ws in list(support_stream_subscribers):
        ws_filters = support_stream_filters.get(id(ws), {})
        if not _support_event_matches_filters(message, ws_filters):
            continue

        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        support_stream_subscribers.discard(ws)
        support_stream_filters.pop(id(ws), None)


async def handle_support_rabbit_event(event_name: str, data: dict, envelope: dict) -> None:
    payload = data if isinstance(data, dict) else {"value": data}

    message = {
        "event": event_name,
        "namespace": "support",
        "payload": payload,
        "meta": {
            "source": "rabbitmq",
            "timestamp": envelope.get("timestamp"),
            "received_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    _store_support_event(message)
    await _broadcast_support_event(message)


# ---------------- Broadcast ----------------
async def broadcast_user_update(session_id: str, payload: dict):
    conn = manager.active_connections.get(session_id)
    if not conn:
        return

    ws = conn.get("ws") if isinstance(conn, dict) else conn

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

        # profile event
        profile_data = user_data.get("profile", {})
        if profile_data:
            profile_payload = {
                "event": "auth.user.profile",
                "data": profile_data,
                "meta": {"replayed": user_data.get("_replayed", False), "source": "user_session_store"},
            }
            asyncio.create_task(broadcast_user_update(session_id, profile_payload))

    add_update_listener(listener)


# ---------------- Aggregated Health WebSocket ----------------
@app.get("/ws/health")
def ws_health_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/health",
        },
        headers={"Upgrade": "websocket"},
    )


@app.websocket("/ws/health")
async def ws_health_stream(ws: WebSocket):
    await ws.accept()
    health_stream_subscribers.add(ws)
    logger.info("HEALTH_WS_CONNECTED")

    await ws.send_json({"event": "services.health", "payload": _aggregated_health_snapshot()})

    try:
        while True:
            message = await ws.receive_text()
            if message.strip().lower() in {"refresh", "health.get"}:
                await ws.send_json(
                    {
                        "event": "services.health",
                        "payload": _aggregated_health_snapshot(),
                    }
                )
    except WebSocketDisconnect:
        logger.info("HEALTH_WS_DISCONNECTED")
    except Exception as exc:
        logger.exception("HEALTH_WS_ERROR | %s", exc)
    finally:
        health_stream_subscribers.discard(ws)


@app.get("/ws/support")
def ws_support_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/support",
        },
        headers={"Upgrade": "websocket"},
    )


@app.websocket("/ws/support")
async def ws_support_stream(ws: WebSocket):
    await ws.accept()

    filters = {
        "project_id": _normalize_filter_value(ws.query_params.get("project_id")),
        "user_id": _normalize_filter_value(ws.query_params.get("user_id")),
        "ticket_id": _normalize_filter_value(ws.query_params.get("ticket_id")),
    }

    support_stream_subscribers.add(ws)
    support_stream_filters[id(ws)] = filters

    await _send_support_snapshot(ws, filters)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"event": raw.strip().lower()}

            event = str(data.get("event", "")).strip().lower()

            if event in {"support.get", "support.refresh", "refresh"}:
                await _send_support_snapshot(ws, support_stream_filters.get(id(ws), {}))
                continue

            if event == "support.subscribe":
                incoming = data.get("filters")
                if isinstance(incoming, dict):
                    updated = {
                        "project_id": _normalize_filter_value(incoming.get("project_id")),
                        "user_id": _normalize_filter_value(incoming.get("user_id")),
                        "ticket_id": _normalize_filter_value(incoming.get("ticket_id")),
                    }
                    support_stream_filters[id(ws)] = updated
                    await ws.send_json(
                        {
                            "event": "support.subscribed",
                            "namespace": "support",
                            "payload": {"filters": updated},
                        }
                    )
                    await _send_support_snapshot(ws, updated)
                continue

            if event in {"ping", "support.ping"}:
                await ws.send_json(
                    {
                        "event": "support.pong",
                        "namespace": "support",
                        "meta": {"ts": datetime.now(timezone.utc).isoformat()},
                    }
                )

    except WebSocketDisconnect:
        pass
    except RuntimeError as exc:
        if "WebSocket is not connected" not in str(exc):
            logger.exception("WS_SUPPORT_RUNTIME_ERROR | %s", exc)
    except Exception as exc:
        logger.exception("WS_SUPPORT_ERROR | %s", exc)
    finally:
        support_stream_subscribers.discard(ws)
        support_stream_filters.pop(id(ws), None)


# ---------------- WebSocket Endpoint ----------------
@app.websocket("/ws/status")
@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    sessionid: Optional[str] = Cookie(None),
):
    session_id = sessionid or f"anon_{id(ws)}"
    await ws.accept()

    logger.info("WS_CONNECTED | session_id=%s", session_id)

    try:
        await manager.connect(ws, session_id)

        replayed = await replay_auth_session(ws, session_id)
        if not replayed:
            await handle_auth_session_get(ws, {"session_id": session_id})

        while True:
            if ws.client_state != WebSocketState.CONNECTED:
                logger.info("WS_RECEIVE_STOP | session_id=%s | state=%s", session_id, ws.client_state)
                break

            try:
                msg = await ws.receive_text()
            except RuntimeError as exc:
                if "WebSocket is not connected" in str(exc):
                    logger.info("WS_RECEIVE_CLOSED | session_id=%s", session_id)
                    break
                raise

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
        logger.info("WS_DISCONNECTED | session_id=%s", session_id)

    except Exception as e:
        logger.exception("WS_ERROR | %s", e)

    finally:
        await manager.disconnect(session_id)


# ---------------- Startup / Shutdown ----------------
@app.on_event("startup")
async def startup():
    global db_ws_client
    logger.info("WS Saver starting")

    db_ws_url = os.getenv("DB_WS_URL", "ws://127.0.0.1:8011/ws")
    db_ws_client = DbWsClient(db_ws_url)
    asyncio.create_task(db_ws_client.connect())

    asyncio.create_task(start_rabbitmq_consumer(manager, db_ws_client))
    asyncio.create_task(start_support_rabbitmq_consumer(handle_support_rabbit_event))

    for service_name, ws_url in SERVICE_HEALTH_WS_URLS.items():
        asyncio.create_task(consume_service_health_stream(service_name, ws_url))

    register_store_listener()


@app.on_event("shutdown")
async def shutdown():
    logger.info("WS Saver shutting down")
    await manager.close_all()


@app.get("/ws/status")
def ws_status_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/status",
        },
        headers={"Upgrade": "websocket"},
    )


# ---------------- Health ----------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "connections": len(manager.active_connections),
        "health_ws": "/ws/health",
        "support_ws": "/ws/support",
    }
