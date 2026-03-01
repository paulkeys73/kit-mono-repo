# E:\WebSocket-Server\user_session_store.py

import json
from pathlib import Path
from threading import Lock
from typing import Callable, List

STORE_FILE = Path("user_session_store.json")
STORE_FILE.touch(exist_ok=True)  # create if not exists

_lock = Lock()

# Listener's for broadcasting updates
_listeners: List[Callable[[dict], None]] = []

def add_update_listener(callback: Callable[[dict], None]):
    """Register a callback to be called whenever store updates."""
    _listeners.append(callback)

def _notify_listeners(user_data: dict):
    for callback in _listeners:
        try:
            callback(user_data)
        except Exception as e:
            print(f"⚠️ Listener failed: {e}")

def load_store() -> dict:
    """Load the full user session store."""
    with _lock:
        try:
            with STORE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}
        return data

def save_store(data: dict):
    """Overwrite the full store."""
    with _lock:
        with STORE_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def update_user_session(user_data: dict):
    """Update or add a user session in the store and notify listeners."""
    user_id = user_data.get("user_id") or user_data.get("profile", {}).get("id")
    if not user_id:
        raise ValueError("user_data must contain 'user_id' or profile.id")

    store = load_store()
    store[str(user_id)] = user_data
    save_store(store)

    # Notify listeners for broadcasting
    _notify_listeners(user_data)

    return store[str(user_id)]

def get_user_session(user_id: int) -> dict | None:
    store = load_store()
    return store.get(str(user_id))


def remove_user_session(user_id: int) -> bool:
    store = load_store()
    key = str(user_id)
    if key not in store:
        return False
    del store[key]
    save_store(store)
    return True


def remove_by_session_id(session_id: str) -> list[int]:
    store = load_store()
    removed_user_ids: list[int] = []
    keep_store: dict = {}

    for key, value in store.items():
        current_session_id = value.get("session_id")
        if current_session_id == session_id:
            try:
                removed_user_ids.append(int(key))
            except ValueError:
                pass
            continue
        keep_store[key] = value

    if len(keep_store) != len(store):
        save_store(keep_store)

    return removed_user_ids



def get_full_profile(user_id: int) -> dict:
    """
    Return the full profile fields for a user from the session store.
    """
    store = load_store()
    session = store.get(str(user_id))
    if not session:
        return {}

    profile_fields = [
        "id", "username", "full_name", "first_name", "last_name", "email",
        "phone", "bio", "location", "country", "address", "state", "city",
        "postal_code", "profile_image", "avatar",
        "facebook_url", "x_url", "linkedin_url", "instagram_url",
        "is_staff", "is_superuser"
    ]

    data = {}
    for k in profile_fields:
        if k in session:
            data[k] = session[k]
        elif "user" in session and k in session["user"]:
            data[k] = session["user"][k]
    return data

