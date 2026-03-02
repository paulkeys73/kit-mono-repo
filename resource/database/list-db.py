import os
import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CYBERPANEL_URL = "https://192.168.42.80:8090"
SESSION_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json")
WEBSITE_INFO_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/created-websites.json")

DB_API_URL = f"{CYBERPANEL_URL}/dataBases/fetchDatabases"

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
        sessionid = cookie_dict.get("sessionid")
        if not csrf_token or not sessionid:
            print("[!] CSRF token or sessionid missing in cookies. Cannot proceed.")
            return None, None

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Referer": CYBERPANEL_URL + "/dataBases/listDBs",
            "Cookie": f"csrftoken={csrf_token}; sessionid={sessionid}"
        }

        return session, headers
    except Exception as e:
        print(f"[!] Failed to load session: {e}")
        return None, None

def list_db_accounts(session, headers, target_domain):
    print(f"[*] Fetching DB accounts for domain '{target_domain}' ...")

    payload = {"databaseWebsite": target_domain}
    resp = session.post(DB_API_URL, json=payload, headers=headers, verify=False)

    if resp.status_code != 200:
        print(f"[!] API call failed with status: {resp.status_code}")
        print("[DEBUG] Response snippet:", resp.text[:500])
        return

    try:
        data = resp.json()
    except Exception as e:
        print(f"[!] Failed to parse JSON: {e}")
        print("[DEBUG] Raw response snippet:", resp.text[:500])
        return

    if not data.get("status"):
        print(f"[!] API returned failure status: {data.get('error_message', 'No error message')}")
        return

    records_raw = data.get("data", [])

    # This is the crucial fix:
    if isinstance(records_raw, str):
        try:
            records = json.loads(records_raw)
        except Exception as e:
            print(f"[!] Failed to parse nested JSON in 'data': {e}")
            records = []
    else:
        records = records_raw

    if not records:
        print("[!] No database accounts found.")
        return

    print(f"\n[+] Found {len(records)} database account(s):\n")
    for idx, rec in enumerate(records, start=1):
        print(f"DB Account #{idx}:")
        if isinstance(rec, dict):
            for key, value in rec.items():
                print(f"   {key}: {value}")
        else:
            print(f"   [Unexpected record type: {type(rec)}] {rec}")
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

    list_db_accounts(session, headers, target_domain)

if __name__ == "__main__":
    main()
