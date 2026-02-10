# E:\WebSocket-Server\rabbit_consumer.py
import json
import logging
import aio_pika
from datetime import datetime
from hashlib import sha256

from session_store import SESSION_STORE
from connection_manager import ConnectionManager
from db_ws_client import DbWsClient

logger = logging.getLogger("rabbit-consumer")

RABBITMQ_URL = "amqp://admin:admin@localhost:5672/"
EXCHANGE_NAME = "events"
QUEUE_NAME = "ws_auth_state"
ROUTING_KEY = "auth.session.snapshot"

# Dedup + inflight tracking
_seen_events = set()
_inflight_db_requests = set()


def _event_fingerprint(event: dict) -> str:
    """Stable hash to deduplicate identical events."""
    raw = json.dumps(event, sort_keys=True)
    return sha256(raw.encode()).hexdigest()


async def start_rabbitmq_consumer(manager: ConnectionManager, db_ws_client: DbWsClient):
    try:
        logger.info("🐇 Connecting to RabbitMQ...")
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

        await queue.bind(exchange, routing_key=ROUTING_KEY)

        logger.info(
            "🐇 RabbitMQ ready | exchange=%s | queue=%s | rk=%s",
            EXCHANGE_NAME,
            QUEUE_NAME,
            ROUTING_KEY,
        )

        async with queue.iterator() as iterator:
            async for message in iterator:
                await _handle_message(message, manager, db_ws_client)

    except Exception:
        logger.exception("❌ Rabbit consumer crashed")


async def _handle_message(message: aio_pika.IncomingMessage, manager: ConnectionManager, db_ws_client: DbWsClient):
    async with message.process():
        payload = json.loads(message.body)
        await process_snapshot(snapshot=payload, manager=manager, db_ws_client=db_ws_client, is_replay=False, event_name=payload.get("event", "auth.session.snapshot"))


async def process_snapshot(snapshot: dict, manager: ConnectionManager, db_ws_client: DbWsClient, *, is_replay: bool, event_name: str):
    """Canonical auth event handler."""
    ts = datetime.utcnow().isoformat()
    fingerprint = _event_fingerprint(snapshot)

    if fingerprint in _seen_events:
        logger.debug("♻️ Duplicate event ignored | fp=%s", fingerprint)
        return

    _seen_events.add(fingerprint)

    user_id = snapshot.get("user_id")
    session_id = snapshot.get("session_id")
    state = snapshot.get("state", "active")
    profile = snapshot.get("profile")

    # Ignore anonymous session
    if not user_id or str(session_id).startswith("anon_"):
        logger.debug("♻️ Skipped anonymous session | session_id=%s", session_id)
        return

    # Persist raw event
    SESSION_STORE.store_event(event_name, {**snapshot, "ts": ts, "replay": is_replay})

    # Persist session
    SESSION_STORE.upsert({
        "user_id": user_id,
        "session_id": session_id,
        "state": state,
        "user": profile,
        "ts": ts,
    })

    logger.info("📥 Auth snapshot | user_id=%s | session_id=%s | replay=%s", user_id, session_id, is_replay)

    # WS Rebind
    if manager:
        manager.attach_user(session_id, user_id)

    # Broadcast to WS
    if manager and profile and state == "active":
        await manager.broadcast_to_user(user_id=user_id, message={
            "event": "auth.user.profile",
            "user_id": user_id,
            "session_id": session_id,
            "profile": profile,
            "meta": {"ts": ts, "replay": is_replay},
        })

    # DB WS restore
    request_key = f"{user_id}:{session_id}"
    if db_ws_client and request_key not in _inflight_db_requests:
        _inflight_db_requests.add(request_key)
        try:
            db_res = await db_ws_client.get_user(
                db="default",
                session_id=session_id,
                email=profile.get("email") if profile else None,
                user_id=user_id,
            )

            if db_res and db_res.get("found"):
                user = db_res["user"]
                SESSION_STORE.upsert({
                    "user_id": user["id"],
                    "session_id": session_id,
                    "state": "active",
                    "user": user,
                    "ts": ts,
                })

                await manager.broadcast_to_user(user_id=user["id"], message={
                    "event": "auth.user.profile",
                    "user_id": user["id"],
                    "session_id": session_id,
                    "profile": user,
                    "meta": {"ts": ts, "replay": True},
                })

                logger.info("✅ Session restored from DB WS | user_id=%s | session_id=%s", user["id"], session_id)

        except Exception:
            logger.exception("⚠️ DB WS fetch failed | user_id=%s | session_id=%s", user_id, session_id)
        finally:
            _inflight_db_requests.discard(request_key)
