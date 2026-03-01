# File: create-default-website.py

import os
import sys
import json
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Configuration ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
WEBSITE_CREATE_URL = f"{CYBERPANEL_URL}/websites/submitWebsiteCreation"
WEBSITE_LIST_URL = f"{CYBERPANEL_URL}/websites/listWebsites"
CREATE_PAGE_URL = f"{CYBERPANEL_URL}/websites/createWebsite"

SESSION_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json")
LOG_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/created-websites.json")

DEFAULT_PACKAGE = "admin_shared-hosting"
DEFAULT_PHP = "PHP 8.2"
DEFAULT_ADMIN_EMAIL = "mail@mail.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*"
}

def load_session_from_json():
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
            print("[+] Session is still valid.")
            return session
        else:
            print(f"[!] Session test failed: HTTP {test.status_code}")
    except Exception as e:
        print(f"[!] Error loading session: {e}")

    return None

def website_exists(session, domain):
    try:
        resp = session.get(WEBSITE_LIST_URL, headers=HEADERS, verify=False)
        if resp.status_code != 200:
            print("[!] Could not fetch website list.")
            return False
        return domain.lower() in resp.text.lower()
    except Exception as e:
        print(f"[!] Error checking website existence: {e}")
        return False

def log_creation(domain, username, response_data):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "domain": domain,
        "username": username,
        "response": response_data
    }
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        except Exception as e:
            print(f"[!] Warning: Could not read existing log file: {e}")

    logs.append(log_entry)

    try:
        with open(LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)
        print(f"[+] Logged creation info to {LOG_FILE}")
    except Exception as e:
        print(f"[!] Failed to write log file: {e}")

def create_website(session, domain, username, email):
    session.get(CREATE_PAGE_URL, headers=HEADERS, verify=False)
    csrf_token = session.cookies.get("csrftoken", "")

    if not csrf_token:
        print("[!] CSRF token not found. Cannot proceed.")
        return

    payload = {
        "package": DEFAULT_PACKAGE,
        "domainName": domain,
        "adminEmail": email,
        "apacheBackend": 0,
        "dkimCheck": 0,
        "mailDomain": 1,
        "openBasedir": 0,
        "phpSelection": DEFAULT_PHP,
        "ssl": 0,
        "websiteOwner": username
    }

    headers = HEADERS.copy()
    headers.update({
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": CREATE_PAGE_URL,
        "X-CSRFToken": csrf_token
    })

    print(f"[*] Creating website '{domain}' for user '{username}'...")
    print(f"[DEBUG] Payload:\n{json.dumps(payload, indent=2)}")

    resp = session.post(WEBSITE_CREATE_URL, json=payload, headers=headers, verify=False)

    data = {}
    try:
        data = resp.json()
        print(f"[DEBUG] Response JSON: {data}")
    except Exception as e:
        print(f"[!] Failed to parse JSON response: {e}")
        snippet = resp.text[:500]
        print(f"[!] Response snippet:\n{snippet}")

    if resp.status_code == 200 and data.get("status") == 1 and data.get("createWebSiteStatus") == 1:
        print(f"[+] Website '{domain}' created successfully.")
        log_creation(domain, username, data)
    else:
        print("[!] Website creation failed.")
        print(f"[!] Status Code: {resp.status_code}")
        print("[!] Response content:")
        print(resp.text)

def main():
    if len(sys.argv) != 4:
        print("Usage: python create-default-website.py <username> <email> <domain>")
        sys.exit(1)

    username = sys.argv[1]
    email = sys.argv[2]
    domain = sys.argv[3]

    session = load_session_from_json()
    if not session:
        print("[!] Could not load session.")
        sys.exit(1)

    if website_exists(session, domain):
        print(f"[!] Website '{domain}' already exists.")
    else:
        create_website(session, domain, username, email)

if __name__ == "__main__":
    main()
