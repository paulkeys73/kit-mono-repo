import sys
import os
import json
import requests
import urllib3

# === Configuration ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
SESSION_FILE = os.path.abspath(
    "f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json"
)
SUBMIT_DOMAIN_CREATION_URL = f"{CYBERPANEL_URL}/websites/submitDomainCreation"

# === Disable SSL warnings ===
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Force UTF-8 for terminal output ===
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# === Load admin session ===
def load_session():
    if not os.path.exists(SESSION_FILE):
        print("[!] Session file not found at:", SESSION_FILE)
        return None

    try:
        with open(SESSION_FILE, "r") as f:
            cookies = json.load(f)
        session = requests.Session()
        jar = requests.cookies.RequestsCookieJar()
        for k, v in cookies.items():
            jar.set(k, v)
        session.cookies = jar
        print("[+] Session loaded successfully.")
        return session
    except Exception as e:
        print(f"[!] Failed to load session: {e}")
        return None

# === Add subdomain ===
def add_subdomain(session, parent_domain, subdomain, package="Default", owner=None):
    csrf_token = session.cookies.get("csrftoken", "")
    if not csrf_token:
        print("[!] CSRF token not found in session cookies. Are you logged in?")
        return False

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": f"{CYBERPANEL_URL}/websites/CreateNewDomain",
        "x-csrftoken": csrf_token,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Origin": CYBERPANEL_URL,
    }

    full_domain = f"{subdomain}.{parent_domain}"

    payload = {
        "domainName": full_domain,
        "masterDomain": parent_domain,
        "phpSelection": "PHP 8.2",
        "ssl": 1,
        "path": "",
        "apacheBackend": 0,
        "dkimCheck": 0,
        "openBasedir": 0,
        "autoRenew": 0,
        "packageName": package,
        "owner": owner if owner else "",
        "isSubdomain": 1
    }

    print(f"[*] Attempting to add subdomain: {full_domain}")
    try:
        resp = session.post(
            SUBMIT_DOMAIN_CREATION_URL,
            headers=headers,
            json=payload,
            verify=False
        )

        print(f"[DEBUG] Response URL: {resp.url}")
        print(f"[DEBUG] Status Code: {resp.status_code}")
        print(f"[DEBUG] Headers: {resp.headers.get('content-type')}")

        if resp.status_code == 200:
            try:
                resp_json = resp.json()
                status = resp_json.get("status")
                create_status = resp_json.get("createWebSiteStatus")
                error_message = resp_json.get("error_message")

                if status == 1 and create_status == 1:
                    print(f"[✅] Subdomain '{full_domain}' added successfully!")
                    return True
                else:
                    print(f"[❌] Failed to add subdomain '{full_domain}': {error_message or resp.text}")
                    return False
            except ValueError:
                print(f"[ℹ️] Non-JSON response received:\n{resp.text.strip()[:200]}...")
                return False
        else:
            print(f"[❌] HTTP {resp.status_code} error when adding subdomain.")
            print(f"[ℹ️] Response content: {resp.text.strip()[:200]}...")
            return False

    except requests.exceptions.RequestException as e:
        print(f"[!] Request error: {e}")
        return False
    except Exception as e:
        print(f"[!] Unexpected error: {e}")
        return False

# === Entry point ===
def main():
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <parent_domain> <subdomain> [package] [owner]")
        print("Example: python add-subdomain.py example.com blog Default user01")
        sys.exit(1)

    parent_domain = sys.argv[1]
    subdomain = sys.argv[2]
    package = sys.argv[3] if len(sys.argv) > 3 else "Default"
    owner = sys.argv[4] if len(sys.argv) > 4 else None

    session = load_session()
    if not session:
        print("[!] Could not load session.")
        sys.exit(1)

    success = add_subdomain(session, parent_domain, subdomain, package, owner)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
