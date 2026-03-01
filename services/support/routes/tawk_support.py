# routes/tawk_support.py
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter

from db import database, support_tickets
from messaging.rabbitmq import safe_emit_event

router = APIRouter()


@router.post("/ticket-from-tawk")
async def ticket_from_tawk(data: dict):
    """
    Create a support ticket from Tawk.to chat visitor info.
    """
    ticket_id = uuid4()
    project_id = uuid4()  # fallback if no project_id passed

    query = support_tickets.insert().values(
        id=ticket_id,
        project_id=project_id,
        user_id=0,
        username=data.get("name") or "Tawk Visitor",
        first_name=None,
        last_name=None,
        email=data.get("email") or "",
        subject=f"Live chat started at {datetime.now(timezone.utc).isoformat()}",
        message=f"Visitor info: {data}",
        priority="normal",
        status="open",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await database.execute(query)

    await safe_emit_event(
        "support.ticket.created",
        {
            "ticket_id": str(ticket_id),
            "project_id": str(project_id),
            "user_id": 0,
            "status": "open",
            "ticket": {
                "id": str(ticket_id),
                "project_id": str(project_id),
                "user_id": 0,
                "username": data.get("name") or "Tawk Visitor",
                "email": data.get("email") or "",
                "subject": f"Live chat started at {datetime.now(timezone.utc).isoformat()}",
                "message": f"Visitor info: {data}",
                "status": "open",
                "priority": "normal",
            },
            "source": "tawk",
        },
    )

    return {"success": True, "ticket_id": str(ticket_id)}
