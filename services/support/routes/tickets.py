# routes/tickets.py
from datetime import datetime, timezone
import os
import uuid
from typing import List, Optional, Union, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from db import database, support_tickets
from messaging.rabbitmq import safe_emit_event
from models import TicketResponse, TicketUpdate

router = APIRouter()
UPLOAD_DIR = "data/uploads"


def _serialize_record(record: Any) -> dict[str, Any]:
    if record is None:
        return {}

    item = dict(record)
    for key, value in list(item.items()):
        if isinstance(value, uuid.UUID):
            item[key] = str(value)
        elif isinstance(value, datetime):
            item[key] = value.isoformat()
        elif hasattr(value, "value"):
            item[key] = value.value
    return item


@router.post("/", response_model=dict)
async def create_ticket(
    project_id: uuid.UUID = Form(...),
    user_id: int = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    priority: Optional[str] = Form("normal"),
    upload: Optional[Union[UploadFile, str]] = File(None),
):
    ticket_id = uuid.uuid4()
    file_path = None

    # Some clients send upload="" when no file is selected.
    # Accept that payload and treat it as no file instead of 422.
    if isinstance(upload, UploadFile) and upload.filename:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file_path = f"{UPLOAD_DIR}/{ticket_id}_{upload.filename}"
        with open(file_path, "wb") as f:
            f.write(await upload.read())

    normalized_priority = (priority or "normal").lower()

    query = support_tickets.insert().values(
        id=ticket_id,
        project_id=project_id,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        subject=subject,
        message=message,
        status="open",
        priority=normalized_priority,
        file_path=file_path,
    )
    await database.execute(query)

    await safe_emit_event(
        "support.ticket.created",
        {
            "ticket_id": str(ticket_id),
            "project_id": str(project_id),
            "user_id": user_id,
            "status": "open",
            "ticket": {
                "id": str(ticket_id),
                "project_id": str(project_id),
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "subject": subject,
                "message": message,
                "status": "open",
                "priority": normalized_priority,
                "file_path": file_path,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )

    return {"success": True, "ticket_id": str(ticket_id)}


@router.get("/", response_model=List[TicketResponse])
async def get_all_tickets(
    project_id: Optional[uuid.UUID] = None,
    username: Optional[str] = None,
    email: Optional[str] = None,
    user_id: Optional[int] = None,
):
    query = """
        SELECT
            id::text AS id,
            project_id::text AS project_id,
            user_id,
            username,
            first_name,
            last_name,
            email,
            subject,
            message,
            status::text AS status,
            priority::text AS priority,
            file_path,
            created_at,
            updated_at
        FROM support_tickets
        WHERE (CAST(:project_id AS uuid) IS NULL OR project_id = CAST(:project_id AS uuid))
          AND (CAST(:username AS text) IS NULL OR username = CAST(:username AS text))
          AND (CAST(:email AS text) IS NULL OR email = CAST(:email AS text))
          AND (CAST(:user_id AS bigint) IS NULL OR user_id = CAST(:user_id AS bigint))
        ORDER BY created_at DESC
    """

    results = await database.fetch_all(
        query,
        {
            "project_id": str(project_id) if project_id is not None else None,
            "username": username or None,
            "email": email or None,
            "user_id": user_id,
        },
    )
    return results


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, project_id: uuid.UUID):
    query = """
        SELECT
            id::text AS id,
            project_id::text AS project_id,
            user_id,
            username,
            first_name,
            last_name,
            email,
            subject,
            message,
            status::text AS status,
            priority::text AS priority,
            file_path,
            created_at,
            updated_at
        FROM support_tickets
        WHERE id = CAST(:ticket_id AS uuid)
          AND project_id = CAST(:project_id AS uuid)
        LIMIT 1
    """
    ticket = await database.fetch_one(
        query,
        {
            "ticket_id": ticket_id,
            "project_id": str(project_id),
        },
    )
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket


@router.put("/{ticket_id}/status")
async def update_ticket_status(ticket_id: str, update: TicketUpdate):
    status_value = update.status.value if hasattr(update.status, "value") else str(update.status)
    update_query = """
        UPDATE support_tickets
        SET status = CAST(:status AS ticketstatus),
            updated_at = NOW()
        WHERE id = CAST(:ticket_id AS uuid)
    """
    await database.execute(update_query, {"status": status_value, "ticket_id": ticket_id})

    ticket_query = """
        SELECT
            id::text AS id,
            project_id::text AS project_id,
            user_id,
            username,
            first_name,
            last_name,
            email,
            subject,
            message,
            status::text AS status,
            priority::text AS priority,
            file_path,
            created_at,
            updated_at
        FROM support_tickets
        WHERE id = CAST(:ticket_id AS uuid)
        LIMIT 1
    """
    ticket = await database.fetch_one(ticket_query, {"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    ticket_payload = _serialize_record(ticket)
    await safe_emit_event(
        "support.ticket.updated",
        {
            "ticket_id": ticket_payload.get("id", ticket_id),
            "project_id": ticket_payload.get("project_id"),
            "user_id": ticket_payload.get("user_id"),
            "changes": {"status": status_value},
            "ticket": ticket_payload,
        },
    )

    return {"success": True, "ticket": ticket}


@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: str):
    ticket_query = """
        SELECT
            id::text AS id,
            project_id::text AS project_id,
            user_id,
            username,
            email,
            subject,
            message,
            status::text AS status,
            priority::text AS priority,
            file_path,
            created_at,
            updated_at
        FROM support_tickets
        WHERE id = CAST(:ticket_id AS uuid)
        LIMIT 1
    """
    ticket = await database.fetch_one(ticket_query, {"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    delete_query = """
        DELETE FROM support_tickets
        WHERE id = CAST(:ticket_id AS uuid)
    """
    await database.execute(delete_query, {"ticket_id": ticket_id})

    ticket_payload = _serialize_record(ticket)
    await safe_emit_event(
        "support.ticket.deleted",
        {
            "ticket_id": ticket_payload.get("id", ticket_id),
            "project_id": ticket_payload.get("project_id"),
            "user_id": ticket_payload.get("user_id"),
            "ticket": ticket_payload,
        },
    )

    return {"success": True, "deleted_ticket_id": ticket_id}
