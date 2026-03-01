import os
import sys
import json
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Configuration ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
FETCH_WEBSITES_URL = f"{CYBERPANEL_URL}/websites/fetchWebsitesList"
RESOURCE_BASE_URL = f"{CYBERPANEL_URL}/websites/"
SESSION_FILE = os.path.abspath(
    "f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json"
)
RESOURCE_OUTPUT_DIR = "f:/my-servers/services/backend/django/hosting/auth/users/users-db/website-resources"

def get_headers(session):
    csrf = session.cookies.get("csrftoken", "")
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": f"{CYBERPANEL_URL}/websites/websites",
        "x-csrftoken": csrf,
    }

def load_session():
    if not os.path.exists(SESSION_FILE):
        print("[!] Session file not found.")
        return None
    try:
        with open(SESSION_FILE, "r") as f:
            cookies = json.load(f)
        session = requests.Session()
        for name, value in cookies.items():
            session.cookies.set(name, value, domain="192.168.42.80")
        return session
    except Exception as e:
        print(f"[!] Error loading session: {e}")
        return None

def fetch_websites(session):
    headers = get_headers(session)
    payload = {"page": 1, "recordsToShow": 50}
    try:
        resp = session.post(FETCH_WEBSITES_URL, headers=headers, json=payload, verify=False)
        if resp.status_code != 200:
            print(f"[!] Failed to fetch websites. HTTP {resp.status_code}")
            return []
        data = resp.json()
        websites = data.get("data", [])
        if isinstance(websites, str):
            websites = json.loads(websites)
        return websites
    except Exception as e:
        print(f"[!] Error fetching website list: {e}")
        return []

def website_exists(websites, domain):
    print(f"[i] Checking if '{domain}' exists in website list...")
    for site in websites:
        if site.get("domain", "").strip().lower() == domain.lower():
            return True
    return False

def fetch_website_resources(session, domain, username):
    full_url = f"{RESOURCE_BASE_URL}{domain}"
    try:
        print(f"🌐 Fetching resources from: {full_url}")
        response = session.get(full_url, headers=get_headers(session), verify=False)

        if response.status_code != 200:
            print(f"❌ Failed to fetch resources. HTTP {response.status_code}")
            return None

        print("✅ Website resources fetched successfully.\n")
        soup = BeautifulSoup(response.text, "html.parser")

        data = {
            "scripts": [script["src"] for script in soup.find_all("script", src=True)],
            "stylesheets": [link["href"] for link in soup.find_all("link", rel="stylesheet")],
            "images": [img["src"] for img in soup.find_all("img", src=True)],
            "links": [
                a["href"]
                for a in soup.find_all("a", href=True)
                if not a["href"].startswith("#") and not a["href"].lower().startswith("javascript")
            ]
        }

        output_path = os.path.join(RESOURCE_OUTPUT_DIR, f"{username}.resources.json")
        os.makedirs(RESOURCE_OUTPUT_DIR, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"\n📁 Resources saved to: {output_path}")
        return data

    except requests.RequestException as e:
        print(f"🔥 Error fetching website resources: {e}")
        return None

def main():
    if len(sys.argv) != 2:
        print("Usage: python website-resources.py <username>")
        sys.exit(1)

    username = sys.argv[1].strip().lower()
    if not username.isalnum():
        print("[!] Invalid username. Only alphanumeric characters allowed.")
        sys.exit(1)

    domain = f"{username}.dev.local"
    session = load_session()
    if not session:
        print("[!] Could not load session.")
        sys.exit(1)

    websites = fetch_websites(session)
    if not websites:
        print("[!] No websites returned from API.")
        sys.exit(1)

    if website_exists(websites, domain):
        print(f"[+] Website '{domain}' exists.")
        fetch_website_resources(session, domain, username)
    else:
        print(f"[❌] Website '{domain}' does not exist.")
        sys.exit(1)

if __name__ == "__main__":
    main()
