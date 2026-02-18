# email_service.py
import os
from string import Template
from datetime import datetime
from typing import List
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import app.services.hooks as hooks  # reuse your logging setup

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)

# -----------------------------
# Core function to send email
# -----------------------------
def send_email(
    subject: str,
    body: str,
    to_emails: List[str],
    use_ssl: bool = False,
    use_starttls: bool = True
):
    """
    Send an email via SMTP with optional SSL or STARTTLS.
    Logs results via hooks.logger.
    """
    try:
        msg = MIMEText(body, "html")  # send as HTML
        msg['Subject'] = subject
        msg['From'] = SMTP_FROM
        msg['To'] = ", ".join(to_emails)

        if use_ssl:
            server = smtplib.SMTP_SSL(SMTP_SERVER, 465)
        else:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            if use_starttls:
                server.starttls()

        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_emails, msg.as_string())
        server.quit()

        hooks.logger.info(f"[EMAIL] Sent to {to_emails} | Subject: {subject}")

    except smtplib.SMTPAuthenticationError as e:
        hooks.logger.error(f"[EMAIL AUTH ERROR] Failed to authenticate: {e}")
        raise
    except Exception as e:
        hooks.logger.error(f"[EMAIL ERROR] Failed to send email to {to_emails}: {e}")
        raise

# -----------------------------
# Payment successful email template sender
# -----------------------------
def send_payment_success_email(
    to_email: str,
    customer_name: str,
    amount: str,
    currency: str,
    order_id: str
):
    template_path = os.path.join("email_templates", "payment_success.html")
    if not os.path.exists(template_path):
        hooks.logger.warning(f"[EMAIL TEMPLATE MISSING] {template_path} not found")
        body = f"Hi {customer_name},\nYour payment of {amount} {currency} for order {order_id} was successful."
    else:
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        tpl = Template(template_content)
        body = tpl.substitute(
            customer_name=customer_name,
            amount=amount,
            currency=currency,
            order_id=order_id,
            year=datetime.utcnow().year
        )

    send_email(
        subject="Payment Successful",
        body=body,
        to_emails=[to_email],
        use_ssl=False,
        use_starttls=True
    )

# -----------------------------
# Optional test function
# -----------------------------
def test_email():
    """
    Sends a test email to yourself using environment SMTP settings.
    """
    try:
        send_email(
            subject="SMTP Test Email",
            body="<b>This is a test email from email_service.py</b>",
            to_emails=[SMTP_USERNAME]
        )
        print("✅ Test email sent successfully")
    except Exception as e:
        print(f"❌ Test email failed: {e}")


# -----------------------------
# Run test if executed directly
# -----------------------------
if __name__ == "__main__":
    test_email()
