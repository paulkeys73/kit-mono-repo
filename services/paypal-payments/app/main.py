from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Routers
from app.routes import payments, sandbox, health, sponsor, cart, webhook

# Config
from app.config import settings, ensure_payments_table


# -------------------------
# Create FastAPI instance
# ---------------------------
app = FastAPI(
    title="PayPal Payments API",
    version="1.2.0",
)


# -----------------------------
# CORS setup
# -----------------------------
origins = [
    "http://localhost:8800",
    "http://127.0.0.1:8800",
    "http://templates.local-hostall.site",
    "http://localhost:4000",
    "http://localhost:4011",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Application lifecycle
# -----------------------------
@app.on_event("startup")
def on_startup():
    """
    Verify DB connectivity on startup with retries and ensure payments table exists.
    """
    try:
        settings.wait_for_db_connection()
        ensure_payments_table()
        print("Database connection verified and payments table ensured")
    except Exception as e:
        print("Database startup check failed:", e)
        raise


@app.on_event("shutdown")
def on_shutdown():
    print("🛑 Application shutting down")


# Close DB pool during app shutdown.
@app.on_event("shutdown")
def on_shutdown_close_pool():
    settings.close_db_pool()


# -----------------------------
# Include routes
# -----------------------------
app.include_router(payments.router)
app.include_router(sandbox.router)
app.include_router(health.router)
app.include_router(sponsor.router)
app.include_router(cart.router)
app.include_router(webhook.router)


# -----------------------------
# Run with Uvicorn
# -----------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )
