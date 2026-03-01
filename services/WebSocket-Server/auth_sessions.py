# E:\WebSocket-Server\auth_sessions.py
from session_store import SESSION_STORE
from profile import send_profile_to_ws
import logging

logger = logging.getLogger("websocket-saver")

async def handle_auth_session_get(ws, payload):
    """
    Handles 'auth.session.get'.
    Fallback when replay fails.
    """
    session_id = payload.get("session_id")
    user_id = payload.get("user_id")
    session = None

    if session_id:
        session = SESSION_STORE.get(session_id)

    if not session and user_id:
        sessions = SESSION_STORE.get_user_sessions(user_id)
        if sessions:
            session = sessions[-1]

    if not session:
        await ws.send_json({"event": "auth.anonymous"})
        logger.info("📦 auth.anonymous sent | session_id=%s", session_id)
        return False

    user_data = session.get("user", {})

    # Send sessions events
    await ws.send_json({
        "event": "auth.user.session",
        "data": { "session_id": session_id, "user_id": session.get("user_id"), **user_data },
        "meta": { "replayed": True, "source": "session_store" }
    })

    # Trigger profile from canonical store
    await send_profile_to_ws(session_id, session.get("user_id"))

    logger.debug(
        "📦 auth.user.session + profile triggered | session_id=%s | user_id=%s",
        session_id,
        session.get("user_id"),
    )
    return True

async def replay_auth_session(ws, session_id: str) -> bool:
    """
    Replays latest session + profile for a session_id.
    """
    session = SESSION_STORE.get(session_id)
    if not session or not session.get("user"):
        return False

    user_data = session["user"]

    # Send session event
    await ws.send_json({
        "event": "auth.user.session",
        "data": { "session_id": session_id, "user_id": session.get("user_id"), **user_data },
        "meta": { "replayed": True, "source": "session_store" }
    })

    # Trigger profile from canonical store
    await send_profile_to_ws(session_id, session.get("user_id"))

    logger.debug(
        "🔁 session + profile replayed | session_id=%s | user_id=%s",
        session_id,
        user_data.get("id"),
    )
    return True
