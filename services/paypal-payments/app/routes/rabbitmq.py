import aio_pika
import asyncio
import json
import logging
import time
from typing import Optional
from datetime import datetime, date
from decimal import Decimal

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rabbitmq")

# -----------------------------
# Config
# -----------------------------
RABBITMQ_URL = "amqp://admin:admin@localhost:5672/"
DEFAULT_QUEUE = "donations_queue"
RECONNECT_DELAY = 5  # seconds

# -----------------------------
# Connection state
# -----------------------------
_connection: Optional[aio_pika.RobustConnection] = None
_channel: Optional[aio_pika.Channel] = None
_lock = asyncio.Lock()

# -----------------------------
# Utilities
# -----------------------------
async def get_channel() -> aio_pika.Channel:
    """Return a robust channel, reconnecting if necessary."""
    global _connection, _channel
    async with _lock:
        while True:
            try:
                if _connection is None or _connection.is_closed:
                    _connection = await aio_pika.connect_robust(RABBITMQ_URL)
                    logger.info("RabbitMQ connection established at %s", RABBITMQ_URL)
                if _channel is None or _channel.is_closed:
                    _channel = await _connection.channel()
                    logger.info("RabbitMQ channel created and ready")
                return _channel
            except Exception as e:
                logger.error("Failed to get channel: %s. Retrying in %ds...", e, RECONNECT_DELAY)
                await asyncio.sleep(RECONNECT_DELAY)

async def publish_json(payload: dict, queue_name: str = DEFAULT_QUEUE) -> None:
    """
    Publish a JSON-serializable dict to a RabbitMQ queue.
    Ensures the queue exists before sending.
    """
    if not isinstance(queue_name, str):
        raise TypeError(f"queue_name must be a string, got {type(queue_name)}")

    if not isinstance(payload, dict):
        raise TypeError(f"payload must be a dict, got {type(payload)}")

    channel = await get_channel()
    await channel.declare_queue(queue_name, durable=True)

    def _json_default(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, set):
            return list(value)
        return str(value)

    message = aio_pika.Message(
        body=json.dumps(payload, default=_json_default).encode("utf-8"),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )

    try:
        await channel.default_exchange.publish(message, routing_key=queue_name)
        logger.info("Message published successfully to queue '%s'", queue_name)
    except Exception as e:
        logger.error("Failed to publish message: %s", e)

async def emit_event(event_type: str, data: dict, queue_name: str = DEFAULT_QUEUE) -> None:
    """Emit a structured event with timestamp."""
    payload = {
        "event": event_type,
        "data": data,
        "timestamp": time.time(),
    }
    await publish_json(payload, queue_name)

# -----------------------------
# Consumer
# -----------------------------
async def consume_queue(queue_name: str = DEFAULT_QUEUE, callback=None):
    """
    Consume messages from a given queue and process via a callback.
    Default behavior: log message.
    """
    channel = await get_channel()
    queue = await channel.declare_queue(queue_name, durable=True)
    logger.info("Consuming from queue '%s'...", queue_name)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                try:
                    payload = json.loads(message.body.decode())
                    if callback:
                        await callback(payload)
                    else:
                        logger.info("Received message: %s", json.dumps(payload, indent=2))
                except Exception as e:
                    logger.error("Failed to process message: %s", e)

# -----------------------------
# Interactive test loop
# -----------------------------
async def interactive_emit_loop():
    """
    Async-friendly loop to emit events interactively.
    Uses asyncio.to_thread to avoid blocking the event loop.
    """
    while True:
        event_type = await asyncio.to_thread(input, "Enter event type (or 'quit' to exit): ")
        if event_type.lower() == "quit":
            break
        data_str = await asyncio.to_thread(input, "Enter JSON payload (e.g., {\"msg\":\"hello\"}): ")
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            logger.error("Invalid JSON. Try again.")
            continue

        await emit_event(event_type, data)
        logger.info("Event emitted successfully.")

# -----------------------------
# Main runner for testing
# -----------------------------
async def main():
    consumer_task = asyncio.create_task(consume_queue())
    try:
        await interactive_emit_loop()
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            logger.info("Consumer stopped.")

if __name__ == "__main__":
    asyncio.run(main())
