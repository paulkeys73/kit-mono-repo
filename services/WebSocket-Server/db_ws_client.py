# E:\WebSocket-Server\db_ws_client.py

import asyncio
import json
import uuid
import logging
import websockets
from user_session_store import update_user_session

logger = logging.getLogger("db-ws-client")


class DbWsClient:
    def __init__(self, url: str):
        self.url = url
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self._connected = asyncio.Event()

    async def connect(self):
        """Persistent connection to DB WebSocket with auto-reconnect and push updates."""
        while True:
            try:
                logger.info("🗄️ Connecting to DB WS: %s", self.url)
                self.ws = await websockets.connect(self.url)
                self._connected.set()
                logger.info("🗄️ DB WS connected")

                async for message in self.ws:
                    payload = json.loads(message)
                    request_id = payload.get("request_id")
                    event = payload.get("event")

                    # Fulfill pending request futures
                    if request_id and request_id in self.pending:
                        self.pending[request_id].set_result(payload)
                        del self.pending[request_id]

                    # Handle DB push updates (reactive)
                    if event in ("db.user.updated", "db.user.result"):
                        await self._store_user_session(payload)

            except Exception as e:
                logger.warning("❌ DB WS lost, reconnecting in 2s: %s", e)
                self._connected.clear()
                await asyncio.sleep(2)

    async def get_user(
        self,
        db: str,
        session_id: str | None = None,
        email: str | None = None,
        user_id: str | None = None,
        timeout: int = 3,
    ) -> dict | None:
        """Send session_id, email, and/or user_id to DB WS and return user info."""
        await self._connected.wait()
        if not self.ws:
            logger.warning("⚠️ DB WS not connected, cannot send payload")
            return None

        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self.pending[request_id] = future

        payload = {"event": "db.user.get", "request_id": request_id, "db": db}
        if session_id:
            payload["session_id"] = session_id
        if email:
            payload["email"] = email
        if user_id:
            payload["user_id"] = user_id

        logger.info("📨 Sending DB WS payload: %s", payload)
        try:
            await self.ws.send(json.dumps(payload))
        except Exception as e:
            logger.error("❌ Failed to send payload: %s | error=%s", payload, e)
            self.pending.pop(request_id, None)
            return None

        try:
            response = await asyncio.wait_for(future, timeout)
            logger.info("📬 Received DB WS response: %s", response)
            await self._store_user_session(response)
            return response
        except asyncio.TimeoutError:
            self.pending.pop(request_id, None)
            logger.warning("⏱️ DB WS request timed out for payload: %s", payload)
            return None

    async def _store_user_session(self, response: dict):
        """Standardize and store user data from DB WS response or push event."""
        user = response.get("user")
        if not user:
            return

        session_id = response.get("session_id", f"anon_{user.get('id', 'unknown')}")
        user_data = {
            
    "user_id": user.get("id", 0),
    "session_id": session_id,
    "profile": {
        "id": user.get("id", 0),
        "username": user.get("username", ""),
        "full_name": f"{user.get('first_name','')} {user.get('last_name','')}".strip(),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "email": user.get("email", ""),
        "phone": user.get("phone", ""),
        "bio": user.get("bio", ""),
        "location": user.get("location", ""),
        "country": user.get("country", ""),
        "address": user.get("address", ""),
        "state": user.get("state", ""),
        "city": user.get("city", ""),
        "postal_code": user.get("postal_code", ""),
        "facebook_url": user.get("facebook_url", ""),
        "x_url": user.get("x_url", ""),
        "linkedin_url": user.get("linkedin_url", ""),
        "instagram_url": user.get("instagram_url", ""),
        "avatar": user.get("profile_image", ""),  # ⚠️ must match your frontend field
        "is_authenticated": True,
        "is_staff": user.get("is_staff", False),
        "is_superuser": user.get("is_superuser", False),
            },
            "meta": response.get("meta", {}),
        }

        update_user_session(user_data)
        logger.info(f"💾 User session updated | user_id={user_data['user_id']} | session_id={session_id}")
