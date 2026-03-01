# E:\WebSocket-Server\profile.py
import json
from pathlib import Path
from typing import Optional
import logging
from connection_manager import manager  # active_connections manager

logger = logging.getLogger("profile-ws")

# Path to the users session store
STORE_FILE = Path("user_session_store.json")
STORE_FILE.touch(exist_ok=True)  # ensure the file exists


def load_user_sessions() -> dict:
    """Load all user sessions from the JSON store."""
    try:
        with STORE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def get_full_profile(user_id: int) -> Optional[dict]:
    """Fetch the full nested profile for a given user_id."""
    store = load_user_sessions()
    user_entry = store.get(str(user_id))
    if not user_entry:
        logger.warning("⚠️ No user entry found in store for user_id=%s", user_id)
        return None
    profile = user_entry.get("profile")
    if not profile:
        logger.warning("⚠️ No profile found for user_id=%s", user_id)
        return None
    return profile


async def send_profile_to_ws(session_id: str, user_id: int, _replayed: bool = True):
    """
    Sends the full profile to the frontend via WebSocket.

    Args:
        session_id: session_id to send the profile to
        user_id: ID of the user
        _replayed: flag indicating if this is a replayed profile
    """
    profile_data = get_full_profile(user_id)
    if not profile_data:
        logger.warning("⚠️ Cannot send profile: missing data for user_id=%s", user_id)
        return

    # Find active connection for session
    ws = manager.active_connections.get(session_id)
    if not ws:
        logger.warning("⚠️ No active WS connection for session_id=%s", session_id)
        return

    payload = {
        "event": "auth.user.profile",
        "data": profile_data,
        "meta": {"replayed": _replayed, "source": "profile"}  # updated source
    }

    try:
        await manager.safe_send(ws, payload)
        logger.info("📦 auth.user.profile sent | user_id=%s | session_id=%s", user_id, session_id)
    except Exception as e:
        logger.error(
            "❌ Failed to send profile WS | user_id=%s | session_id=%s | error=%s",
            user_id, session_id, e
        )
        await manager.disconnect(session_id)
