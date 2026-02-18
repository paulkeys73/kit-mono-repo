import asyncio
import json
import aio_pika
from threading import Thread
import uuid
from datetime import datetime, timezone, timedelta
from auth_app import events

RABBITMQ_URL = "amqp://admin:admin@localhost:5672/"
EXCHANGE_NAME = "events"
EXCHANGE_TYPE = aio_pika.ExchangeType.TOPIC

QUEUE_BINDINGS = {
    "auth_events_queue": "auth.#",
    "ws_auth_state": "auth.session.snapshot",
    "all_events_queue": "#",
}

# -----------------------------
# DEFAULT EVENT SCHEMA
# -----------------------------
DEFAULT_EVENT_PAYLOAD = {
    "event": None,
    "timestamp": None,
    "correlation_id": None,
    "user_id": None,
    "session_id": None,
    "session_token": None,
    "profile": None,
    "jwt": {"access": None, "refresh": None},
    "expires_at": None,
    "state": None,  # active | logged_out | expired
}

class RabbitPublisher:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self._start_loop, daemon=True)
        self.thread.start()

        self.connection = None
        self.channel = None
        self.exchange = None
        self.queues = {}

        # Connect asynchronously
        asyncio.run_coroutine_threadsafe(self._connect(), self.loop)
        self._hook_auth_events()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect(self):
        try:
            self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
            self.channel = await self.connection.channel(publisher_confirms=True)

            self.exchange = await self.channel.declare_exchange(
                EXCHANGE_NAME, EXCHANGE_TYPE, durable=True
            )

            for queue_name, routing_key in QUEUE_BINDINGS.items():
                queue = await self.channel.declare_queue(queue_name, durable=True)
                await queue.bind(self.exchange, routing_key=routing_key)
                self.queues[queue_name] = queue

            print(f"🐇 RabbitMQ ready | exchange='{EXCHANGE_NAME}' | queues={list(self.queues)}")
        except Exception as e:
            print(f"❌ RabbitMQ connection error: {e}")

    # -----------------------------
    # PAYLOAD NORMALIZATION
    # -----------------------------
    def _normalize_payload(self, payload: dict) -> dict:
        normalized = json.loads(json.dumps(DEFAULT_EVENT_PAYLOAD))  # deep copy
        normalized.update(payload)

        normalized["event"] = normalized.get("event") or "unknown.event"
        normalized["timestamp"] = normalized.get("timestamp") or datetime.now(timezone.utc).isoformat()
        normalized["correlation_id"] = normalized.get("correlation_id") or str(uuid.uuid4())

        # Normalize JWT
        if normalized.get("jwt") is None:
            normalized["jwt"] = {"access": None, "refresh": None}
        else:
            normalized["jwt"].setdefault("access", None)
            normalized["jwt"].setdefault("refresh", None)

        # Set TTL for session snapshots if not set
        if normalized["event"] == "auth.session.snapshot" and "expires_at" not in normalized:
            # Default TTL 24h
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            normalized["expires_at"] = expires_at.isoformat()
            normalized["state"] = normalized.get("state") or "active"

        return normalized

    async def publish_async(self, payload: dict):
        try:
            payload = self._normalize_payload(payload)
            message = aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await self.exchange.publish(message, routing_key=payload["event"])
            print(f"✅ Published | {payload['event']} | user_id={payload['user_id']}")
        except Exception as e:
            print(f"❌ publish_async failed: {e}")

    def publish(self, payload: dict):
        try:
            future = asyncio.run_coroutine_threadsafe(self.publish_async(payload), self.loop)
            return future.result()
        except Exception as e:
            print(f"❌ publish failed: {e}")

    # -----------------------------
    # AUTO-HOOK AUTH EVENTS
    # -----------------------------
    def _hook_auth_events(self):
        for attr in dir(events):
            if not attr.startswith("emit_"):
                continue

            original_fn = getattr(events, attr)
            if not callable(original_fn):
                continue

            def wrapper(*args, _fn=original_fn, _name=attr, **kwargs):
                result = _fn(*args, **kwargs)

                # Build event payload dynamically
                payload = {
                    "event": _name.replace("emit_", "auth."),
                    "user_id": args[0] if len(args) > 0 else None,
                    "session_id": args[1] if len(args) > 1 else None,
                    "profile": args[2] if len(args) > 2 else None,
                    "jwt": args[3] if len(args) > 3 else None,
                }

                # Publish safely
                self.publish(payload)
                return result

            setattr(events, attr, wrapper)


# Singleton
rabbit_publisher = RabbitPublisher()
