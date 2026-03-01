import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from db import database

router = APIRouter()
HEALTH_WS_INTERVAL_SECONDS = 10.0


async def build_health_snapshot() -> dict:
    db_status = "disconnected"

    try:
        if database.is_connected:
            # lightweight query to verify DB responsiveness
            await database.execute("SELECT 1")
            db_status = "connected"
    except Exception:
        db_status = "error"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "service": "centralized-support-system",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/", summary="Service health check")
async def health_check():
    return await build_health_snapshot()


@router.get("/ws")
async def ws_health_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /health/ws",
        },
        headers={"Upgrade": "websocket"},
    )


@router.websocket("/ws")
async def health_ws(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            await websocket.send_json(
                {
                    "event": "health.update",
                    "payload": await build_health_snapshot(),
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
