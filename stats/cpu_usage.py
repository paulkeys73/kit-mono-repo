import os
import pickle
import subprocess
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CYBERPANEL_URL = "https://192.168.42.80:8090"
SYSTEM_STATUS_URL = f"{CYBERPANEL_URL}/base/getSystemStatus"
SESSION_FILE = r"E:\hosting\auth\users\cp_admin_session.pkl"  # Ensure both scripts use this
USER_LIST_URL = f"{CYBERPANEL_URL}/users/listUsers"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def load_or_auth_admin_session():
    # Try existing session first
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "rb") as f:
                session = pickle.load(f)
            test = session.get(USER_LIST_URL, headers=HEADERS, verify=False)
            if test.status_code == 200 and "List Users" in test.text:
                print("[+] Reused existing admin session.")
                return session
        except Exception as e:
            print(f"[!] Failed to reuse session: {e}")

    print("[*] No valid session. Triggering admin-login-cp.py...")

    result = subprocess.run(
        ["python3", r"E:\hosting\auth\admin-login-cp.py"],  # Must match actual location
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.returncode != 0:
        print("[!] Admin login script failed.")
        print(result.stderr)
        return None

    # Try to load new session again
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "rb") as f:
                session = pickle.load(f)
            print("[+] New admin session loaded.")
            return session
        except Exception as e:
            print(f"[!] Failed to load session after login: {e}")
    else:
        print(f"[!] Session file not found at {SESSION_FILE} after login.")

    print("[!] Could not obtain session.")
    return None

def get_system_status(session):
    try:
        resp = session.get(SYSTEM_STATUS_URL, verify=False)
        if resp.status_code != 200:
            print(f"[-] Failed to get system status: HTTP {resp.status_code}")
            print(f"Response: {resp.text[:200]}")
            return None
        return resp.json()
    except Exception as e:
        print(f"[-] JSON parsing error: {e}")
        return None

def main():
    session = load_or_auth_admin_session()
    if not session:
        print("[!] Could not authenticate. Aborting.")
        return

    status = get_system_status(session)
    if status is None:
        print("Could not retrieve system status from CyberPanel.")
        return

    cpu = status.get("cpuUsage")
    ram = status.get("ramUsage")
    disk = status.get("diskUsage")

    print(f"CPU Usage: {cpu}%")
    print(f"RAM Usage: {ram}%")
    print(f"Disk Usage: {disk}%")

if __name__ == "__main__":
    main()
