# main.py
from fastapi import FastAPI, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from db import database, metadata, engine, ensure_schema_compatibility
from routes import tickets, conversations, subscribers, health, tawk_support, support

import uvicorn

app = FastAPI(title="Centralized Support System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

# Include routers
app.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])
app.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
app.include_router(subscribers.router, prefix="/subscribers", tags=["Subscribers"])
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(tawk_support.router, prefix="/tawk", tags=["Tawk Support"])
app.include_router(support.router, prefix="/support", tags=["Support"])



@app.on_event("startup")
async def startup():
    metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/ws/health")
async def ws_health_http_alias():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/health",
        },
        headers={"Upgrade": "websocket"},
    )


@app.websocket("/ws/health")
async def ws_health_socket_alias(ws: WebSocket):
    await health.health_ws(ws)


@app.get("/ws/status")
async def ws_status_http():
    return JSONResponse(
        status_code=status.HTTP_426_UPGRADE_REQUIRED,
        content={
            "status": "upgrade_required",
            "detail": "Use WebSocket protocol for /ws/health",
        },
        headers={"Upgrade": "websocket"},
    )


@app.websocket("/ws/status")
async def ws_status_socket(ws: WebSocket):
    await ws.accept()
    await ws.send_json({
        "event": "unsupported_endpoint",
        "detail": "Use ws://127.0.0.1:8099/ws/health for support health stream",
    })
    await ws.close(code=1000)

@app.get("/")
async def root():
    return {"message": "Centralized Support System API", "docs": "/docs"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8099)
