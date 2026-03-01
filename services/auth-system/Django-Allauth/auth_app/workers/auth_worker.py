#E:\auth-system\Django-Allauth\auth_app\workers\auth_worker.py



import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone


logger = logging.getLogger(__name__)

class EventConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """
        Accepts the WebSocket connection and subscribes to the 'events' group.
        """
        await self.accept()
        await self.channel_layer.group_add("events", self.channel_name)
        logger.info(f"WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code):
        """
        Removes the WebSocket from the 'events' group when disconnected.
        """
        await self.channel_layer.group_discard("events", self.channel_name)
        logger.info(f"WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data):
        """
        Handles messages received from clients (optional for future extensions).
        """
        logger.info(f"Received from client: {text_data}")

    async def broadcast_event(self, event):
        """
        Called by the channel_layer to push events to WebSocket clients.
        Filters only relevant auth events.
        """
        payload = event.get("payload", {})

        event_type = payload.get("event")
        # Only push recognized auth event
        allowed_events = [
            "auth.user.created",
            "auth.email.verification.sent",
            "auth.email.verified",
            "auth.login.success",
            "auth.login.failed",
            "auth.logout",
            "auth.password.reset.request",
            "auth.password.reset.completed",
        ]

        if event_type in allowed_events:
            await self.send(text_data=json.dumps(payload))
            logger.info(f"Pushed event to client: {event_type}")


# ----------------- HELPER TO PUSH EVENTS FROM OUTSIDE -----------------
def push_event_to_websockets(event_name: str, payload: dict):
    """
    Optional helper to push events directly to WebSocket clients
    from other parts of Django code if needed.
    """
    enriched_payload = {
        "event": event_name,
        "timestamp": timezone.now().isoformat(),
        **payload
    }

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "events",
            {
                "type": "broadcast_event",
                "payload": enriched_payload
            }
        )
        logger.info(f"Event broadcasted via WebSocket: {event_name}")
    except Exception as e:
        logger.error(f"[WS ERROR] Failed to broadcast event '{event_name}': {e}")
