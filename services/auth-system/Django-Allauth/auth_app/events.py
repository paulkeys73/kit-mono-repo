# auth_app/events.py

from django.utils import timezone
import threading
import uuid
import hashlib
import json

# IMPORTANT:
# Do NOT import rabbit_publisher at module level.
# Lazy import inside emit() prevents circular import issues
# and prevents startup race conditions.


# ============================================================
# EVENT NAMES
# ============================================================

# User lifecycle
AUTH_USER_CREATED = "auth.user.created"

# Email verification
AUTH_EMAIL_VERIFICATION_SENT = "auth.email.verification.sent"
AUTH_EMAIL_VERIFIED = "auth.email.verified"

# Passwordless flow
AUTH_PASSWORDLESS_CODE_SENT = "auth.passwordless.code.sent"
AUTH_PASSWORDLESS_VERIFIED = "auth.passwordless.verified"
AUTH_PASSWORDLESS_FAILED = "auth.passwordless.failed"
AUTH_PASSWORDLESS_EXPIRED = "auth.passwordless.expired"

# Password login flow
AUTH_PASSWORD_LOGIN_SUCCESS = "auth.password.login.success"
AUTH_PASSWORD_LOGIN_FAILED = "auth.password.login.failed"

# Unified session events
AUTH_SESSION_CREATED = "auth.session.created"
AUTH_SESSION_SNAPSHOT = "auth.session.snapshot"
AUTH_LOGOUT = "auth.logout"

# Password reset
AUTH_PASSWORD_RESET_REQUEST = "auth.password.reset.request"
AUTH_PASSWORD_RESET_COMPLETED = "auth.password.reset.completed"

# Profile refresh
AUTH_PROFILE_REFRESH = "auth.refresh.success"


# ============================================================
# DEDUP + CORRELATION SYSTEM
# ============================================================

_last_payload_hashes = {}
_lock = threading.Lock()
_user_correlation_ids = {}


def _hash_payload(payload: dict) -> str:
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.md5(payload_str.encode("utf-8")).hexdigest()


def emit(event_name: str, payload: dict):
    """
    Core emitter.

    Handles:
    - deduplication
    - correlation id
    - enrichment
    - SAFE publishing (never crashes auth)
    """

    user_id = payload.get("user_id")
    if not user_id:
        print(f"[EVENT ERROR] Missing user_id in payload for {event_name}")
        return False

    user_key = f"{user_id}_{event_name}"

    with _lock:
        payload_hash = _hash_payload(payload)

        # Skip duplicate events
        if _last_payload_hashes.get(user_key) == payload_hash:
            return False

        _last_payload_hashes[user_key] = payload_hash

        # Maintain correlation ID per user+event
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

    # --------------------------------------------------------
    # SAFE LAZY PUBLISH (NO MORE NoneType.publish ERRORS)
    # --------------------------------------------------------

    try:
        from auth_app.rabbitmq_publisher import rabbit_publisher

        if rabbit_publisher is None:
            print(f"[EVENT WARNING] Rabbit publisher not ready. Skipping {event_name}")
            return False

        if not hasattr(rabbit_publisher, "publish"):
            print(f"[EVENT WARNING] Publisher not initialized properly. Skipping {event_name}")
            return False

        rabbit_publisher.publish(enriched_payload)
        return True

    except Exception as e:
        print(f"[EVENT ERROR] Failed to publish '{event_name}': {e}")
        return False


# ============================================================
# USER LIFECYCLE
# ============================================================

def emit_user_created(
    *,
    user_id: int,
    username: str,
    email: str,
    full_name: str,
    method: str,
):
    return emit(AUTH_USER_CREATED, {
        "user_id": user_id,
        "username": username,
        "email": email,
        "full_name": full_name,
        "method": method,
    })


# ============================================================
# EMAIL VERIFICATION FLOW
# ============================================================

def emit_email_verification_sent(user_id: int, email: str):
    return emit(AUTH_EMAIL_VERIFICATION_SENT, {
        "user_id": user_id,
        "email": email,
    })


def emit_email_verified(user_id: int, session_id: str | None = None):
    return emit(AUTH_EMAIL_VERIFIED, {
        "user_id": user_id,
        "session_id": session_id,
    })


# ============================================================
# PASSWORDLESS FLOW
# ============================================================

# PASSWORDLESS FLOW
def emit_passwordless_code_sent(user_id, email, expires_at, code=None):
    try:
        from auth_app.rabbitmq_publisher import rabbit_publisher

        if rabbit_publisher is None:
            print(f"[EVENT WARNING] Rabbit publisher not ready. Skipping auth.passwordless.code.sent")
            return False

        payload = {
            "event": "auth.passwordless.code.sent",
            "user_id": user_id,
            "email": email,
            "expires_at": expires_at,
            "code": code,  # optional, only for dev/testing
        }

        rabbit_publisher.publish(payload)
        return True

    except Exception as e:
        print(f"[EVENT ERROR] Failed to emit passwordless code: {e}")
        return False


def emit_passwordless_verified(
    user_id: int,
    session_id: str,
    profile: dict | None = None,
    jwt: dict | None = None,
):
    return emit(AUTH_PASSWORDLESS_VERIFIED, {
        "user_id": user_id,
        "session_id": session_id,
        "profile": profile or {},
        "jwt": jwt or {"access": None, "refresh": None},
        "method": "passwordless",
    })


def emit_passwordless_failed(user_id: int, reason: str):
    return emit(AUTH_PASSWORDLESS_FAILED, {
        "user_id": user_id,
        "reason": reason,
        "method": "passwordless",
    })


def emit_passwordless_expired(user_id: int):
    return emit(AUTH_PASSWORDLESS_EXPIRED, {
        "user_id": user_id,
        "method": "passwordless",
    })


# ============================================================
# PASSWORD LOGIN FLOW
# ============================================================

def emit_password_login_success(user_id: int, session_id: str):
    return emit(AUTH_PASSWORD_LOGIN_SUCCESS, {
        "user_id": user_id,
        "session_id": session_id,
        "method": "password",
    })


def emit_password_login_failed(user_id: int, reason: str):
    return emit(AUTH_PASSWORD_LOGIN_FAILED, {
        "user_id": user_id,
        "reason": reason,
        "method": "password",
    })


# ============================================================
# SESSION LAYER (UNIFIED)
# ============================================================

def emit_session_created(
    *,
    user_id: int,
    session_id: str,
    profile: dict,
    jwt: dict,
    expires_at: str,
    method: str,
):
    return emit(AUTH_SESSION_CREATED, {
        "user_id": user_id,
        "session_id": session_id,
        "profile": profile,
        "jwt": jwt or {"access": None, "refresh": None},
        "expires_at": expires_at,
        "method": method,
        "state": "active",
    })


def emit_session_snapshot(
    *,
    user_id: int,
    session_id: str,
    profile: dict,
    jwt: dict,
    expires_at: str,
    state: str = "active",
):
    return emit(AUTH_SESSION_SNAPSHOT, {
        "user_id": user_id,
        "session_id": session_id,
        "profile": profile,
        "jwt": jwt or {"access": None, "refresh": None},
        "expires_at": expires_at,
        "state": state,
    })


def emit_logout(user_id: int, session_id: str):
    return emit(AUTH_LOGOUT, {
        "user_id": user_id,
        "session_id": session_id,
        "state": "logged_out",
    })


# ============================================================
# PROFILE REFRESH
# ============================================================

def emit_profile_refresh(
    user_id: int,
    session_id: str | None = None,
    profile: dict | None = None,
    jwt: dict | None = None,
    session_token: str | None = None,
):
    resolved_session_id = session_id or session_token
    return emit(AUTH_PROFILE_REFRESH, {
        "user_id": user_id,
        "session_id": resolved_session_id,
        "profile": profile or {},
        "jwt": jwt or {"access": None, "refresh": None},
    })


# ============================================================
# PASSWORD RESET
# ============================================================

def emit_password_reset_request(user_id: int, email: str):
    return emit(AUTH_PASSWORD_RESET_REQUEST, {
        "user_id": user_id,
        "email": email,
    })


def emit_password_reset_completed(user_id: int):
    return emit(AUTH_PASSWORD_RESET_COMPLETED, {
        "user_id": user_id,
    })


__all__ = [
    "emit_user_created",
    "emit_email_verification_sent",
    "emit_email_verified",
    "emit_passwordless_code_sent",
    "emit_passwordless_verified",
    "emit_passwordless_failed",
    "emit_passwordless_expired",
    "emit_password_login_success",
    "emit_password_login_failed",
    "emit_session_created",
    "emit_session_snapshot",
    "emit_logout",
    "emit_profile_refresh",
    "emit_password_reset_request",
    "emit_password_reset_completed",
]
