import os
import json
import requests
import subprocess
import urllib3
import sys
from bs4 import BeautifulSoup  # For HTML error summaries

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CyberPanel Configuration ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
WEBSITE_API_URL = f"{CYBERPANEL_URL}/websites/fetchWebsitesList"

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
        "Referer": f"{CYBERPANEL_URL}/websites/websites",
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
                WEBSITE_API_URL, headers=headers, json={"page": 1, "recordsToShow": 50}, verify=False
            )
            if test.status_code == 200 and "data" in test.text:
                print("[+] Reused existing admin session.")
                return session
            else:
                print(f"[!] Session test failed. Status: {test.status_code}")
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
                WEBSITE_API_URL, headers=headers, json={"page": 1, "recordsToShow": 50}, verify=False
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
    alerts = soup.find_all("div", class_="alert")
    titles = soup.find_all(["h1", "h2", "h3", "title"])

    print("\n[!] Summary of HTML fallback page:\n")

    for title in titles:
        text = title.get_text(strip=True)
        if text:
            print(f"❌ Page title: {text}")

    for alert in alerts:
        msg = alert.get_text(strip=True)
        if msg:
            print(f"⚠️ Alert: {msg}")

    if "{$ errorMessage $" in html or "Setup Wizard" in html:
        print("\n💡 HINT: This is a **template fallback page**, not an API response.")
        print("👉 Possible causes:")
        print("   - CyberPanel backend is down or misconfigured.")
        print("   - You are not fully authenticated.")
        print("   - Setup Wizard hasn't been completed.")
        print("   - Internal PHP error on the panel.")
        print("🔧 You may want to log in manually via browser and complete setup.")

    print("\n[DEBUG] Raw fallback HTML received from server (likely frontend page instead of API).")

def list_user_websites(session, username):
    print(f"[*] Fetching websites owned by user: {username}")
    headers = get_headers(session)
    payload = {"page": 1, "recordsToShow": 100}  # Fetch up to 100 to cover most cases

    try:
        resp = session.post(WEBSITE_API_URL, headers=headers, json=payload, verify=False)
    except Exception as e:
        print(f"[!] HTTP request failed: {e}")
        return

    content_type = resp.headers.get("Content-Type", "")
    is_json = "application/json" in content_type

    if resp.status_code != 200:
        print(f"[!] API call failed with status: {resp.status_code}")
        if not is_json:
            summarize_html_error(resp.text)
        else:
            print("[DEBUG] Response:", resp.text)
        return

    try:
        data = resp.json()
    except Exception:
        print("[!] Response is not valid JSON. Trying to summarize HTML output...")
        summarize_html_error(resp.text)
        return

    websites = data.get("data", [])

    if isinstance(websites, str):
        try:
            websites = json.loads(websites)
        except Exception as e:
            print(f"[!] Failed to parse nested JSON in 'data': {e}")
            print("[DEBUG] Nested JSON string:", websites)
            return

    # Filter by username (admin field)
    filtered_websites = [w for w in websites if w.get("admin", "").lower() == username.lower()]

    if not filtered_websites:
        print(f"[!] No websites found for user '{username}'.")
        return

    print(f"\n[+] Found {len(filtered_websites)} website(s) for user '{username}':\n")
    for idx, site in enumerate(filtered_websites, start=1):
        print(f"Website #{idx}:")
        for key, value in site.items():
            print(f"   {key}: {value}")
        print("-" * 40)

def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <username>")
        sys.exit(1)

    username = sys.argv[1]

    session = load_or_auth_admin_session()
    if not session:
        print("[!] Could not obtain admin session. Aborting.")
        sys.exit(1)

    list_user_websites(session, username)

if __name__ == "__main__":
    main()
