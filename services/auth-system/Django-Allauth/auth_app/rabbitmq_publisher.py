import asyncio
import json
import aio_pika
from threading import Thread, Event
import uuid
from datetime import datetime, timezone, timedelta
from auth_app import events

RABBITMQ_URL = "amqp://admin:admin@localhost:5672/"
EXCHANGE_NAME = "events"
EXCHANGE_TYPE = aio_pika.ExchangeType.TOPIC

QUEUE_BINDINGS = {
    "auth_events_queue": "auth.#",
    "ws_auth_state": ("auth.session.snapshot", "auth.logout"),
    "all_events_queue": "#",
}

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
    "state": None,
    "email": None,
    "code": None,
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
        self.ready_event = Event()

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

            for queue_name, routing_keys in QUEUE_BINDINGS.items():
                queue = await self.channel.declare_queue(queue_name, durable=True)
                if isinstance(routing_keys, str):
                    routing_keys = (routing_keys,)
                for routing_key in routing_keys:
                    await queue.bind(self.exchange, routing_key=routing_key)
                self.queues[queue_name] = queue

            print(f"🐇 RabbitMQ ready | exchange='{EXCHANGE_NAME}' | queues={list(self.queues)}")
            self.ready_event.set()
        except Exception as e:
            print(f"❌ RabbitMQ connection error: {e}")

    def _normalize_payload(self, payload: dict) -> dict:
        normalized = json.loads(json.dumps(DEFAULT_EVENT_PAYLOAD))
        normalized.update(payload)

        normalized["event"] = normalized.get("event") or "unknown.event"
        normalized["timestamp"] = normalized.get("timestamp") or datetime.now(timezone.utc).isoformat()
        normalized["correlation_id"] = normalized.get("correlation_id") or str(uuid.uuid4())

        if normalized.get("jwt") is None:
            normalized["jwt"] = {"access": None, "refresh": None}
        else:
            normalized["jwt"].setdefault("access", None)
            normalized["jwt"].setdefault("refresh", None)

        if normalized["event"] == "auth.session.snapshot" and not normalized.get("expires_at"):
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            normalized["expires_at"] = expires_at.isoformat()
            normalized["state"] = normalized.get("state") or "active"

        return normalized

    async def publish_async(self, payload: dict):
        try:
            if not self.exchange:
                raise RuntimeError("RabbitMQ exchange not ready")

            payload = self._normalize_payload(payload)
            message = aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await self.exchange.publish(message, routing_key=payload["event"])
            print(f"✅ Published | {payload['event']} | user_id={payload.get('user_id')}")
        except Exception as e:
            print(f"❌ publish_async failed: {e}")

    def publish(self, payload: dict):
        try:
            if not self.ready_event.wait(timeout=5):
                print("❌ RabbitMQ not ready — publish skipped")
                return
            future = asyncio.run_coroutine_threadsafe(self.publish_async(payload), self.loop)
            return future.result()
        except Exception as e:
            print(f"❌ publish failed: {e}")

    def _hook_auth_events(self):
        """Auto-wrap emit_* functions to publish events, except passwordless_code_sent"""
        from auth_app import events as events_module

        for attr in dir(events_module):
            if not attr.startswith("emit_"):
                continue

            # Skip emit_passwordless_code_sent to prevent double publishing
            if attr == "emit_passwordless_code_sent":
                continue

            original_fn = getattr(events_module, attr)
            if not callable(original_fn):
                continue

            def wrapper(*args, _fn=original_fn, _name=attr, **kwargs):
                result = _fn(*args, **kwargs)
                payload = kwargs.copy()
                payload["event"] = _name.replace("emit_", "auth.")
                self.publish(payload)
                return result

            setattr(events_module, attr, wrapper)


# Singleton instance
rabbit_publisher = RabbitPublisher()
