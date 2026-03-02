# File: list-packages.py

import os
import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CYBERPANEL_URL = "https://192.168.42.80:8090"
SESSION_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json")
PACKAGE_API_URL = f"{CYBERPANEL_URL}/packages/fetchPackagesTable"

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
            print("[!] CSRF token or sessionid missing.")
            return None, None

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Referer": CYBERPANEL_URL + "/packages/listPackages",
            "Cookie": f"csrftoken={csrf_token}; sessionid={sessionid}"
        }

        return session, headers
    except Exception as e:
        print(f"[!] Failed to load session: {e}")
        return None, None

def list_packages(session, headers):
    print("[*] Fetching hosting packages ...")

    try:
        resp = session.post(PACKAGE_API_URL, headers=headers, json={}, verify=False)

        if resp.status_code != 200:
            print(f"[!] API call failed with status: {resp.status_code}")
            print("[DEBUG] Response snippet:", resp.text[:500])
            return

        data = resp.json()

    except Exception as e:
        print(f"[!] Failed to decode JSON: {e}")
        print("[DEBUG] Raw response snippet:", resp.text[:500])
        return

    if data.get("status") != 1:
        print(f"[!] API returned failure: {data.get('error_message', 'No error message')}")
        return

    raw = data.get("data", [])
    if isinstance(raw, str):
        try:
            records = json.loads(raw)
        except Exception as e:
            print(f"[!] Could not decode nested JSON from 'data': {e}")
            print("[DEBUG] Raw data string:", raw[:200])
            return
    else:
        records = raw

    if not records:
        print("[!] No packages found.")
        return

    print(f"\n[+] Found {len(records)} hosting package(s):\n")
    for idx, rec in enumerate(records, start=1):
        print(f"Package #{idx}:")
        if isinstance(rec, dict):
            for key, val in rec.items():
                print(f"   {key}: {val}")
        else:
            print(f"   [Unexpected record format] {rec}")
        print("-" * 40)

def main():
    session, headers = load_session()
    if not session or not headers:
        print("[!] Session could not be established.")
        return

    list_packages(session, headers)

if __name__ == "__main__":
    main()
