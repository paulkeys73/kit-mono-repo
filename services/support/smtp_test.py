import smtplib
import os
from email.mime.text import MIMEText

# Load from .env needed
from dotenv import load_dotenv
load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")

TO_EMAIL = SMTP_USERNAME  # send test to yourself

subject = "SMTP Test Email"
body = "This is a test email from Python to verify SMTP configuration."

# Test STARTTLS (comonly port 587)
try:
    print(f"Testing {SMTP_SERVER}:{SMTP_PORT} with STARTTLS...")
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.ehlo()
    server.starttls()
    server.login(SMTP_USERNAME, SMTP_PASSWORD)
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM
    msg['To'] = TO_EMAIL
    server.sendmail(SMTP_FROM, TO_EMAIL, msg.as_string())
    server.quit()
    print("✅ STARTTLS test succeeded")
except smtplib.SMTPAuthenticationError as e:
    print(f"❌ STARTTLS authentication failed: {e}")
except Exception as e:
    print(f"❌ STARTTLS connection failed: {e}")

# Test SSL (commonly port 465)
try:
    print(f"\nTesting {SMTP_SERVER}:465 with SSL...")
    server = smtplib.SMTP_SSL(SMTP_SERVER, 465)
    server.login(SMTP_USERNAME, SMTP_PASSWORD)
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM
    msg['To'] = TO_EMAIL
    server.sendmail(SMTP_FROM, TO_EMAIL, msg.as_string())
    server.quit()
    print("✅ SSL test succeeded")
except smtplib.SMTPAuthenticationError as e:
    print(f"❌ SSL authentication failed: {e}")
except Exception as e:
    print(f"❌ SSL connection failed: {e}")

# Test plain (commonly port 25)
try:
    print(f"\nTesting {SMTP_SERVER}:25 without encryption...")
    server = smtplib.SMTP(SMTP_SERVER, 25)
    server.login(SMTP_USERNAME, SMTP_PASSWORD)
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM
    msg['To'] = TO_EMAIL
    server.sendmail(SMTP_FROM, TO_EMAIL, msg.as_string())
    server.quit()
    print("✅ Plain port 25 test succeeded")
except smtplib.SMTPAuthenticationError as e:
    print(f"❌ Plain port 25 authentication failed: {e}")
except Exception as e:
    print(f"❌ Plain port 25 connection failed: {e}")
