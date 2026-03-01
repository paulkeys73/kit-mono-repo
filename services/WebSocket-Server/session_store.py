# auth/ws/session_store.py
import time
import json
import os
from threading import Lock
from typing import Dict, Optional, List

SESSION_FILE = "sessions.json"
EVENT_FILE = "session_events.json"  # optionals persistence for events

class SessionStore:
    """
    DEV MODE session store with event tracking.

    Stores:
    - session_id
    - user_id
    - user (minimal snapshot)
    - state
    - optional expiration
    - event log (from RabbitMQ)
    """

    def __init__(self):
        self._sessions: Dict[str, dict] = {}              # session_id -> session
        self._user_sessions: Dict[int, List[str]] = {}   # user_id -> [session_id]
        self._events: List[dict] = []                    # event log
        self._lock = Lock()
        self._load_from_file()

    # ------------------- Persistence -------------------

    def _load_from_file(self):
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._sessions = data.get("sessions", {})
                    self._user_sessions = {
                        int(k): v for k, v in data.get("user_sessions", {}).items()
                    }
            except Exception as e:
                print(f"[SessionStore] Failed to load sessions: {e}")

        if os.path.exists(EVENT_FILE):
            try:
                with open(EVENT_FILE, "r", encoding="utf-8") as f:
                    self._events = json.load(f)
            except Exception as e:
                print(f"[SessionStore] Failed to load events: {e}")

    def _save_to_file(self):
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"sessions": self._sessions, "user_sessions": self._user_sessions},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            print(f"[SessionStore] Failed to save sessions: {e}")

        try:
            with open(EVENT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._events, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SessionStore] Failed to save events: {e}")

    # ------------------- Session Management -------------------

    def upsert(self, snapshot: dict):
        sid = snapshot.get("session_id")
        user_id = snapshot.get("user_id")
        user = snapshot.get("user") or {}
        state = snapshot.get("state", "active")
        expires_at_iso = snapshot.get("expires_at")

        # ❌ Never store anonymous sessions
        if not sid or not user_id:
            return

        expires_ts = None
        if expires_at_iso:
            try:
                import datetime
                expires_ts = datetime.datetime.fromisoformat(expires_at_iso).timestamp()
            except Exception:
                pass

        session_data = {
            "session_id": sid,
            "user_id": user_id,
            "user": {
                "id": user_id,
                "email": user.get("email"),
                "username": user.get("username"),
                "is_staff": bool(user.get("is_staff", False)),
                "is_superuser": bool(user.get("is_superuser", False)),
            },
            "state": state,
            "_expires_ts": expires_ts,
        }

        with self._lock:
            # Invalidate session
            if state != "active":
                self._sessions.pop(sid, None)
                if user_id in self._user_sessions:
                    self._user_sessions[user_id] = [
                        s for s in self._user_sessions[user_id] if s != sid
                    ]
                self._save_to_file()
                return

            # Enforce single active session per user
            old_sids = self._user_sessions.get(user_id, [])
            for old_sid in old_sids:
                self._sessions.pop(old_sid, None)

            self._sessions[sid] = session_data
            self._user_sessions[user_id] = [sid]

            self._save_to_file()

    # ------------------- Event Tracking -------------------

    def store_event(self, event_name: str, payload: dict):
        """
        Store RabbitMQ events with timestamp.
        """
        with self._lock:
            self._events.append({
                "event": event_name,
                "payload": payload,
                "timestamp": time.time()
            })

            # Optional: cap the event log to prevent memory bloat
            if len(self._events) > 1000:
                self._events.pop(0)

            self._save_to_file()

    def get_events(self) -> List[dict]:
        with self._lock:
            return self._events.copy()

    # ------------------- Retrieval & Removal -------------------

    def get(self, session_id: str) -> Optional[dict]:
        with self._lock:
            data = self._sessions.get(session_id)
            if not data:
                return None

            expires_ts = data.get("_expires_ts")
            if expires_ts and expires_ts < time.time():
                self._sessions.pop(session_id, None)
                uid = data.get("user_id")
                if uid in self._user_sessions:
                    self._user_sessions[uid] = [
                        s for s in self._user_sessions[uid] if s != session_id
                    ]
                self._save_to_file()
                return None
            return data

    def get_user_sessions(self, user_id: int) -> List[dict]:
        with self._lock:
            sids = self._user_sessions.get(user_id, []).copy()
        return [self.get(sid) for sid in sids if self.get(sid)]

    def remove_session(self, session_id: str):
        with self._lock:
            sess = self._sessions.pop(session_id, None)
            if not sess:
                return

            uid = sess.get("user_id")
            if uid in self._user_sessions:
                self._user_sessions[uid] = [
                    s for s in self._user_sessions[uid] if s != session_id
                ]
            self._save_to_file()

    def remove_user_sessions(self, user_id: int):
        with self._lock:
            sids = self._user_sessions.pop(user_id, [])
            for sid in sids:
                self._sessions.pop(sid, None)
            self._save_to_file()



    # ------------------- Generic KV (Idempotency) -------------------

    def exists(self, key: str) -> bool:
        with self._lock:
            return any(
                e.get("event") == "__kv__"
                and e.get("payload", {}).get("key") == key
                for e in self._events
            )

    def set(self, key: str, value=True):
        with self._lock:
            self._events.append({
                "event": "__kv__",
                "payload": {
                    "key": key,
                    "value": value,
                },
                "timestamp": time.time(),
            })

            if len(self._events) > 1000:
                self._events.pop(0)

            self._save_to_file()




# ------------------- Singleton -------------------

SESSION_STORE = SessionStore()
