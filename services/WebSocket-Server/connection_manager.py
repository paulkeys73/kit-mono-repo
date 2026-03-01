import logging
from typing import Dict
from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger("ws-manager")


class ConnectionManager:
    def __init__(self):
        # session_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # session_id -> user_id
        self.session_users: Dict[str, int] = {}

    async def connect(self, ws: WebSocket, session_id: str):
        """
        Register a websocket for a session.
        ASSUMES ws.accept() WAS ALREADY CALLED.
        """
        old_ws = self.active_connections.get(session_id)
        if old_ws is ws:
            return

        if old_ws and old_ws is not ws:
            try:
                if old_ws.client_state == WebSocketState.CONNECTED:
                    await old_ws.close(code=1000)
            except Exception:
                pass
            logger.debug(
                "♻️ WS_REPLACED | session_id=%s",
                session_id,
            )

        self.active_connections[session_id] = ws

        logger.info(
            "🔌 WS_CONNECTED | session_id=%s | total=%d",
            session_id,
            len(self.active_connections),
        )

    def attach_user(self, session_id: str, user_id: int):
        """
        Bind a user_id to an existing WS session.
        Safe to call multiple times.
        """
        if session_id not in self.active_connections:
            logger.warning(
                "⚠️ WS_ATTACH_SKIPPED | no active WS | session_id=%s | user_id=%s",
                session_id,
                user_id,
            )
            return

        prev = self.session_users.get(session_id)
        self.session_users[session_id] = user_id

        if prev != user_id:
            logger.debug(
                "🔗 WS_BOUND | session_id=%s | user_id=%s",
                session_id,
                user_id,
            )

    def detach_session(self, session_id: str):
        user_id = self.session_users.pop(session_id, None)
        if user_id is not None:
            logger.info(
                "WS_UNBOUND | session_id=%s | user_id=%s",
                session_id,
                user_id,
            )

    def detach_user(self, user_id: int) -> list[str]:
        detached_sessions: list[str] = []
        for session_id, uid in list(self.session_users.items()):
            if uid != user_id:
                continue
            self.session_users.pop(session_id, None)
            detached_sessions.append(session_id)

        if detached_sessions:
            logger.info(
                "WS_USER_UNBOUND | user_id=%s | sessions=%d",
                user_id,
                len(detached_sessions),
            )
        return detached_sessions

    async def safe_send(self, ws: WebSocket, payload: dict) -> bool:
        """
        Send JSON only if the socket is alive.
        Never throws.
        """
        if ws.client_state != WebSocketState.CONNECTED:
            return False

        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def broadcast_to_user(self, user_id: int, message: dict):
        """
        Send a message to all WS connections bound to a user.
        """
        for session_id, uid in list(self.session_users.items()):
            if uid != user_id:
                continue

            ws = self.active_connections.get(session_id)
            if not ws:
                self._cleanup(session_id)
                continue

            ok = await self.safe_send(ws, message)
            if not ok:
                self._cleanup(session_id)

    async def disconnect(self, session_id: str):
        """
        Explicit disconnect (client closed).
        """
        ws = self.active_connections.pop(session_id, None)
        user_id = self.session_users.pop(session_id, None)

        if ws and ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close()
            except Exception:
                pass

        logger.info(
            "🔌 WS_DISCONNECTED | session_id=%s | user_id=%s",
            session_id,
            user_id,
        )

    def _cleanup(self, session_id: str):
        """
        Internal cleanup without touching the socket.
        """
        self.active_connections.pop(session_id, None)
        self.session_users.pop(session_id, None)

        logger.debug(
            "🧹 WS_CLEANUP | session_id=%s",
            session_id,
        )

    async def close_all(self, code=1012):
        """
        Graceful shutdown.
        """
        for ws in list(self.active_connections.values()):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.close(code=code)
            except Exception:
                pass

        self.active_connections.clear()
        self.session_users.clear()

        logger.info("🛑 All WS connections closed")


# singletons
manager = ConnectionManager()
