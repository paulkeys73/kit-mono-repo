import os
import json
import requests
import subprocess
import urllib3
import sys
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CyberPanel Configuration ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
CHILD_DOMAIN_API_URL = f"{CYBERPANEL_URL}/websites/fetchChildDomainsMain"  # ✅ Actual API for child domains

# === Session File Location ===
SESSION_FILE = os.path.abspath(
    "f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json"
)

def get_headers(session):
    csrf_token = session.cookies.get("csrftoken", "")
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Referer": f"{CYBERPANEL_URL}/websites/listChildDomains",
        "x-csrftoken": csrf_token,
    }

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
        headers = get_headers(session)
        try:
            test = session.post(
                CHILD_DOMAIN_API_URL,
                headers=headers,
                json={"page": 1, "recordsToShow": 10},
                verify=False,
            )
            if test.status_code == 200 and "data" in test.text:
                print("[+] Reused existing admin session.")
                return session
        except Exception as e:
            print(f"[!] Session test error: {e}")

    print("[*] No valid session. Triggering admin-login-cp.py...")

    result = subprocess.run(
        ["python3", "f:/my-servers/services/backend/django/hosting/auth/admin-login-cp.py"],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.returncode != 0:
        print("[!] Admin login script failed.")
        print(result.stderr)
        return None

    session = load_session_from_file()
    if session:
        headers = get_headers(session)
        try:
            test = session.post(
                CHILD_DOMAIN_API_URL,
                headers=headers,
                json={"page": 1, "recordsToShow": 10},
                verify=False,
            )
            if test.status_code == 200 and "data" in test.text:
                print("[+] New admin session loaded.")
                return session
        except Exception as e:
            print(f"[!] Failed to validate new session: {e}")

    print("[!] Could not obtain valid session.")
    return None

def summarize_html_error(html):
    soup = BeautifulSoup(html, "html.parser")
    titles = soup.find_all(["h1", "h2", "h3", "title"])
    alerts = soup.find_all("div", class_="alert")

    for title in titles:
        text = title.get_text(strip=True)
        if text:
            print(f"❌ Page title: {text}")
    for alert in alerts:
        msg = alert.get_text(strip=True)
        if msg:
            print(f"⚠️ Alert: {msg}")
    print("[!] Likely frontend HTML fallback instead of API response.")

def list_child_domains_by_user(session, user):
    print(f"[*] Fetching child domains for user: {user}")
    headers = get_headers(session)
    payload = {"page": 1, "recordsToShow": 100}  # 🧹 Pull as many as possible

    try:
        resp = session.post(CHILD_DOMAIN_API_URL, headers=headers, json=payload, verify=False)
    except Exception as e:
        print(f"[!] HTTP request failed: {e}")
        return

    if resp.status_code != 200:
        print(f"[!] API call failed with status: {resp.status_code}")
        if "html" in resp.headers.get("Content-Type", ""):
            summarize_html_error(resp.text)
        else:
            print("[DEBUG] Response:", resp.text)
        return

    try:
        data = resp.json()
        child_domains = data.get("data", [])
    except Exception as e:
        print(f"[!] Failed to decode JSON: {e}")
        return

    if isinstance(child_domains, str):
        try:
            child_domains = json.loads(child_domains)
        except Exception as e:
            print(f"[!] Could not parse nested JSON: {e}")
            return

    filtered = [d for d in child_domains if d.get("admin") == user]

    if not filtered:
        print(f"[!] No child domains found for user '{user}'.")
        return

    print(f"\n[+] Found {len(filtered)} child domain(s) for user '{user}':\n")
    for idx, domain_info in enumerate(filtered, start=1):
        print(f"Child Domain #{idx}:")
        for key, value in domain_info.items():
            print(f"   {key}: {value}")
        print("-" * 40)

def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <username>")
        sys.exit(1)

    user = sys.argv[1]
    session = load_or_auth_admin_session()
    if not session:
        print("[!] Could not obtain admin session. Aborting.")
        sys.exit(1)

    list_child_domains_by_user(session, user)

if __name__ == "__main__":
    main()
