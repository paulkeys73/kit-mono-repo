import requests
import urllib3
import json
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CyberPanel Configuration ===
CYBERPANEL_URL = "https://192.168.42.80:8090"
LOGIN_PAGE = f"{CYBERPANEL_URL}/login"
LOGIN_API = f"{CYBERPANEL_URL}/verifyLogin"

# === Session File (shared with add-cp-user.py) ===
SESSION_FILE = "f:/my-servers/services/backend/django/hosting/auth/users/users-db/cp_admin_session.json"

# === Admin Credentials ===
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123Pw"

# === Headers ===
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": LOGIN_PAGE,
    "Connection": "keep-alive"
}

def get_csrf_token_from_cookie(session):
    resp = session.get(LOGIN_PAGE, headers=HEADERS, verify=False)
    if resp.status_code != 200:
        print(f"[!] Failed to load login page: {resp.status_code}")
        return None

    token = session.cookies.get("csrftoken")
    if token:
        print(f"[+] CSRF token (cookie): {token}")
        return token
    else:
        print("[!] No CSRF token found in cookies.")
        print("[DEBUG] Cookies:", session.cookies.get_dict())
        return None

def save_cookies_to_file(session, path):
    cookies = session.cookies.get_dict()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cookies, f)
    print(f"[+] Session cookies saved to {path}")

def login_and_save_session(username, password):
    session = requests.Session()
    csrf_token = get_csrf_token_from_cookie(session)
    if not csrf_token:
        print("[!] CSRF token missing. Aborting login.")
        return None

    payload = {
        "username": username,
        "password": password,
        "languageSelection": "english",
        "twofa": ""
    }

    headers = HEADERS.copy()
    headers["X-CSRFToken"] = csrf_token
    headers["Content-Type"] = "application/json"

    response = session.post(LOGIN_API, json=payload, headers=headers, verify=False)

    print(f"[DEBUG] POST {LOGIN_API} status: {response.status_code}")
    print(f"[DEBUG] Response JSON: {response.text}")

    if response.status_code == 200:
        try:
            data = response.json()
            if data.get("loginStatus") == 1:
                save_cookies_to_file(session, SESSION_FILE)
                print("[+] Login successful. Session saved.")
                return session
            else:
                print(f"[!] Login failed: {data.get('error_message')}")
        except Exception as e:
            print(f"[!] Failed to parse login response: {e}")
    else:
        print("[!] Login request failed.")
    return None

if __name__ == "__main__":
    login_and_save_session(ADMIN_USERNAME, ADMIN_PASSWORD)
