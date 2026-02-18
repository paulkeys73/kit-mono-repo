from fastapi import APIRouter, HTTPException, Form
from pydantic import BaseModel
from datetime import datetime
import os
import json
import logging

# -----------------------------------
# Setup
# -----------------------------------
CONVERSATIONS_FILE = "data/conversations.json"

router = APIRouter(
    prefix="/engineer",
    tags=["TalkToEngineer"]
)

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TalkToEngineer")

# -----------------------------------
# Models
# -----------------------------------
class ConversationMessage(BaseModel):
    sender: str  # "user" or "engineer"
    message: str
    timestamp: str


# -----------------------------------
# Utility Functions
# -----------------------------------
def load_conversations() -> list:
    """Load conversation data safely, fixing missing keys when possible."""
    if not os.path.exists(CONVERSATIONS_FILE):
        return []

    try:
        with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.warning("Invalid data format in conversations.json, resetting.")
            return []
        return data
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning(f"⚠️ Error loading conversations: {e}")
        return []


def save_conversations(conversations: list):
    """Persist conversations safely to disk."""
    os.makedirs(os.path.dirname(CONVERSATIONS_FILE), exist_ok=True)
    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(conversations, f, indent=2, default=str, ensure_ascii=False)


def append_message(ticket_id: str, sender: str, message: str) -> ConversationMessage:
    """Append a new message to a ticket conversation."""
    conversations = load_conversations()

    convo = next((c for c in conversations if c.get("ticket_id") == ticket_id), None)
    new_message = {
        "sender": sender,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }

    if convo:
        convo["conversation"].append(new_message)
    else:
        convo = {
            "ticket_id": ticket_id,
            "conversation": [new_message]
        }
        conversations.append(convo)

    save_conversations(conversations)
    return ConversationMessage(**new_message)


# -----------------------------------
# API Endpoints
# -----------------------------------
@router.post("/talk", summary="Send message to engineer / user")
async def talk_to_engineer(
    ticket_id: str = Form(..., description="Ticket ID"),
    sender: str = Form(..., description="Message sender: 'user' or 'engineer'"),
    message: str = Form(..., description="Message content")
):
    if sender not in ["user", "engineer"]:
        raise HTTPException(status_code=400, detail="Sender must be 'user' or 'engineer'")

    msg = append_message(ticket_id, sender, message)
    logger.info(f"💬 Message added to {ticket_id} by {sender}")
    return {"success": True, "data": msg.dict()}


@router.get("/talk/{ticket_id}", summary="Get conversation for a ticket")
async def get_conversation(ticket_id: str):
    conversations = load_conversations()
    convo = next((c for c in conversations if c.get("ticket_id") == ticket_id), None)

    if not convo:
        logger.info(f"🆕 New conversation entry created for ticket {ticket_id}")
        new_convo = {"ticket_id": ticket_id, "conversation": []}
        conversations.append(new_convo)
        save_conversations(conversations)
        return {"ticket_id": ticket_id, "conversation": []}

    return {"ticket_id": ticket_id, "conversation": convo["conversation"]}





@router.get("/tickets", summary="List all support tickets")
async def list_tickets():
    """
    Return a summary of all support tickets with last message preview.
    """
    tickets_file = "data/support_tickets.json"
    conversations_file = "data/conversations.json"

    tickets = []
    if os.path.exists(tickets_file):
        try:
            with open(tickets_file, "r", encoding="utf-8") as f:
                tickets = json.load(f)
        except json.JSONDecodeError:
            logger.warning("⚠️ support_tickets.json is invalid, returning empty list")
            tickets = []

    # Mergez in latest conversation data (optional)y
    conversations = load_conversations()
    for t in tickets:
        convo = next((c for c in conversations if c["ticket_id"] == t["ticket_id"]), None)
        if convo and convo["conversation"]:
            t["last_message"] = convo["conversation"][-1]["message"]
            t["last_updated"] = convo["conversation"][-1]["timestamp"]
        else:
            t["last_message"] = None
            t["last_updated"] = None

    tickets.sort(key=lambda x: x["last_updated"] or "", reverse=True)
    return {"tickets": tickets}

