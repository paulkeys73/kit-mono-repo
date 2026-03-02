import requests
from requests.auth import HTTPBasicAuth
import json
import urllib3
import sys
from pathlib import Path

# -----------------------------
# WordPress Credentials
# -----------------------------
WP_URL = "https://wp-seo.com/wp-json/wp/v2"
WP_USER = "root"
WP_APP_PASSWORD = "nolCZV0GWFz5YiIXECXBNQcY"

# -----------------------------
# Path to external post JSON
# -----------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
POST_JSON_PATH = BASE_DIR / "app/services/externals/Scrapers/data/final-blog-post.json"

# -----------------------------
# Disable warnings for self-signed SSL
# -----------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------------
# Helper Functions
# -----------------------------
def wp_auth():
    return HTTPBasicAuth(WP_USER, WP_APP_PASSWORD)


def check_login():
    print("=== WordPress Login Check ===")
    url = f"{WP_URL}/users/me"
    try:
        resp = requests.get(url, auth=wp_auth(), verify=False)
        print(f"[DEBUG] Request URL: {url} | Status: {resp.status_code}")
        if resp.status_code == 200:
            user = resp.json()
            print(f"[✓] Logged in as {user.get('name')} (ID: {user.get('id')})")
            return True
        print(f"[✗] Login failed | Status: {resp.status_code}")
        print(resp.text)
        return False
    except Exception as e:
        print(f"[✗] Error during login check: {e}")
        return False


def get_or_create_term(name, taxonomy="categories"):
    """Get existing term by name, or create it and return its ID"""
    url = f"{WP_URL}/{taxonomy}?search={name}"
    resp = requests.get(url, auth=wp_auth(), verify=False)
    if resp.status_code == 200 and resp.json():
        return resp.json()[0]["id"]
    payload = {"name": name}
    resp = requests.post(f"{WP_URL}/{taxonomy}", auth=wp_auth(), json=payload, verify=False)
    if resp.status_code in [200, 201]:
        return resp.json()["id"]
    print(f"[✗] Failed to create {taxonomy[:-1]} '{name}' | Status: {resp.status_code}")
    return None


def resolve_terms(names, taxonomy="categories"):
    """Convert list of names → list of IDs"""
    ids = []
    for name in names:
        term_id = get_or_create_term(name, taxonomy)
        if term_id:
            ids.append(term_id)
    return ids


def create_post_from_json(json_path: Path):
    if not json_path.exists():
        print(f"[✗] JSON file not found: {json_path}")
        return None

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("[✗] JSON file is empty")
        return None

    first_key = next(iter(data))
    post_data = data[first_key]

    # -----------------------------
    # Combine all sections content
    # -----------------------------
    content = ""
    if "sections" in post_data:
        content = "\n\n".join(post_data["sections"].values())

    # -----------------------------
    # Prepare Rank Math SEO meta
    # -----------------------------
    seo_meta = {}
    if "seo" in post_data:
        seo_meta = {
            "rank_math_focus_keyword": post_data["seo"].get("rank_math_focus_keyword", ""),
            "rank_math_secondary_keywords": post_data["seo"].get("rank_math_secondary_keywords", []),
            "rank_math_title": post_data["seo"].get("rank_math_title", ""),
            "rank_math_description": post_data["seo"].get("rank_math_description", ""),
            "rank_math_keyword_density": post_data["seo"].get("rank_math_keyword_density", ""),
            "rank_math_readability": post_data["seo"].get("rank_math_readability", ""),
            "rank_math_content_ai_ready": post_data["seo"].get("rank_math_content_ai_ready", ""),
            "rank_math_generated_at": post_data.get("generated_at", ""),
        }

    # -----------------------------
    # Resolve category and tag IDs
    # -----------------------------
    category_ids = resolve_terms(post_data.get("categories", []), "categories")
    tag_ids = resolve_terms(post_data.get("tags", []), "tags")

    payload = {
        "title": post_data.get("title", first_key),
        "content": content,
        "status": "publish",
        "categories": category_ids,
        "tags": tag_ids,
        "meta": seo_meta,
    }

    if not payload["title"] or not payload["content"]:
        print("[✗] Cannot create post: title or content is empty")
        return None

    url = f"{WP_URL}/posts"
    try:
        resp = requests.post(url, auth=wp_auth(), json=payload, verify=False)
        if resp.status_code in [200, 201]:
            created_post = resp.json()
            print(f"[✓] Post created: {created_post.get('title', {}).get('rendered', '')} (ID: {created_post.get('id')})")
            return created_post
        print(f"[✗] Failed to create post | Status: {resp.status_code}")
        print(resp.text)
        return None
    except Exception as e:
        print(f"[✗] Error creating post: {e}")
        return None


# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    if not check_login():
        sys.exit(1)

    created = create_post_from_json(POST_JSON_PATH)
    if created is None:
        sys.exit(1)
