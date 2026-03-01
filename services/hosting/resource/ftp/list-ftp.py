import os
import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CYBERPANEL_URL = "https://192.168.42.80:8090"
SESSION_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json")
WEBSITE_INFO_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/created-websites.json")

FTP_API_URL = f"{CYBERPANEL_URL}/ftp/getAllFTPAccounts"

def load_target_domain():
    if not os.path.exists(WEBSITE_INFO_FILE):
        print(f"[!] Website info file not found at {WEBSITE_INFO_FILE}")
        return None

    try:
        with open(WEBSITE_INFO_FILE, "r") as f:
            websites = json.load(f)
        if not websites:
            print("[!] Website info JSON is empty.")
            return None

        domain = websites[0].get("domain")
        if not domain:
            print("[!] 'domain' key missing in website info JSON.")
            return None

        return domain

    except Exception as e:
        print(f"[!] Failed to load website info JSON: {e}")
        return None

def load_session():
    if not os.path.exists(SESSION_FILE):
        print("[!] Session file not found.")
        return None, None

    try:
        with open(SESSION_FILE, "r") as f:
            cookie_dict = json.load(f)

        session = requests.Session()
        session.cookies.update(cookie_dict)

        csrf_token = cookie_dict.get("csrftoken")
        if not csrf_token:
            print("[!] CSRF token missing in cookies. Cannot proceed.")
            return None, None

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Referer": CYBERPANEL_URL + "/ftp/listFTPAccounts"
        }

        return session, headers

    except Exception as e:
        print(f"[!] Failed to load session: {e}")
        return None, None

def list_ftp_accounts(session, headers, target_domain):
    print(f"[*] Fetching FTP accounts for domain '{target_domain}' ...")

    payload = {"selectedDomain": target_domain}
    resp = session.post(FTP_API_URL, json=payload, headers=headers, verify=False)

    if resp.status_code != 200:
        print(f"[!] API call failed with status: {resp.status_code}")
        print("[DEBUG] Response:", resp.text)
        return

    try:
        data = resp.json()
    except Exception as e:
        print(f"[!] Failed to parse JSON: {e}")
        print("[DEBUG] Raw response:", resp.text)
        return

    records = data.get("data", [])

    if isinstance(records, str):
        try:
            records = json.loads(records)
        except Exception as e:
            print(f"[!] Failed to parse nested JSON in 'data': {e}")
            print("[DEBUG] Nested JSON string:", records)
            return

    if not records:
        print("[!] No FTP accounts found for this domain.")
        return

    print(f"\n[+] Found {len(records)} FTP account(s):\n")

    for idx, rec in enumerate(records, start=1):
        if not isinstance(rec, dict):
            print(f"[!] Skipping unexpected record (not dict): {rec}")
            continue
        
        print(f"Account #{idx}:")
        # Print all key-value pairs nicely
        for key, value in rec.items():
            print(f"   {key}: {value}")
        print("-" * 40)

def main():
    target_domain = load_target_domain()
    if not target_domain:
        print("[!] Cannot proceed without target domain.")
        return

    session, headers = load_session()
    if not session or not headers:
        print("[!] Could not load a valid session.")
        return

    list_ftp_accounts(session, headers, target_domain)

if __name__ == "__main__":
    main()
