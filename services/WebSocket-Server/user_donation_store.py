import json
import logging
import asyncio
from pathlib import Path
from threading import Lock
from datetime import datetime
from typing import Dict, List, Union

from connection_manager import ConnectionManager
from db_donation_ws_client import fetch_user_donations_from_db

# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("user-donation-store")

# --------------------------------------------------
# Config
# --------------------------------------------------
STORE_FILE = Path("user_donation_store.json")
STORE_FILE.touch(exist_ok=True)
_lock = Lock()

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def _load_store() -> Dict[str, dict]:
    with _lock:
        try:
            logger.info("📥 Loading donation store from %s", STORE_FILE)
            data = json.load(STORE_FILE.open("r", encoding="utf-8"))
            logger.info("✅ Donation store loaded | %d users", len(data))
            return data
        except json.JSONDecodeError:
            logger.warning("⚠️ Donation store corrupted, resetting")
            return {}
        except Exception:
            logger.exception("❌ Failed to load donation store")
            return {}

def _save_store(data: Dict[str, dict]):
    with _lock:
        try:
            json.dump(data, STORE_FILE.open("w", encoding="utf-8"), indent=2, ensure_ascii=False)
            logger.info("💾 Donation store saved | %d users", len(data))
        except Exception:
            logger.exception("❌ Failed to save donation store")

def _donation_key(donation: dict) -> str | None:
    meta = donation.get("metadata") or {}
    return meta.get("order_id") or donation.get("id")

# --------------------------------------------------
# Core Logic
# --------------------------------------------------
def update_user_donations(user_id: int, donations: Union[dict, List[dict]], session_id: str | None = None):
    if not user_id:
        raise ValueError("user_id is required")

    if isinstance(donations, dict):
        donations = [donations]

    store = _load_store()
    user_key = str(user_id)

    entry = store.get(user_key, {
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "donations": {},
    })

    logger.info("📝 Updating donations for user_id=%s | existing=%d donations", user_id, len(entry["donations"]))

    for donation in donations:
        key = _donation_key(donation)
        if not key:
            logger.warning("⚠️ Skipping donation with missing key: %s", donation)
            continue
        entry["donations"][key] = {**donation, "_stored_at": datetime.utcnow().isoformat()}

    entry["session_id"] = session_id
    entry["updated_at"] = datetime.utcnow().isoformat()
    store[user_key] = entry

    _save_store(store)
    logger.info("✅ Donations updated | user_id=%s | total=%d", user_id, len(entry["donations"]))

    return entry

async def retrieve_and_push_user_donations(user_id: int):
    logger.info("🚀 Fetching donations from DB for user_id=%s", user_id)
    donations = await fetch_user_donations_from_db(user_id)

    if not donations:
        logger.info("⚠️ No donations found for user_id=%s", user_id)
        return

    logger.info("📦 %d donations received from DB for user_id=%s", len(donations), user_id)
    entry = update_user_donations(user_id, donations)

    payload = {
        "type": "donation_snapshot",
        "user_id": user_id,
        "donations": list(entry["donations"].values()),
        "updated_at": entry["updated_at"],
    }

    logger.info("📡 Broadcasting donation snapshot to user_id=%s | donations=%d",
                user_id, len(entry["donations"]))
    await ConnectionManager.broadcast_to_user(user_id, payload)
    logger.info("✅ Donations successfully pushed to user_id=%s", user_id)

def get_user_donations(user_id: int) -> dict | None:
    logger.info("🔍 Retrieving donations from local store for user_id=%s", user_id)
    return _load_store().get(str(user_id))
