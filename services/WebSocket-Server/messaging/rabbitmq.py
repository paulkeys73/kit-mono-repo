import json
import logging
import aio_pika
from datetime import datetime

logger = logging.getLogger("rabbitmq")

RABBITMQ_URL = "amqp://admin:admin@localhost:5672/"
EXCHANGE_NAME = "events"


_connection = None
_channel = None
_exchange = None


async def _get_exchange():
    global _connection, _channel, _exchange

    if _exchange:
        return _exchange

    logger.info("🐇 Connecting to RabbitMQ (emitter)...")

    _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    _channel = await _connection.channel()

    _exchange = await _channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    return _exchange


async def emit_event(event_name: str, data: dict):
    exchange = await _get_exchange()

    payload = {
        "event": event_name,
        "data": data,
        "timestamp": datetime.utcnow().timestamp(),
    }

    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )

    await exchange.publish(
        message,
        routing_key=event_name,
    )

    logger.info("📤 Event emitted | %s", event_name)
