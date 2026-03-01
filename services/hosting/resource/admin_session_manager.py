import os
import json
import requests
import subprocess
from bs4 import BeautifulSoup

# === Constants ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
USER_LIST_URL = f"{CYBERPANEL_URL}/users/listUsers"
SESSION_FILE = "f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json"



HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*"
}

requests.packages.urllib3.disable_warnings()

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
    session = load_session_from_file()
    if session:
        try:
            test = session.get(USER_LIST_URL, headers=HEADERS, verify=False)
            if test.status_code == 200 and "List Users" in test.text:
                print("[+] Reused existing admin session.")
                return session
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
