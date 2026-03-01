# Path: E:\auth-system\Django-Allauth\auth_app\consumers\consumer.py

import os
import django
import aio_pika
import asyncio
import json
import uuid
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from rest_framework_simplejwt.tokens import RefreshToken

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Django_Settings.settings")
django.setup()

User = get_user_model()

RABBITMQ_URL = "amqp://admin:admin@localhost:5672/"
EXCHANGE_NAME = "events"
QUEUE_NAME = "auth_events"
ROUTING_KEY_PATTERN = "auth.*"  # consumes all auth events

def serialize_profile(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": f"{user.first_name} {user.last_name}".strip(),
        "avatar": user.profile_image.url if getattr(user, "profile_image", None) else "",
        "phone": getattr(user, "phone", ""),
        "bio": getattr(user, "bio", ""),
        "location": getattr(user, "location", ""),
        "country": getattr(user, "country", ""),
        "address": getattr(user, "address", ""),
        "city": getattr(user, "city", ""),
        "state": getattr(user, "state", ""),
        "postal_code": getattr(user, "postal_code", ""),
        "facebook": getattr(user, "facebook_url", ""),
        "x": getattr(user, "x_url", ""),
        "linkedin": getattr(user, "linkedin_url", ""),
        "instagram": getattr(user, "instagram_url", ""),
    }

async def handle_message(message: aio_pika.IncomingMessage):
    async with message.process():
        payload = json.loads(message.body.decode())
        correlation_id = payload.get("correlation_id") or str(uuid.uuid4())
        payload["correlation_id"] = correlation_id

        if payload.get("user_id"):
            try:
                user = await sync_to_async(User.objects.get)(id=payload["user_id"])
                payload["profile"] = serialize_profile(user)

                def create_session():
                    session = SessionStore()
                    session["user_id"] = user.id
                    session.create()
                    return session.session_key

                payload["session_token"] = await sync_to_async(create_session)()
                refresh = await sync_to_async(RefreshToken.for_user)(user)
                payload["jwt"] = {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                }
            except User.DoesNotExist:
                print(f"⚠️ User {payload['user_id']} not found, skipping enrichment.")

        # Here you can process the event in Python, e.g., send to websocket, log, etc.
        print(f"📩 Event received: {payload['event']} | user_id: {payload.get('user_id')}")

async def main():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()

    # Declare exchange
    exchange = await channel.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True)

    # Declare a queue and bind it to all auth.* events
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, ROUTING_KEY_PATTERN)

    # Start consuming
    await queue.consume(handle_message)
    print(f"📡 Listening on queue '{QUEUE_NAME}' for routing key '{ROUTING_KEY_PATTERN}'")

    await asyncio.Future()  # keep alive

if __name__ == "__main__":
    asyncio.run(main())
