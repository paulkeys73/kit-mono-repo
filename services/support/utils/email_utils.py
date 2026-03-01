# utils/email_utils.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
SMTP_TLS = os.getenv("SMTP_TLS", "True").lower() == "true"
SMTP_SSL = os.getenv("SMTP_SSL", "False").lower() == "true"

def send_email_notification(to_email: str, to_name: str, ticket_id: str, subject: str, message: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg["Subject"] = subject

        text = f"Ticket ID: {ticket_id}\nMessage: {message}"
        html = f"<html><body><p>Dear {to_name},</p><p>{message}</p><p>Ticket ID: {ticket_id}</p></body></html>"

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
        return True
    except Exception as e:
        print(f"[EMAIL FAILED] {e}")
        return False