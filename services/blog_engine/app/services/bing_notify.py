import json
import requests
import urllib.parse
import os
from datetime import datetime
from pathlib import Path

API_KEY = "edccbdc0d30545af9d19d7681faeb27e"
BASE_DIR = Path(__file__).resolve().parents[2]
SEO_DATA_FILE = str(BASE_DIR / "app/services/data/outputs/blog_posts.json")
LOG_FILE = str(BASE_DIR / "app/services/logs/bing_submit.log")
SITE_BASE_URLS = ["https://seo-post.paycc.store"]  # List of sites

def submit_url_to_bing(site_url, url_to_submit):
    BING_API_URL = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey={API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {"siteUrl": site_url, "urlList": [url_to_submit]}

    try:
        response = requests.post(BING_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            log_message(f"✅ Success: {url_to_submit} on {site_url}")
            return True
        else:
            log_message(f"❌ Failed: {url_to_submit} on {site_url} | Status {response.status_code} | {response.text}")
            return False
    except Exception as e:
        log_message(f"❗ Error submitting {url_to_submit} on {site_url}: {e}")
        return False

def load_seo_data(filepath):
    if not os.path.exists(filepath):
        log_message(f"⚠️ SEO data file not found at {filepath}")
        return {}
    with open(filepath, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            log_message(f"🚫 JSON decode error: {e}")
            return {}

def log_message(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    print(full_message)
    with open(LOG_FILE, "a") as log:
        log.write(full_message + "\n")

def main():
    seo_data = load_seo_data(SEO_DATA_FILE)
    if not seo_data:
        log_message("⚠️ No SEO data to process.")
        return

    for key, post in seo_data.items():
        slug = post.get("slug")
        if not slug:
            log_message(f"⚠️ Skipping {key}: no slug available.")
            continue

        for site_base in SITE_BASE_URLS:
            url = f"{site_base}/{slug}"
            parsed = urllib.parse.urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            submit_url_to_bing(base_url, url)

if __name__ == "__main__":
    main()
