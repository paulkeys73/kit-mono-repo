# E:\WebSocket-Server\rabbit_consumer.py
import json
import logging
import os
from datetime import datetime
from hashlib import sha256
from typing import Awaitable, Callable, Optional

import aio_pika

from connection_manager import ConnectionManager
from db_ws_client import DbWsClient
from session_store import SESSION_STORE
from user_session_store import remove_by_session_id, remove_user_session

logger = logging.getLogger("rabbit-consumer")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "events")
QUEUE_NAME = "ws_auth_state"
ROUTING_KEYS = ("auth.session.snapshot", "auth.logout")

SUPPORT_QUEUE_NAME = "ws_support_events"
SUPPORT_ROUTING_KEYS = (
    "support.ticket.created",
    "support.ticket.updated",
    "support.ticket.deleted",
    "support.conversation.created",
)

# Dedup + inflight tracking
_seen_events = set()
_inflight_db_requests = set()


def _event_fingerprint(event: dict) -> str:
    """Stable hash to deduplicate identical events."""
    raw = json.dumps(event, sort_keys=True)
    return sha256(raw.encode()).hexdigest()


async def start_rabbitmq_consumer(manager: ConnectionManager, db_ws_client: DbWsClient):
    try:
        logger.info("Connecting to RabbitMQ for auth events")
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

        for routing_key in ROUTING_KEYS:
            await queue.bind(exchange, routing_key=routing_key)

        logger.info(
            "RabbitMQ ready | exchange=%s | queue=%s | keys=%s",
            EXCHANGE_NAME,
            QUEUE_NAME,
            ",".join(ROUTING_KEYS),
        )

        async with queue.iterator() as iterator:
            async for message in iterator:
                await _handle_message(message, manager, db_ws_client)

    except Exception:
        logger.exception("Rabbit auth consumer crashed")


async def start_support_rabbitmq_consumer(
    support_handler: Callable[[str, dict, dict], Awaitable[None]],
):
    try:
        logger.info("Connecting to RabbitMQ for support events")
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()

        exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            SUPPORT_QUEUE_NAME,
            durable=True,
        )

        for routing_key in SUPPORT_ROUTING_KEYS:
            await queue.bind(exchange, routing_key=routing_key)

        logger.info(
            "RabbitMQ ready | exchange=%s | queue=%s | keys=%s",
            EXCHANGE_NAME,
            SUPPORT_QUEUE_NAME,
            ",".join(SUPPORT_ROUTING_KEYS),
        )

        async with queue.iterator() as iterator:
            async for message in iterator:
                async with message.process():
                    envelope = _decode_message(message)
                    event_name = str(envelope.get("event") or message.routing_key or "")
                    data = envelope.get("data")
                    if not isinstance(data, dict):
                        data = {"value": data}

                    if not event_name:
                        logger.warning("Dropped support event without event name")
                        continue

                    await support_handler(event_name, data, envelope)

    except Exception:
        logger.exception("Rabbit support consumer crashed")


def _decode_message(message: aio_pika.IncomingMessage) -> dict:
    try:
        payload = json.loads(message.body)
    except Exception:
        logger.exception("Failed to decode RabbitMQ message")
        return {}

    if isinstance(payload, dict):
        return payload
    return {"data": payload}


async def _handle_message(
    message: aio_pika.IncomingMessage,
    manager: ConnectionManager,
    db_ws_client: DbWsClient,
):
    async with message.process():
        payload = _decode_message(message)
        event_name = str(payload.get("event") or message.routing_key or "auth.session.snapshot")
        await process_snapshot(
            snapshot=payload,
            manager=manager,
            db_ws_client=db_ws_client,
            is_replay=False,
            event_name=event_name,
        )


async def process_snapshot(
    snapshot: dict,
    manager: ConnectionManager,
    db_ws_client: DbWsClient,
    *,
    is_replay: bool,
    event_name: str,
):
    """Canonical auth event handler."""
    ts = datetime.utcnow().isoformat()
    fingerprint = _event_fingerprint(snapshot)

    if fingerprint in _seen_events:
        logger.debug("Duplicate event ignored | fp=%s", fingerprint)
        return

    _seen_events.add(fingerprint)

    user_id = snapshot.get("user_id")
    session_id = snapshot.get("session_id")
    state = snapshot.get("state") or ("logged_out" if event_name == "auth.logout" else "active")
    profile = snapshot.get("profile")

    # Ignore anonymous session
    if not user_id or str(session_id).startswith("anon_"):
        logger.debug("Skipped anonymous session | session_id=%s", session_id)
        return

    # Persist raw event
    SESSION_STORE.store_event(event_name, {**snapshot, "ts": ts, "replay": is_replay})

    if state != "active":
        SESSION_STORE.remove_user_sessions(user_id)
        remove_user_session(user_id)
        if session_id:
            remove_by_session_id(session_id)

        if manager:
            await manager.broadcast_to_user(
                user_id=user_id,
                message={
                    "event": "auth.logged_out",
                    "user_id": user_id,
                    "session_id": session_id,
                    "state": state,
                    "meta": {"ts": ts, "replay": is_replay},
                },
            )
            await manager.broadcast_to_user(
                user_id=user_id,
                message={
                    "event": "auth.anonymous",
                    "user_id": user_id,
                    "session_id": session_id,
                    "meta": {"ts": ts, "replay": is_replay},
                },
            )
            manager.detach_user(user_id)
            if session_id:
                manager.detach_session(session_id)

        logger.info(
            "Auth session invalidated | user_id=%s | session_id=%s | state=%s | replay=%s",
            user_id,
            session_id,
            state,
            is_replay,
        )
        return

    if not session_id:
        logger.warning("Active auth event missing session_id | user_id=%s", user_id)
        return

    # Persist session
    SESSION_STORE.upsert(
        {
            "user_id": user_id,
            "session_id": session_id,
            "state": state,
            "user": profile,
            "ts": ts,
        }
    )

    logger.info("Auth snapshot | user_id=%s | session_id=%s | replay=%s", user_id, session_id, is_replay)

    # WS Rebind
    if manager:
        manager.attach_user(session_id, user_id)

    # Broadcast to WS
    if manager and profile:
        await manager.broadcast_to_user(
            user_id=user_id,
            message={
                "event": "auth.user.profile",
                "user_id": user_id,
                "session_id": session_id,
                "profile": profile,
                "meta": {"ts": ts, "replay": is_replay},
            },
        )

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
                current_session = SESSION_STORE.get(session_id)
                if not current_session or current_session.get("user_id") != user_id:
                    logger.info(
                        "Skipped DB restore for stale session | user_id=%s | session_id=%s",
                        user_id,
                        session_id,
                    )
                    return
                SESSION_STORE.upsert(
                    {
                        "user_id": user["id"],
                        "session_id": session_id,
                        "state": "active",
                        "user": user,
                        "ts": ts,
                    }
                )

                if manager:
                    await manager.broadcast_to_user(
                        user_id=user["id"],
                        message={
                            "event": "auth.user.profile",
                            "user_id": user["id"],
                            "session_id": session_id,
                            "profile": user,
                            "meta": {"ts": ts, "replay": True},
                        },
                    )

                logger.info("Session restored from DB WS | user_id=%s | session_id=%s", user["id"], session_id)

        except Exception:
            logger.exception("DB WS fetch failed | user_id=%s | session_id=%s", user_id, session_id)
        finally:
            _inflight_db_requests.discard(request_key)
