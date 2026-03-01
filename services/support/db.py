import os
import uuid
from dotenv import load_dotenv
from enum import Enum as PyEnum

import sqlalchemy
from databases import Database
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Text,
    TIMESTAMP,
    Enum,
    BigInteger,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

# -----------------------------
# Environment
# -----------------------------
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

# Async database (used by FastAPI routes)
database = Database(DATABASE_URL)

# Metadata
metadata = MetaData()

# Sync engine (used ONLY for create_all)
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
engine = sqlalchemy.create_engine(SYNC_DATABASE_URL)


def ensure_schema_compatibility():
    """
    Apply minimal non-destructive schema fixes for legacy databases.
    create_all() does not alter existing tables, so we patch missing columns.
    """
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS project_id UUID"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_support_tickets_project_id ON support_tickets (project_id)"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id UUID"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_project_id ON conversations (project_id)"
            )
        )

# -----------------------------
# Enums
# -----------------------------
class TicketStatus(PyEnum):
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(PyEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# -----------------------------
# Tables
# -----------------------------
support_tickets = Table(
    "support_tickets",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("project_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("user_id", BigInteger, nullable=False),
    Column("username", String(150), nullable=False),
    Column("first_name", String(150)),
    Column("last_name", String(150)),
    Column("email", String(255), nullable=False, index=True),
    Column("subject", String(255), nullable=False),
    Column("message", Text, nullable=False),
    Column("file_path", Text),
    Column("status", Enum(TicketStatus), nullable=False, default=TicketStatus.OPEN),
    Column("priority", Enum(TicketPriority), nullable=False, default=TicketPriority.NORMAL),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("ticket_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("project_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("sender_type", String(20), nullable=False),
    Column("sender_id", BigInteger),
    Column("message", Text, nullable=False),
    Column("file_path", Text),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
)

subscribers = Table(
    "subscribers",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("project_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("email", String(255), nullable=False, index=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
)
