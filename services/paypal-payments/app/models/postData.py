import asyncio
import aiohttp
import json
import logging
import hashlib
from pathlib import Path
from typing import Dict
from copy import deepcopy

from watchfiles import awatch
from aiohttp import ClientConnectorError

# 🔌 RabbitMQ
from rabbitmq import emit_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("json-db-watcher")

# ------------------------------------------------
# Background task tracking
# -------------------------------------------------
BACKGROUND_TASKS: set[asyncio.Task] = set()

def track_task(coro):
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)

# -------------------------------------------------
# Paths
# -------------------------------------------------
APP_DIR = Path(__file__).parent.parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DONATIONS_FILE = DATA_DIR / "donations.json"
STATS_FILE = DATA_DIR / "stats.json"

# -------------------------------------------------
# Endpoints
# -------------------------------------------------
DB_BASE = "http://localhost:8011"
DB_CREATE_URL = f"{DB_BASE}/donations/"
DB_UPDATE_URL = f"{DB_BASE}/donations/update-by-order/"
STATS_SERVER_URL = f"{DB_BASE}/donations/stats/"
DB_HEALTH_URL = f"{DB_BASE}/health"

# -------------------------------------------------
# Runtime state (dedup + idempotency)
# -------------------------------------------------
PROCESSED_ORDERS: set[str] = set()
LAST_STATS_HASH: str | None = None

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def hash_payload(payload: Dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()

async def wait_for_db():
    logger.info("⏳ Waiting for DB readiness...")
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(DB_HEALTH_URL) as r:
                    if r.status == 200:
                        logger.info("✅ DB ready")
                        return
        except Exception:
            pass
        await asyncio.sleep(2)

async def safe_request(method, url, session, retries=5, **kwargs):
    delay = 1
    for attempt in range(retries):
        try:
            async with session.request(method, url, **kwargs) as resp:
                return resp, await resp.text()
        except ClientConnectorError:
            logger.warning("⏳ DB not reachable (%s %s), retry %s",
                           method, url, attempt + 1)
        except Exception:
            logger.exception("❌ Unexpected HTTP error")

        await asyncio.sleep(delay)
        delay = min(delay * 2, 10)

    logger.error("❌ Max retries exceeded for %s %s", method, url)
    return None, None

# -------------------------------------------------
# Donation schema
# -------------------------------------------------
DONATION_SCHEMA = {
    "id": None,
    "user_id": None,
    "amount": None,
    "currency": None,
    "status": None,
    "full_name": None,
    "user_name": None,
    "first_name": None,
    "last_name": None,
    "email": None,
    "card_last4": None,
    "card_brand": None,
    "card_type": None,
    "network": None,
    "network_reference_id": None,
    "paypal_fee": None,
    "net_amount": None,
    "tier_id": None,
    "order_id": None,
    "source": None,
    "method": None,
    "payment_type": None,
    "billing_full_name": None,
    "billing_country": None,
    "extra_metadata": None,
}

# -------------------------------------------------
# Normalize donation
# -------------------------------------------------
def normalize_donation_payload(event: Dict) -> Dict:
    payload = deepcopy(DONATION_SCHEMA)
    metadata = event.get("metadata") or {}

    payload.update({
        "id": event.get("id"),
        "status": event.get("status"),
        "amount": event.get("amount"),
        "currency": event.get("currency"),
        "user_id": event.get("user_id"),
        "user_name": event.get("user_name"),
        "first_name": event.get("first_name"),
        "last_name": event.get("last_name"),
        "full_name": event.get("full_name"),
        "email": event.get("email"),
        "card_last4": event.get("card_last4"),
        "card_brand": event.get("card_brand"),
        "card_type": event.get("card_type"),
        "network": event.get("network"),
        "network_reference_id": event.get("network_reference_id"),
        "paypal_fee": event.get("paypal_fee"),
        "net_amount": event.get("net_amount"),
        "tier_id": event.get("tier_id"),
        "order_id": metadata.get("order_id"),
        "source": metadata.get("source"),
        "method": metadata.get("method"),
        "payment_type": metadata.get("type"),
        "billing_full_name": metadata.get("billing_full_name"),
        "billing_country": metadata.get("billing_country"),
    })
    return payload

# -------------------------------------------------
# Donation ops (deduplicated)
# -------------------------------------------------
async def create_donation(event: Dict):
    payload = normalize_donation_payload(event)
    order_id = payload.get("order_id")

    if order_id in PROCESSED_ORDERS:
        return

    async with aiohttp.ClientSession() as session:
        resp, body = await safe_request(
            "POST", DB_CREATE_URL, session, json=payload
        )
        if resp and resp.status == 200:
            PROCESSED_ORDERS.add(order_id)
            logger.info("CREATE donation | OK | %s", order_id)
            await emit_event("donation.created", payload)

async def update_donation(event: Dict):
    payload = normalize_donation_payload(event)
    order_id = payload.get("order_id")

    if not order_id or order_id in PROCESSED_ORDERS:
        return

    async with aiohttp.ClientSession() as session:
        resp, body = await safe_request(
            "PATCH",
            f"{DB_UPDATE_URL}{order_id}",
            session,
            json=payload,
        )
        if resp and resp.status == 200:
            PROCESSED_ORDERS.add(order_id)
            logger.info("UPDATE donation | OK | %s", order_id)
            await emit_event("donation.updated", payload)

def push_donation(event: Dict):
    status = (event.get("status") or "").upper()
    if status in ("CREATING", "CREATED", "PENDING"):
        track_task(create_donation(event))
    elif status == "COMPLETED":
        track_task(update_donation(event))

# -------------------------------------------------
# Stats (idempotent)
# -------------------------------------------------
async def push_stats(stats: Dict):
    global LAST_STATS_HASH
    current_hash = hash_payload(stats)

    if current_hash == LAST_STATS_HASH:
        return

    LAST_STATS_HASH = current_hash

    async with aiohttp.ClientSession() as session:
        resp, body = await safe_request(
            "POST", STATS_SERVER_URL, session, json=stats
        )
        if resp and resp.status == 200:
            logger.info("✅ Stats pushed")
            await emit_event(
                "donation.stats.snapshot",
                {"event": "donation.stats.snapshot", "data": stats},
            )

# -------------------------------------------------
# Watcher
# -------------------------------------------------
async def watch_json_files():
    logger.info("👀 Watching %s", DATA_DIR)

    async for changes in awatch(DATA_DIR):
        for _, path in changes:
            path = Path(path)

            if path == DONATIONS_FILE:
                for d in json.loads(DONATIONS_FILE.read_text()):
                    push_donation(d)

            elif path == STATS_FILE:
                stats = json.loads(STATS_FILE.read_text())
                if isinstance(stats, dict):
                    await push_stats(stats)

# -------------------------------------------------
# Initial replay
# -------------------------------------------------
async def push_all_data():
    if DONATIONS_FILE.exists():
        for d in json.loads(DONATIONS_FILE.read_text()):
            push_donation(d)

    if STATS_FILE.exists():
        stats = json.loads(STATS_FILE.read_text())
        if isinstance(stats, dict):
            await push_stats(stats)

    if BACKGROUND_TASKS:
        await asyncio.gather(*BACKGROUND_TASKS, return_exceptions=True)

# -------------------------------------------------
# MAIN
# -------------------------------------------------
async def main():
    logger.info("🚀 Starting JSON → DB watcher")

    await wait_for_db()
    await push_all_data()
    await watch_json_files()

if __name__ == "__main__":
    asyncio.run(main())
