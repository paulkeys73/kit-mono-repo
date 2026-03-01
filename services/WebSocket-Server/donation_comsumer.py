import json
import logging
import aio_pika
import os
import asyncio
from datetime import datetime, timezone
from hashlib import sha256

from session_store import SESSION_STORE

logger = logging.getLogger("rabbit-donation-consumer")

RABBITMQ_URL = "amqp://admin:admin@localhost:5672/"

EXCHANGE_NAME = "events"
QUEUE_NAME = "donations_queue"

ROUTING_KEYS = [
    "donation.created",
    "donation.updated",
    "donation.stats.snapshot",
]

# ------------------------------------------------
# JSON file path (single snapshot stores)
# -------------------------------------------------
STATS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "donation_stats_store.json",
)
STATS_FILE_LOCK = asyncio.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# -------------------------------------------------
# JSON helpers
# -------------------------------------------------
def _default_stats() -> dict:
    return {
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        },
        "snapshot": None,
    }

def _load_stats() -> dict:
    if not os.path.exists(STATS_FILE):
        return _default_stats()

    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except (json.JSONDecodeError, TypeError):
        return _default_stats()

    if "meta" not in stats:
        stats["meta"] = _default_stats()["meta"]
    if "snapshot" not in stats:
        stats["snapshot"] = None

    return stats

def _write_stats(payload: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

# -------------------------------------------------
# Dedup helpers
# -------------------------------------------------
def _order_key(order_id: str) -> str:
    return f"donation:order:{order_id}"

def _snapshot_key(ts: str) -> str:
    return f"donation:snapshot:{ts}"

# -------------------------------------------------
# Consumer bootstrap
# -------------------------------------------------
async def start_donation_consumer():
    try:
        logger.info("🐇 Connecting to RabbitMQ (donations)...")
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()

        exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            QUEUE_NAME,
            durable=True,
        )

        for rk in ROUTING_KEYS:
            await queue.bind(exchange, routing_key=rk)

        logger.info(
            "🐇 Donation consumer ready | queue=%s | keys=%s",
            QUEUE_NAME,
            ROUTING_KEYS,
        )

        async with queue.iterator() as iterator:
            async for message in iterator:
                await _handle_message(message)

    except Exception:
        logger.exception("❌ Donation consumer crashed")

# -------------------------------------------------
# Message handler
# -------------------------------------------------
async def _handle_message(message: aio_pika.IncomingMessage):
    async with message.process():
        payload = json.loads(message.body)
        await process_event(payload)

# -------------------------------------------------
# Dispatcher
# -------------------------------------------------
async def process_event(event: dict):
    if event.get("event") == "donation.stats.snapshot":
        await process_stats_snapshot(event)
    else:
        await process_donation_event(event)

# -------------------------------------------------
# Donation lifecycle
# -------------------------------------------------
async def process_donation_event(event: dict):
    ts = datetime.now(timezone.utc).isoformat()
    data = event.get("data", {})

    order_id = data.get("order_id")
    status = (data.get("status") or "").upper()

    if not order_id:
        logger.warning("⚠️ Donation event missing order_id")
        return

    if status == "COMPLETED" and SESSION_STORE.exists(_order_key(order_id)):
        logger.info("♻️ Duplicate COMPLETED ignored | order_id=%s", order_id)
        return

    SESSION_STORE.store_event(event.get("event"), {**data, "ts": ts})

    logger.info("📥 Donation event | order=%s | status=%s", order_id, status)

    if status == "COMPLETED":
        SESSION_STORE.set(_order_key(order_id), True)
        logger.info("✅ Donation finalized | order_id=%s", order_id)

# -------------------------------------------------
# Stats snapshot handler (REPLACE, NOT APPEND)
# -------------------------------------------------
async def process_stats_snapshot(event: dict):
    ts = datetime.now(timezone.utc).isoformat()
    data = event.get("data", {})

    snapshot_ts = data.get("updated_at") or ts
    snapshot_key = _snapshot_key(snapshot_ts)

    if SESSION_STORE.exists(snapshot_key):
        logger.info("♻️ Duplicate stats snapshot ignored | ts=%s", snapshot_ts)
        return

    snapshot = {
        "ts": snapshot_ts,
        "currency": data.get("currency"),
        "month_start": data.get("month_start"),
        "month_end": data.get("month_end"),
        "monthly_target": data.get("monthly_target"),
        "total_raised": data.get("total_raised"),
        "net_raised": data.get("net_raised"),
        "donations_count": data.get("donations_count"),
        "percent": data.get("percent"),
        "remaining": data.get("remaining"),
    }

    async with STATS_FILE_LOCK:
        stats = _load_stats()
        stats["snapshot"] = snapshot
        stats["meta"]["last_updated"] = ts
        _write_stats(stats)

    SESSION_STORE.set(snapshot_key, True)

    logger.info(
        "📊 Stats updated | total=%s | count=%s",
        snapshot["total_raised"],
        snapshot["donations_count"],
    )

# -------------------------------------------------
# Entrypoint
# -------------------------------------------------
if __name__ == "__main__":
    logger.info("🚀 Starting donation consumer service")
    asyncio.run(start_donation_consumer())
