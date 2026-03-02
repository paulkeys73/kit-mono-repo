import os
import sys
import json
import requests
import urllib3
from urllib.parse import quote
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CYBERPANEL_URL = "https://192.168.42.80:8090"
SESSION_FILE = os.path.abspath(
    "f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json"
)
CHILD_DOMAIN_API_URL = f"{CYBERPANEL_URL}/websites/listChildDomains"

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
        print("[!] Session file not found.")
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
        print(f"[!] Failed to load session: {e}")
        return None

def fetch_user_domains(session, username):
    headers = get_headers(session)
    payload = {"domain": username}
    try:
        resp = session.post(CHILD_DOMAIN_API_URL, headers=headers, json=payload, verify=False)
        if resp.status_code != 200:
            print(f"[!] Failed to fetch child domains. Status: {resp.status_code}")
            return []
        data = resp.json()
        domains = json.loads(data.get("data", "[]")) if isinstance(data.get("data"), str) else data.get("data")
        return domains
    except Exception as e:
        print(f"[!] Error fetching domains: {e}")
        return []

def fetch_domain_resource_page(session, master_domain, child_domain):
    url = f"{CYBERPANEL_URL}/websites/{quote(master_domain)}/{quote(child_domain)}"
    try:
        resp = session.get(url, verify=False)
        if resp.status_code != 200:
            print(f"[!] Failed to fetch page for {child_domain}. Status: {resp.status_code}")
            return None
        return resp.text
    except Exception as e:
        print(f"[!] Error fetching domain page: {e}")
        return None

def summarize_resource_page(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title else "No title found"
    print(f"📝 Page Title: {title}")

    # Example: grab load avg if present
    load_box = soup.find("div", id="header-nav-right")
    if load_box:
        print("✅ Found top nav bar. Page loaded successfully.")

def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <cp_username>")
        sys.exit(1)

    username = sys.argv[1]
    session = load_session_from_file()
    if not session:
        print("[!] Could not obtain session.")
        sys.exit(1)

    print(f"[*] Fetching child domains for user: {username}")
    domains = fetch_user_domains(session, username)

    if not domains:
        print("[!] No domains found for this user.")
        return

    print(f"\n[+] Found {len(domains)} domain(s):\n")

    for idx, d in enumerate(domains, 1):
        child = d["domain"]
        parent = d["masterDomain"]
        print(f"Child Domain #{idx}: {child} (under {parent})")

        html = fetch_domain_resource_page(session, parent, child)
        if html:
            summarize_resource_page(html)

        print("-" * 40)

if __name__ == "__main__":
    main()
