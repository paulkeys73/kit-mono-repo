# File: load-user-session.py
import pickle
import os
import sys
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


CYBERPANEL_URL = "https://192.168.42.80:8090"
SESSION_FILE = os.path.abspath("f:/my-servers/services/backend/django/hosting/auth/cp_admin_session.pkl")

def load_admin_session():
    if not os.path.exists(SESSION_FILE):
        print("[!] Session file does not exist.")
        return None

    try:
        with open(SESSION_FILE, "rb") as f:
            session = pickle.load(f)

        # Validate session by hitting a known endpoint
        test_url = f"{CYBERPANEL_URL}/users/listUsers"
        resp = session.get(test_url, verify=False)
        if resp.status_code == 200 and "List Users" in resp.text:
            print("[+] Admin session is valid and active.")
            return session
        else:
            print("[!] Session loaded but appears to be invalid or expired.")
            return None
    except Exception as e:
        print(f"[!] Error loading session: {e}")
        return None

# Allow importing this in other modules
if __name__ == "__main__":
    sess = load_admin_session()
    if sess:
        print("[*] Session loaded successfully.")
    else:
        print("[!] Failed to load valid session.")
