from fastapi import APIRouter, HTTPException, Request
from typing import List, Optional
import uuid
import re

from db import database
from models import TicketWithTopicsResponse
from sqlalchemy import text

router = APIRouter()


@router.get("/tickets", response_model=List[TicketWithTopicsResponse])
async def get_user_tickets(
    request: Request,
    user_id: Optional[int] = None,
    project_id: Optional[uuid.UUID] = None,
):
    """
    Return tickets only for the authenticated/requested user.
    User identity can come from x-user-id header or user_id query param.
    If both are provided, they must match.
    """
    header_user_id = request.headers.get("x-user-id") or request.headers.get("x-auth-user-id")

    resolved_user_id = user_id

    if header_user_id is not None:
        try:
            header_user_id_int = int(header_user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid x-user-id header") from exc

        if resolved_user_id is None:
            resolved_user_id = header_user_id_int
        elif resolved_user_id != header_user_id_int:
            raise HTTPException(status_code=403, detail="User mismatch")

    if resolved_user_id is None:
        raise HTTPException(status_code=400, detail="user_id is required")

    query = text(
        """
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
            updated_at,
            to_tsvector(
                'english',
                coalesce(subject, '') || ' ' || coalesce(message, '')
            )::text AS topics
        FROM support_tickets
        WHERE user_id = :user_id
          AND (CAST(:project_id AS uuid) IS NULL OR project_id = CAST(:project_id AS uuid))
        ORDER BY created_at DESC
        """
    )

    rows = await database.fetch_all(
        query,
        {
            "user_id": resolved_user_id,
            "project_id": str(project_id) if project_id is not None else None,
        },
    )

    results = []
    for row in rows:
        item = dict(row)
        topics = item.get("topics") or ""
        item["topic_terms"] = re.findall(r"'([^']+)':", topics)
        results.append(item)

    return results
