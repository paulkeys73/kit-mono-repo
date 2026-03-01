#E:\WebSocket-Server\ws_handler.py



import logging
from session_store import SESSION_STORE
from starlette.websockets import WebSocketState
logger = logging.getLogger("websocket-saver")


async def on_connect(manager, ws, payload, db_ws_client):
    session_id = payload.get("session_id")
    user_id = payload.get("user_id")
    email = payload.get("email")

    if not session_id:
        return None

    # ❗ register FIRST
    current_ws = manager.active_connections.get(session_id)
    if current_ws is not ws:
        await manager.connect(ws, session_id)

    # Socket may already be replaced
    if ws.client_state != WebSocketState.CONNECTED:
        return None

    session = SESSION_STORE.get(session_id)

    if not session and user_id:
        sessions = SESSION_STORE.get_user_sessions(user_id)
        if sessions:
            session = sessions[-1]

    if not session and db_ws_client:
        try:
            db_res = await db_ws_client.get_user(
                "default",
                session_id=session_id,
                email=email
            )
            if db_res and db_res.get("found"):
                user = db_res["user"]
                session = {
                    "user_id": user["id"],
                    "session_id": session_id,
                    "profile": user,
                    "state": "active",
                }
                SESSION_STORE.upsert(session)
        except Exception:
            logger.exception("DB WS restore failed")

    if session:
        profile = session.get("profile") or session.get("user") or {}
        resolved_user_id = session.get("user_id") or profile.get("id")

        ok = await manager.safe_send(ws, {
            "event": "auth.user.profile",
            "user_id": resolved_user_id,
            "session_id": session_id,
            "profile": profile,
        })
        if ok and resolved_user_id:
            manager.attach_user(session_id, resolved_user_id)
        return resolved_user_id

    # ✅ Only send anonymous if socket is still alive
    await manager.safe_send(ws, {"event": "auth.anonymous"})
    return None
