import os
import sys
import json
import requests
import urllib3
import time
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CONFIG ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
DB_CREATE_URL = f"{CYBERPANEL_URL}/dataBases/submitDBCreation"
CREATE_PAGE_URL = f"{CYBERPANEL_URL}/dataBases/createDatabase"
LIST_SITES_URL = f"{CYBERPANEL_URL}/websites/listAllWebSites"

SESSION_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json")
LOG_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/created-databases.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*"
}

DEFAULT_DB_NAME_PREFIX = "db"
DEFAULT_DB_USER_PREFIX = "dbuser"
DEFAULT_DB_PASS_SUFFIX = "_pass123"


def load_admin_session():
    if not os.path.exists(SESSION_FILE):
        print("[!] Session file not found.")
        return None
    try:
        with open(SESSION_FILE, "r") as f:
            cookies_data = json.load(f)

        session = requests.Session()
        for name, value in cookies_data.items():
            session.cookies.set(name, value, domain="192.168.42.80")

        test = session.get(CREATE_PAGE_URL, headers=HEADERS, verify=False)
        if test.status_code == 200:
            print("[+] Admin session valid.")
            return session
        else:
            print(f"[!] Session test failed: HTTP {test.status_code}")
    except Exception as e:
        print(f"[!] Error loading session: {e}")
    return None


def log_database_creation(domain, dbname, dbuser, status, message):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "domain": domain,
        "database": dbname,
        "user": dbuser,
        "status": status,
        "message": message
    }

    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        except Exception as e:
            print(f"[!] Could not read log file: {e}")

    logs.append(log_entry)

    try:
        with open(LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)
        print(f"[+] Logged DB creation to {LOG_FILE}")
    except Exception as e:
        print(f"[!] Failed to write log file: {e}")


def wait_for_website(session, domain, timeout=60, interval=5):
    print(f"Waiting for website '{domain}' to be registered...")

    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            resp = session.get(LIST_SITES_URL, headers=HEADERS, verify=False)

            content_type = resp.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                print("[!] Received non-JSON response (likely loading page or redirect). Retrying...")
                time.sleep(interval)
                continue

            sites = resp.json().get("data", [])
            for site in sites:
                if site.get("domainName", "").lower() == domain.lower():
                    print(f"[+] Website '{domain}' found.")
                    return True

            print(f"[!] Website '{domain}' not found yet. Retrying...")
        except Exception as e:
            print(f"[!] Exception while checking websites: {e}")

        time.sleep(interval)

    print(f"[!] Timeout waiting for website '{domain}'.")
    return False


def create_database(session, domain, username):
    if not wait_for_website(session, domain):
        return False, "Website not found after waiting"

    # Refresh page to get fresh CSRF token
    session.get(CREATE_PAGE_URL, headers=HEADERS, verify=False)
    csrf_token = session.cookies.get("csrftoken", "")
    if not csrf_token:
        print("[!] CSRF token missing.")
        return False, "Missing CSRF"

    dbname = f"{DEFAULT_DB_NAME_PREFIX}_{username}".lower()
    dbuser = f"{DEFAULT_DB_USER_PREFIX}_{username}".lower()
    dbpass = f"{username}{DEFAULT_DB_PASS_SUFFIX}"

    payload = {
        "webUserName": username,
        "databaseWebsite": domain,
        "dbName": dbname,
        "dbUsername": dbuser,
        "dbPassword": dbpass
    }

    headers = HEADERS.copy()
    headers.update({
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": CREATE_PAGE_URL,
        "X-CSRFToken": csrf_token
    })

    print(f"[*] Creating DB '{dbname}' for domain '{domain}'...")

    try:
        response = session.post(DB_CREATE_URL, json=payload, headers=headers, verify=False)

        try:
            data = response.json()
        except json.JSONDecodeError:
            print("[!] Non-JSON response, trying to evaluate manually...")
            print("[!] Snippet:\n", response.text[:300])
            log_database_creation(domain, dbname, dbuser, "failed", "Non-JSON response")
            return False, "Non-JSON response"

        print(f"[DEBUG] Response JSON:\n{json.dumps(data, indent=2)}")

        if response.status_code == 200 and data.get("status") == 1 and data.get("createDBStatus") == 1:
            log_database_creation(domain, dbname, dbuser, "success", "Created successfully")
            return True, "Database created"
        else:
            err = data.get("error_message", "Unknown error")
            log_database_creation(domain, dbname, dbuser, "failed", err)
            return False, err

    except Exception as e:
        print(f"[!] Exception: {e}")
        log_database_creation(domain, dbname, dbuser, "failed", str(e))
        return False, str(e)


def main():
    if len(sys.argv) != 3:
        print("Usage: python create-default-database.py <username> <domain>")
        sys.exit(1)

    username = sys.argv[1]
    domain = sys.argv[2]

    session = load_admin_session()
    if not session:
        print("[!] Admin session failed.")
        sys.exit(1)

    success, message = create_database(session, domain, username)
    if success:
        print(f"[+] Success: {message}")
    else:
        print(f"[!] Failed: {message}")


if __name__ == "__main__":
    main()
