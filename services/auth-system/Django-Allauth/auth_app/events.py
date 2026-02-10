# auth_app/events.py

from django.utils import timezone
from auth_app.rabbitmq_publisher import rabbit_publisher
import threading, uuid, hashlib, json

# --- Events Names ---
AUTH_USER_CREATED = "auth.user.created"
AUTH_EMAIL_VERIFICATION_SENT = "auth.email.verification.sent"
AUTH_EMAIL_VERIFIED = "auth.email.verified"

AUTH_LOGIN_SUCCESS = "auth.login.success"
AUTH_LOGIN_FAILED = "auth.login.failed"
AUTH_LOGOUT = "auth.logout"

AUTH_PASSWORD_RESET_REQUEST = "auth.password.reset.request"
AUTH_PASSWORD_RESET_COMPLETED = "auth.password.reset.completed"

AUTH_PROFILE_REFRESH = "auth.refresh.success"
AUTH_SESSION_SNAPSHOT = "auth.session.snapshot"


# --- Deduplication & Correlation ---
_last_payload_hashes = {}          # keyed by user_id + event_name
_lock = threading.Lock()
_user_correlation_ids = {}         # keep stable correlation per user

def _hash_payload(payload: dict) -> str:
    """Generate a deterministic hash of the payload to prevent duplicates."""
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.md5(payload_str.encode("utf-8")).hexdigest()

def emit(event_name: str, payload: dict):
    """Publish an event to RabbitMQ with deduplication and correlation tracking."""
    user_id = payload.get("user_id")
    if not user_id:
        print(f"[EVENT ERROR] Missing user_id in payload for {event_name}")
        return False

    user_key = f"{user_id}_{event_name}"

    with _lock:
        payload_hash = _hash_payload(payload)
        # Skip publishing if payload hasn't changed
        if _last_payload_hashes.get(user_key) == payload_hash:
            return False
        _last_payload_hashes[user_key] = payload_hash

        # Ensures a stable correlation ID per user + event
        correlation_id = _user_correlation_ids.get(user_key)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
            _user_correlation_ids[user_key] = correlation_id

    payload["correlation_id"] = correlation_id

    enriched_payload = {
        "event": event_name,
        "timestamp": timezone.now().isoformat(),
        **payload,
    }

    try:
        rabbit_publisher.publish(enriched_payload)
        return True
    except Exception as e:
        print(f"[EVENT ERROR] Failed to publish event '{event_name}': {e}")
        return False

def emit_login_success(user_id: int, session_token: str, profile: dict, jwt: dict = None):
    """Emit login success event."""
    payload = {
        "user_id": user_id,
        "session_token": session_token,
        "profile": profile,
        "jwt": jwt or {"access": None, "refresh": None},
    }
    return emit(AUTH_LOGIN_SUCCESS, payload)

def emit_logout(user_id: int):
    """Emit logout event."""
    payload = {
        "user_id": user_id,
        "profile": None,
        "session_token": None,
        "jwt": None,
    }
    return emit(AUTH_LOGOUT, payload)

def emit_profile_refresh(user_id: int, session_token: str, profile: dict, jwt: dict = None):
    """
    Emit a profile refresh event to update frontend state without hitting auth backend.
    Deduplication ensures multiple WS connections or page reloads don't spam RabbitMQ.
    """
    payload = {
        "user_id": user_id,
        "session_token": session_token,
        "profile": profile,
        "jwt": jwt or {"access": None, "refresh": None},
    }
    return emit(AUTH_PROFILE_REFRESH, payload)


def emit_session_snapshot(
    *,
    user_id: int,
    session_id: str,
    profile: dict,
    jwt: dict,
    expires_at: str,
    state: str = "active",  # active | logged_out | expired
):
    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "profile": profile,
        "jwt": jwt or {"access": None, "refresh": None},
        "expires_at": expires_at,
        "state": state,
    }
    return emit(AUTH_SESSION_SNAPSHOT, payload)

