# models.py

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


# -----------------------------
# API Enums (must match DB)
# -----------------------------
class TicketStatus(str, Enum):
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# -----------------------------
# Ticket Models
# -----------------------------
class SupportTicketCreate(BaseModel):
    project_id: str
    user_id: int
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: EmailStr
    subject: str
    message: str
    priority: Optional[TicketPriority] = TicketPriority.NORMAL


class TicketResponse(BaseModel):
    id: str
    project_id: str
    user_id: int
    username: str
    first_name: Optional[str]
    last_name: Optional[str]
    email: EmailStr
    subject: str
    message: str
    status: TicketStatus
    priority: TicketPriority
    file_path: Optional[str]
    created_at: datetime
    updated_at: datetime


class TicketWithTopicsResponse(TicketResponse):
    topics: Optional[str] = None
    topic_terms: List[str] = Field(default_factory=list)


class TicketUpdate(BaseModel):
    status: TicketStatus
    admin_notes: Optional[str] = None


# -----------------------------
# Conversations
# -----------------------------
class ConversationCreate(BaseModel):
    project_id: str
    sender_type: str  # "user" | "admin"
    sender_id: Optional[int] = None
    message: str
    file_path: Optional[str] = None


# -----------------------------
# Subscribers
# -----------------------------
class SubscriberCreate(BaseModel):
    project_id: str
    email: EmailStr
