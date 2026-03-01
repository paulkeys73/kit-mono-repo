import json
import logging
import os
import uuid
import websockets

# -------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("db-ws-client")

# --------------------------------------------------
# Config
# --------------------------------------------------
DB_WS_URL = os.getenv("DB_WS_URL", "ws://127.0.0.1:8011/ws")

# -------------------------------------------------
# Fetch donation from DB via WS
# --------------------------------------------------
async def fetch_user_donations_from_db(user_id: int) -> list[dict]:
    request_id = str(uuid.uuid4())
    payload = {
        "event": "db.donations.get",
        "request_id": request_id,
        "user_id": user_id,
    }

    logger.info("➡️ Sending DB_WS request | user_id=%s | request_id=%s", user_id, request_id)

    try:
        async with websockets.connect(DB_WS_URL) as ws:
            await ws.send(json.dumps(payload))
            logger.info("📤 Request sent to WS server")

            while True:
                raw = await ws.recv()
                logger.info("📝 Raw WS response: %s", raw)

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.error("❌ Failed to decode JSON from WS response: %s", raw)
                    continue

                # Ignore unrelated message
                if data.get("request_id") != request_id:
                    logger.info("⚠️ Ignored unrelated WS message | request_id=%s", data.get("request_id"))
                    continue

                # Check for errors
                if data.get("status") != "ok":
                    logger.error("❌ DB_WS_ERROR | user_id=%s | data=%s", user_id, data)
                    return []

                donations = data.get("donations", [])
                logger.info("⬅️ DB_WS_RESPONSE | user_id=%s | donations=%d", user_id, len(donations))
                return donations

    except websockets.exceptions.ConnectionClosed as e:
        logger.error("❌ WS connection closed unexpectedly | user_id=%s | %s", user_id, e)
        return []
    except Exception as e:
        logger.exception("❌ Unexpected error fetching donations from WS | user_id=%s", user_id)
        return []
