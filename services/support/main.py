from fastapi import FastAPI,  HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from fastapi.responses import JSONResponse
from routes import talk_to_engineer, support_topics
import json
import os
import re
import uuid
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# ----------------------------
# Load environments variable from .env
# -----------------------------
load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "mail.paulkeys.dev")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
SMTP_TLS = os.getenv("SMTP_TLS", "True").lower() == "true"
SMTP_SSL = os.getenv("SMTP_SSL", "False").lower() == "true"

# -----------------------------
# FastAPI setup
# -----------------------------
app = FastAPI(
    title="Support System API",
    description="Professional support ticket system with email notifications and Swagger docs",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Include Router
# -----------------------------
from routes import talk_to_engineer
app.include_router(talk_to_engineer.router)

TICKETS_FILE = "data/support_tickets.json"

from routes import support_topics

app.include_router(support_topics.router)
app.include_router(talk_to_engineer.router)



# -----------------------------
# Enums & Models
# -----------------------------
class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in-progress"
    RESOLVED = "resolved"

class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class SupportTicket(BaseModel):
    name: str
    email: str
    subject: str
    message: str
    priority: Optional[TicketPriority] = TicketPriority.MEDIUM

class TicketResponse(BaseModel):
    id: str
    name: str
    email: str
    subject: str
    message: str
    priority: str
    status: str
    created_at: str
    updated_at: str

class TicketUpdate(BaseModel):
    status: TicketStatus
    admin_notes: Optional[str] = None

# -----------------------------
# Utility Functions
# -----------------------------
def load_tickets() -> list:
    if not os.path.exists(TICKETS_FILE):
        return []
    try:
        with open(TICKETS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_tickets(tickets):
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        # ensure_ascii=False preserves Unicode characters like → instead of escaping
        json.dump(tickets, f, indent=2, ensure_ascii=False, default=str)


def send_email_notification(to_email: str, to_name: str, ticket_id: str, subject: str, message: str):
    """Send HTML + plain-text email including submitted message"""
    try:
        msg = MIMEMultipart("alternative")
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Reply-To'] = SMTP_FROM

        # Plain text include the submitted message
        text = f"Ticket ID: {ticket_id[:8]}\nSubject: {subject}\nMessage: {message}\nStatus: Open"

        # HTML version
        html = f"""
        <html>
        <body style="font-family:Arial,sans-serif;line-height:1.5;color:#333;">
            <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:8px;">
                <h2 style="color:#2E86C1;">Support Ticket Created</h2>
                <p>Dear <strong>{to_name}</strong>,</p>
                <p>Thank you for contacting support. Your ticket has been created successfully.</p>
                <table style="width:100%;border-collapse:collapse;margin-top:15px;">
                    <tr>
                        <td style="border:1px solid #ddd;padding:8px;"><strong>Ticket ID</strong></td>
                        <td style="border:1px solid #ddd;padding:8px;">{ticket_id[:8]}</td>
                    </tr>
                    <tr>
                        <td style="border:1px solid #ddd;padding:8px;"><strong>Subject</strong></td>
                        <td style="border:1px solid #ddd;padding:8px;">{subject}</td>
                    </tr>
                    <tr>
                        <td style="border:1px solid #ddd;padding:8px;"><strong>Message</strong></td>
                        <td style="border:1px solid #ddd;padding:8px;">{message}</td>
                    </tr>
                    <tr>
                        <td style="border:1px solid #ddd;padding:8px;"><strong>Status</strong></td>
                        <td style="border:1px solid #ddd;padding:8px;">Open</td>
                    </tr>
                </table>
                <p style="margin-top:20px;">We will review your ticket and respond promptly.</p>
                <p>Best regards,<br/>Support Team</p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        if SMTP_SSL:
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        else:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            if SMTP_TLS:
                server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())
        server.quit()
        print(f"[EMAIL SENT] {to_email} | {subject}")
        return True

    except Exception as e:
        print(f"[EMAIL FAILED] {e}")
        return False

# -----------------------------
# API Endpoints
# -----------------------------
@app.post("/support/")
async def create_support_ticket(
    user_id: str = Form(...),
    username: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(...),
    subject: str = Form(...),
    issue: str = Form(...),
    upload: Optional[UploadFile] = File(None)
):
    tickets = load_tickets()
    ticket_id = str(uuid.uuid4())

    # Clean and normalize the message
    # 1. Convert \r\n to \n
    # 2. Remove trailing spaces
    # 3. Collapse multiple empty lines to max 1
    issue_cleaned = issue.replace("\r\n", "\n")
    issue_cleaned = "\n".join(line.rstrip() for line in issue_cleaned.splitlines())
    issue_cleaned = re.sub(r'\n\s*\n', '\n\n', issue_cleaned).strip()

    # Save file locally if uploaded
    file_path = None
    if upload:
        file_path = f"data/uploads/{ticket_id}_{upload.filename}"
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(await upload.read())

    new_ticket = {
        "id": ticket_id,
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "subject": subject,
        "message": issue_cleaned,  # use cleaned message
        "file_path": file_path,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    tickets.append(new_ticket)
    save_tickets(tickets)

    return JSONResponse({
        "success": True,
        "message": "Support ticket created successfully",
        "ticket_number": ticket_id[:8],
    })


@app.get("/tickets/", response_model=List[TicketResponse], summary="Get all tickets", description="Retrieve all support tickets.")
async def get_all_tickets():
    return load_tickets()

@app.get("/tickets/{ticket_id}", response_model=TicketResponse, summary="Get ticket by ID", description="Retrieve a single ticket by its unique ID.")
async def get_ticket(ticket_id: str):
    tickets = load_tickets()
    ticket = next((t for t in tickets if t["id"] == ticket_id), None)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@app.get("/tickets/search/{email}", summary="Search tickets by email", description="Retrieve all tickets submitted by a specific email address.")
async def get_tickets_by_email(email: str):
    tickets = load_tickets()
    user_tickets = [t for t in tickets if t["email"].lower() == email.lower()]
    return {"email": email, "tickets": user_tickets, "total_tickets": len(user_tickets)}

@app.put("/tickets/{ticket_id}/status", summary="Update ticket status", description="Update the status and optionally add admin notes for a ticket.")
async def update_ticket_status(ticket_id: str, update: TicketUpdate):
    tickets = load_tickets()
    ticket_index = next((i for i, t in enumerate(tickets) if t["id"] == ticket_id), None)
    if ticket_index is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    tickets[ticket_index]["status"] = update.status
    tickets[ticket_index]["updated_at"] = datetime.now().isoformat()
    if update.admin_notes:
        tickets[ticket_index]["admin_notes"] = update.admin_notes
    save_tickets(tickets)

    ticket = tickets[ticket_index]
    email_subject = f"Ticket Status Update - #{ticket['id'][:8]}"
    email_body = f"Ticket ID: {ticket['id'][:8]}\nSubject: {ticket['subject']}\nNew Status: {update.status.upper()}"
    if update.admin_notes:
        email_body += f"\nAdmin Notes: {update.admin_notes}"
    send_email_notification(ticket["email"], ticket["name"], ticket["id"], email_subject, ticket["message"])

    return {"success": True, "message": "Ticket status updated", "ticket": ticket}




@app.delete(
    "/tickets/{ticket_id}",
    summary="Delete a support ticket",
    description="Permanently remove a support ticket by its unique ID. This action cannot be undone.",
    response_description="Confirmation message and details of the deleted ticket",
    tags=["Tickets"],
    responses={
        200: {
            "description": "Ticket deleted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Ticket #abcd1234 deleted successfully",
                        "deleted_ticket": {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "subject": "Login issue",
                            "email": "user@example.com",
                            "status": "open"
                        }
                    }
                }
            }
        },
        404: {"description": "Ticket not found"},
    }
)
async def delete_ticket(ticket_id: str):
    """
    Delete a support ticket by its ID.

    - **ticket_id**: The unique identifier of the ticket to delete.
    - Returns a confirmation with partial ticket details.
    """
    tickets = load_tickets()
    ticket_index = next((i for i, t in enumerate(tickets) if t["id"] == ticket_id), None)
    if ticket_index is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    deleted_ticket = tickets.pop(ticket_index)
    save_tickets(tickets)

    return JSONResponse(
        content={
            "success": True,
            "message": f"Ticket #{deleted_ticket['id'][:8]} deleted successfully",
            "deleted_ticket": {
                "id": deleted_ticket["id"],
                "subject": deleted_ticket["subject"],
                "email": deleted_ticket["email"],
                "status": deleted_ticket["status"],
            },
        },
        status_code=200,
    )
    
    
    
    
# -----------------------------
# Subscribe to newsletter
# -----------------------------  

SUBSCRIBERS_FILE = "data/email_subscribers.json"

class Subscriber(BaseModel):
    email: str

def load_subscribers() -> list:
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_subscribers(subscribers):
    os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subscribers, f, indent=2, ensure_ascii=False)

@app.post("/subscribe/", summary="Subscribe to newsletter")
async def subscribe(subscriber: Subscriber):
    subscribers = load_subscribers()
    email = subscriber.email.strip().lower()
    
    if any(s["email"] == email for s in subscribers):
        return JSONResponse({"success": False, "message": "Email already subscribed"}, status_code=400)
    
    subscribers.append({"email": email, "subscribed_at": datetime.now().isoformat()})
    save_subscribers(subscribers)
    
    return {"success": True, "message": f"{email} subscribed successfully"}
  



@app.get("/health", summary="Health check", description="Check the health of the support system API.")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(), "total_tickets": len(load_tickets())}

@app.get("/", summary="Root endpoint", description="Welcome message and link to API docs.")
async def root():
    return {"message": "Support System API", "version": "1.0.0", "docs_url": "/docs"}

# ----------------------------
# Run Uvicorn Servers 
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8099)


















