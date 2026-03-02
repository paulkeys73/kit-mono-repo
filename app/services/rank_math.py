import requests
from requests.auth import HTTPBasicAuth
import json
import urllib3

# -----------------------------
# WordPress Credentials
# -----------------------------
WP_URL = "https://wp-seo.com/wp-json/wp/v2"  # Use HTTPS or HTTP
WP_USER = "root"
WP_APP_PASSWORD = "nolCZV0GWFz5YiIXECXBNQcY"

# -----------------------------
# Disable SSL warnings for self-signed certs
# -----------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------------
# Helper Functions
# -----------------------------
def wp_auth():
    """Return HTTPBasicAuth object for WordPress"""
    return HTTPBasicAuth(WP_USER, WP_APP_PASSWORD)

def check_login():
    """Check WordPress REST API login"""
    print("=== WordPress Login Check ===")
    url = f"{WP_URL}/users/me"
    try:
        resp = requests.get(url, auth=wp_auth(), verify=False)
        print(f"[DEBUG] Request URL: {url}")
        print(f"[DEBUG] Status Code: {resp.status_code}")
        print(f"[DEBUG] Response Headers: {dict(resp.headers)}")

        try:
            resp_json = resp.json()
            print(f"[DEBUG] Response Body: {json.dumps(resp_json, indent=2)}")
        except Exception:
            print(f"[DEBUG] Response Body (raw): {resp.text}")

        if resp.status_code == 200:
            user = resp.json()
            print(f"[✓] Logged in as {user.get('name')} (ID: {user.get('id')})")
            return True
        else:
            print(f"[✗] Login failed | Status code: {resp.status_code}")
            print(f"[✗] Message: {resp.json().get('message', '')}")
            return False

    except Exception as e:
        print(f"[✗] Error during login check: {e}")
        return False

# -----------------------------
# Rank Math API Explorer
# -----------------------------
def get_rm_base_url():
    return WP_URL.replace("/wp/v2", "/rm/v1/")

def list_endpoints():
    """Probe /rm/v1/ to see available endpoints"""
    base_url = get_rm_base_url()
    print("\n=== Discovering Rank Math endpoints ===")
    try:
        resp = requests.get(base_url, auth=wp_auth(), verify=False)
        print(f"[DEBUG] URL: {base_url}")
        print(f"[DEBUG] Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print("[✓] Rank Math endpoints discovered:")
            print(json.dumps(data, indent=2))
        else:
            print(f"[✗] Could not retrieve endpoints | Status {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"[✗] Error discovering endpoints: {e}")

def list_modules():
    """Get active/inactive Rank Math modules"""
    url = f"{get_rm_base_url()}modules"
    print("\n=== Rank Math Modules ===")
    try:
        resp = requests.get(url, auth=wp_auth(), verify=False)
        if resp.status_code == 200:
            modules = resp.json()
            for mod in modules:
                status = "Active" if mod.get("active") else "Inactive"
                print(f"- {mod.get('name')} | {status}")
        else:
            print(f"[✗] Failed to list modules | Status {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"[✗] Error listing modules: {e}")

def get_global_seo():
    """Get global Rank Math SEO settings"""
    url = f"{get_rm_base_url()}seo"
    print("\n=== Rank Math Global SEO Settings ===")
    try:
        resp = requests.get(url, auth=wp_auth(), verify=False)
        if resp.status_code == 200:
            seo = resp.json()
            print(json.dumps(seo, indent=2))
        else:
            print(f"[✗] Failed to get SEO settings | Status {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"[✗] Error fetching SEO settings: {e}")

def get_post_seo(post_id):
    """Get Rank Math SEO data for a specific post/page"""
    url = f"{get_rm_base_url()}seo-post/{post_id}"
    print(f"\n=== Rank Math SEO Data for Post ID {post_id} ===")
    try:
        resp = requests.get(url, auth=wp_auth(), verify=False)
        if resp.status_code == 200:
            post_seo = resp.json()
            print(json.dumps(post_seo, indent=2))
        else:
            print(f"[✗] Failed to get post SEO | Status {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"[✗] Error fetching post SEO: {e}")

# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    if check_login():
        list_endpoints()
        list_modules()
        get_global_seo()
        # Example: fetch SEO data for post ID 1
        get_post_seo(1)
