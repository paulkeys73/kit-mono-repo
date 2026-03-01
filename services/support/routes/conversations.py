# routes/conversations.py
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from db import conversations, database, support_tickets
from messaging.rabbitmq import safe_emit_event
from models import ConversationCreate

router = APIRouter()


@router.get("/ticket/{ticket_id}")
async def get_conversations(ticket_id: str, project_id: str):
    ticket = await database.fetch_one(
        support_tickets.select().where(
            (support_tickets.c.id == ticket_id)
            & (support_tickets.c.project_id == project_id)
        )
    )
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    convs = await database.fetch_all(
        conversations.select().where(
            (conversations.c.ticket_id == ticket_id)
            & (conversations.c.project_id == project_id)
        )
    )
    return convs


@router.post("/ticket/{ticket_id}")
async def add_conversation(ticket_id: str, conv: ConversationCreate):
    ticket = await database.fetch_one(
        support_tickets.select().where(
            (support_tickets.c.id == ticket_id)
            & (support_tickets.c.project_id == conv.project_id)
        )
    )
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    conv_id = uuid4()
    query = conversations.insert().values(
        id=conv_id,
        ticket_id=ticket_id,
        project_id=conv.project_id,
        sender_type=conv.sender_type,
        sender_id=conv.sender_id,
        message=conv.message,
        file_path=conv.file_path,
    )
    await database.execute(query)

    await safe_emit_event(
        "support.conversation.created",
        {
            "conversation_id": str(conv_id),
            "ticket_id": ticket_id,
            "project_id": str(conv.project_id),
            "sender_type": conv.sender_type,
            "sender_id": conv.sender_id,
            "message": conv.message,
            "file_path": conv.file_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {"id": str(conv_id)}
