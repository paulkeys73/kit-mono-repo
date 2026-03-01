from datetime import datetime, timezone
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter()
HEALTH_WS_INTERVAL_SECONDS = 10.0


def build_health_snapshot() -> dict:
    db_status = "connected"
    error = None

    try:
        conn = settings.get_db_connection()
        conn.close()
    except Exception as exc:
        db_status = "error"
        error = str(exc)

    payload = {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "paypal-payments",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        payload["error"] = error
    return payload


@router.get("/health")
async def health_check():
    return build_health_snapshot()


@router.get("/ws/health")
async def ws_health_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/health",
        },
        headers={"Upgrade": "websocket"},
    )


@router.websocket("/ws/health")
async def ws_health(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            await websocket.send_json(
                {
                    "event": "health.update",
                    "payload": build_health_snapshot(),
                }
            )
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEALTH_WS_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return
