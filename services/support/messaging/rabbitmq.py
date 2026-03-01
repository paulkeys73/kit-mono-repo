import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aio_pika

logger = logging.getLogger("support-rabbitmq")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "events")

_connection: aio_pika.RobustConnection | None = None
_channel: aio_pika.RobustChannel | None = None
_exchange: aio_pika.abc.AbstractExchange | None = None


async def _get_exchange() -> aio_pika.abc.AbstractExchange:
    global _connection, _channel, _exchange

    if _exchange is not None:
        return _exchange

    _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    _channel = await _connection.channel()
    _exchange = await _channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )
    return _exchange


async def emit_event(event_name: str, data: dict[str, Any]) -> None:
    exchange = await _get_exchange()

    payload = {
        "event": event_name,
        "data": data,
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }

    message = aio_pika.Message(
        body=json.dumps(payload, default=str).encode("utf-8"),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )

    await exchange.publish(message, routing_key=event_name)


async def safe_emit_event(event_name: str, data: dict[str, Any]) -> bool:
    try:
        await emit_event(event_name, data)
        return True
    except Exception:
        logger.exception("Failed to publish RabbitMQ support event | event=%s", event_name)
        return False
