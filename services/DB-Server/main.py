# db server main.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy import text, create_engine
from functools import lru_cache
import json
import logging
import uvicorn
import base64
import zlib
import pickle
from datetime import datetime
from decimal import Decimal

from donationData import router as donation_router
from core.env_db import (
    build_admin_db_url,
    build_app_db_url,
    get_db_settings,
)

# =====================================================
# LOGGING
# =======================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("db-server")

# =======================================================
# FASTAPI APP
# =======================================================

app = FastAPI(title="DB Server", version="2.2.0")
app.include_router(donation_router)

# =======================================================
# DATABASE ENGINES (LAZY + CACHED)
# =======================================================

@lru_cache
def get_admin_engine():
    return create_engine(
        build_admin_db_url(),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )


@lru_cache
def get_app_engine():
    return create_engine(
        build_app_db_url(),
        pool_pre_ping=True,
    )

# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
def startup():
    cfg = get_db_settings()

    logger.info(
        "📡 DB resolved → %s:%s/%s (env=%s)",
        cfg["DB_HOST"],
        cfg["DB_PORT"],
        cfg["DB_NAME"],
        cfg["DB_ENV"],
    )

    try:
        with get_admin_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("🗄️ DB connection verified")
    except Exception as e:
        logger.warning("⚠️ DB not ready at startup: %s", e)
        logger.warning("⚠️ Service will continue and retry on demand")

# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():
    return {"status": "ok", "service": "db-server"}

# =========================================================
# 🔐 DJANGO SESSION DECODER
# =========================================================

def decode_django_session(session_data: str) -> dict:
    try:
        data = session_data.split(":", 1)[0]

        compressed = data.startswith(".")
        if compressed:
            data = data[1:]

        if len(data) % 4:
            data += "=" * (4 - len(data) % 4)

        raw = base64.urlsafe_b64decode(data)

        if compressed:
            raw = zlib.decompress(raw)

        try:
            decoded = json.loads(raw.decode("utf-8"))
            logger.info("✅ Django session decoded (JSON)")
            return decoded
        except Exception:
            decoded = pickle.loads(raw)
            logger.info("✅ Django session decoded (pickle)")
            return decoded

    except Exception:
        logger.exception("❌ Failed to decode django_session")
        return {}

# =========================================================
# 🧼 SERIALIZATION HELPERS
# =========================================================

def json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def sanitize_user(row: dict) -> dict:
    blacklist = {"password"}
    return {k: json_safe(v) for k, v in row.items() if k not in blacklist}

# =========================================================
# 🔌 WEBSOCKET API
# =========================================================

@app.websocket("/ws")
async def db_ws(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 DB WS connected")

    try:
        while True:
            payload_text = await websocket.receive_text()
            logger.info("📨 Payload received: %s", payload_text)

            payload = json.loads(payload_text)
            event = payload.get("event")
            request_id = payload.get("request_id")

            response = {
                "event": "db.error",
                "request_id": request_id,
                "message": "Unhandled event",
            }

            # -----------------------------
            # USER LOOKUP
            # -----------------------------
            if event == "db.user.get":
                session_id = payload.get("session_id")
                user_id_hint = payload.get("user_id")

                logger.info(
                    "🔎 Lookup | session_id=%s | user_id_hint=%s",
                    session_id,
                    user_id_hint,
                )

                user = None
                resolved_user_id = None
                resolved_via = None

                with get_app_engine().connect() as conn:
                    if user_id_hint:
                        resolved_user_id = int(user_id_hint)
                        resolved_via = "payload"

                    if session_id:
                        session_row = conn.execute(
                            text(
                                "SELECT session_data "
                                "FROM django_session "
                                "WHERE session_key = :sid"
                            ),
                            {"sid": session_id},
                        ).first()

                        if session_row:
                            session_dict = decode_django_session(
                                session_row.session_data
                            )
                            session_uid = session_dict.get("_auth_user_id")
                            if session_uid and not resolved_user_id:
                                resolved_user_id = int(session_uid)
                                resolved_via = "session"

                if resolved_user_id:
                    with get_app_engine().connect() as conn:
                        user_row = conn.execute(
                            text(
                                "SELECT * "
                                "FROM auth_app_customuser "
                                "WHERE id = :uid"
                            ),
                            {"uid": resolved_user_id},
                        ).mappings().first()

                        if user_row:
                            user = sanitize_user(dict(user_row))
                            logger.info(
                                "✅ User loaded | id=%s | via=%s",
                                user.get("id"),
                                resolved_via,
                            )
                        else:
                            logger.warning("❌ User not found")

                response = {
                    "event": "db.user.result",
                    "request_id": request_id,
                    "found": bool(user),
                    "resolved_via": resolved_via,
                    "user": user,
                    "session_id": session_id,
                }

            # -----------------------------
            # DONATION LOOKUP
            # -----------------------------
            elif event == "db.donations.get":
                user_id = payload.get("user_id")
                logger.info("🔎 Donation lookup requested for user_id=%s", user_id)

                if not user_id:
                    response = {
                        "event": "db.donations.result",
                        "request_id": request_id,
                        "status": "error",
                        "message": "user_id required",
                    }
                else:
                    with get_app_engine().connect() as conn:
                        rows = conn.execute(
                            text(
                                """
                                SELECT *
                                FROM donations
                                WHERE user_id = :uid
                                ORDER BY created_at DESC
                                """
                            ),
                            {"uid": int(user_id)},
                        ).mappings().all()

                    donations = [json_safe(dict(r)) for r in rows]

                    response = {
                        "event": "db.donations.result",
                        "request_id": request_id,
                        "status": "ok",
                        "user_id": user_id,
                        "donations": donations,
                    }

            # -----------------------------
            # HEALTH CHECK
            # -----------------------------
            elif event == "db.health":
                response = {
                    "event": "db.health",
                    "request_id": request_id,
                    "status": "ok",
                }

            # -----------------------------
            # SEND RESPONSE
            # -----------------------------
            logger.info("📤 Sending response: %s", response)
            await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info("🔌 DB WS disconnected")
    except Exception:
        logger.exception("⚠️ DB WS fatal error")
        await websocket.close()

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8011,
        reload=False,
    )
