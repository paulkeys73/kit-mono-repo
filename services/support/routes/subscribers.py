# routes/subscribers.py

from fastapi import APIRouter, HTTPException, Request
from db import database, subscribers
from pydantic import BaseModel, EmailStr
from uuid import UUID, uuid4
from typing import List

router = APIRouter()

# -----------------------------
# Pydantic models
# -----------------------------
class SubscriberCreate(BaseModel):
    email: EmailStr
    project_id: UUID | None = None  # optional, middleware can supply it

class SubscriberResponse(BaseModel):
    id: UUID
    email: EmailStr
    project_id: UUID
    created_at: str

class SubscriberDelete(BaseModel):
    email: EmailStr
    project_id: UUID | None = None

# -----------------------------
# Helper to determine project_id
# -----------------------------
async def get_project_id(request: Request, payload_project_id: UUID | None) -> UUID:
    """
    Determine project_id for subscription:
    - Middleware can pass it in payload
    - Frontend direct calls fallback to default
    """
    if payload_project_id:
        return payload_project_id
    header_pid = request.headers.get("x-project-id")
    if header_pid:
        try:
            return UUID(header_pid)
        except ValueError:
            pass
    # fallback default
    return UUID("00000000-0000-0000-0000-000000000001")

# -----------------------------
# POST /subscribers/
# -----------------------------
@router.post("/", response_model=SubscriberResponse)
async def add_subscriber(payload: SubscriberCreate, request: Request):
    project_id = await get_project_id(request, payload.project_id)

    # Prevent duplicate email per project
    existing = await database.fetch_one(
        subscribers.select().where(
            (subscribers.c.email == payload.email)
            & (subscribers.c.project_id == project_id)
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="Email already subscribed")

    # Insert subscriber
    subscriber_id = uuid4()
    query = subscribers.insert().values(
        id=subscriber_id,
        email=payload.email,
        project_id=project_id,
    )
    await database.execute(query)

    return {
        "id": subscriber_id,
        "email": payload.email,
        "project_id": project_id,
        "created_at": str(await database.fetch_val(
            subscribers.select().where(subscribers.c.id == subscriber_id).with_only_columns(subscribers.c.created_at)
        ))
    }

# -----------------------------
# GET /subscribers/{project_id}
# -----------------------------
@router.get("/{project_id}", response_model=List[SubscriberResponse])
async def list_subscribers(project_id: UUID):
    rows = await database.fetch_all(
        subscribers.select().where(subscribers.c.project_id == project_id)
    )
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "project_id": r["project_id"],
            "created_at": r["created_at"].isoformat()
        }
        for r in rows
    ]

# -----------------------------
# DELETE /subscribers/
# -----------------------------
@router.delete("/", response_model=dict)
async def delete_subscriber(payload: SubscriberDelete, request: Request):
    project_id = await get_project_id(request, payload.project_id)

    query = subscribers.delete().where(
        (subscribers.c.email == payload.email)
        & (subscribers.c.project_id == project_id)
    )
    result = await database.execute(query)

    return {
        "success": True,
        "email": payload.email,
        "project_id": str(project_id),
        "deleted": result > 0
    }