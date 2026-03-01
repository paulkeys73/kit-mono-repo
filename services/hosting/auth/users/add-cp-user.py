import sys
import requests
import os
import subprocess
import urllib3
import re
from bs4 import BeautifulSoup
from datetime import datetime
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CyberPanel Configuration ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
USER_CREATE_URL = f"{CYBERPANEL_URL}/users/submitUserCreation"
USER_LIST_URL = f"{CYBERPANEL_URL}/users/listUsers"

# === File Paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DIR = os.path.join(BASE_DIR, "users-db")
SESSION_FILE = os.path.join(USER_DIR, "cp_admin_session.json")
LOG_FILE = os.path.join(USER_DIR, "user_creation_log.json")

# === Defaults ===
DEFAULT_PACKAGE = "admin_shared-hosting"
DEFAULT_ROLE = "user"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*"
}


def ensure_user_dir():
    if not os.path.exists(USER_DIR):
        os.makedirs(USER_DIR)
        print(f"[+] Created missing 'users-db' directory at {USER_DIR}")


def log_user_event(username, email, domain, status, message):
    ensure_user_dir()
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "username": username,
        "email": email,
        "domain": domain,
        "package": DEFAULT_PACKAGE,
        "status": status,
        "message": message
    }

    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        else:
            logs = []
    except (json.JSONDecodeError, FileNotFoundError):
        logs = []

    is_duplicate = any(
        log["username"] == username and
        log["domain"] == domain and
        log["status"] == status and
        log["message"] == message
        for log in logs
    )
    if is_duplicate:
        print(f"[!] Duplicate log entry found. Skipping log update for user '{username}'.")
        return

    logs.append(entry)

    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

    print(f"[+] Log updated for user '{username}' - status: {status}")


def save_session_to_file(session):
    ensure_user_dir()
    cookies = session.cookies.get_dict()
    with open(SESSION_FILE, "w") as f:
        json.dump(cookies, f)


def load_session_from_file():
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r") as f:
            cookies = json.load(f)
        session = requests.Session()
        jar = requests.cookies.RequestsCookieJar()
        for k, v in cookies.items():
            jar.set(k, v)
        session.cookies = jar
        return session
    except Exception as e:
        print(f"[!] Failed to load session cookies: {e}")
        return None


def load_or_auth_admin_session():
    print(f"[*] Looking for session at: {SESSION_FILE}")
    session = load_session_from_file()
    if session:
        try:
            test = session.get(USER_LIST_URL, headers=HEADERS, verify=False)
            if test.status_code == 200 and "List Users" in test.text:
                print("[+] Reused existing admin session.")
                return session
            else:
                print("[!] Session test failed. Status:", test.status_code)
        except Exception as e:
            print(f"[!] Session test error: {e}")

    print("[*] No valid session. Triggering admin-login-cp.py...")

    result = subprocess.run(
        ["python3", "f:/my-servers/services/backend/django/hosting/auth/admin-login-cp.py"],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.returncode != 0:
        print("[!] Admin login script failed.")
        print(result.stderr)
        return None

    session = load_session_from_file()
    if session:
        try:
            test = session.get(USER_LIST_URL, headers=HEADERS, verify=False)
            if test.status_code == 200 and "List Users" in test.text:
                print("[+] New admin session loaded.")
                return session
        except Exception as e:
            print(f"[!] Failed to validate new session: {e}")

    print("[!] Could not obtain session.")
    return None


def user_exists(session, username):
    resp = session.get(USER_LIST_URL, headers=HEADERS, verify=False)
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        if cols and cols[0].get_text(strip=True).lower() == username.lower():
            return True
    return False


def create_user(session, username, email, domain, password="admin123Pw"):
    if user_exists(session, username):
        msg = f"User '{username}' already exists."
        print(f"[!] {msg}")
        log_user_event(username, email, domain, "skipped", msg)
        return False

    csrf_token = session.cookies.get("csrftoken", "")
    if not csrf_token:
        msg = "No CSRF token found in session."
        print(f"[!] {msg}")
        log_user_event(username, email, domain, "failed", msg)
        return False

    raw_first = re.sub(r'[^a-zA-Z]', '', username).capitalize()
    first_name = raw_first if len(raw_first) > 2 else "Client"

    payload = {
        "firstName": first_name,
        "lastName": "User",
        "email": email,
        "userName": username,
        "package": DEFAULT_PACKAGE,
        "selectedACL": DEFAULT_ROLE,
        "password": password,
        "securityLevel": "HIGH",
        "websitesLimit": 0
    }

    headers = HEADERS.copy()
    headers.update({
        "Content-Type": "application/json",
        "Referer": f"{CYBERPANEL_URL}/users/createUser",
        "X-CSRFToken": csrf_token
    })

    resp = session.post(USER_CREATE_URL, json=payload, headers=headers, verify=False)

    print(f"[DEBUG] POST {USER_CREATE_URL} status: {resp.status_code}")
    print(f"[DEBUG] Response: {resp.text}")

    if resp.status_code == 200:
        try:
            data = resp.json()
            if data.get("createStatus") == 1:
                msg = f"User '{username}' created successfully."
                print(f"[+] {msg}")
                log_user_event(username, email, domain, "success", msg)
                return True
            else:
                msg = data.get("error_message", "Unknown error")
                print(f"[!] Failed to create user: {msg}")
                log_user_event(username, email, domain, "failed", msg)
        except Exception as e:
            msg = f"Failed to parse JSON: {e}"
            print(f"[!] {msg}")
            log_user_event(username, email, domain, "failed", msg)
    else:
        msg = f"HTTP error {resp.status_code}"
        print(f"[!] {msg}")
        log_user_event(username, email, domain, "failed", msg)

    return False


def main(username, email, domain):
    session = load_or_auth_admin_session()
    if not session:
        print("[!] Could not obtain admin session. Aborting.")
        log_user_event(username, email, domain, "failed", "Admin session error")
        sys.exit(1)

    create_user(session, username, email, domain)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python add-cp-user.py <username> <email> <domain>")
        sys.exit(1)

    main(sys.argv[1], sys.argv[2], sys.argv[3])
