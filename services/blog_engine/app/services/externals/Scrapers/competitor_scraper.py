#competitor_scraper.py


#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

# ------------------------ Configuration ------------------------ #
WORKDIR = Path("/mnt/h/blog_engine/app/services/externals/Scrapers")
DATA_DIR = WORKDIR / "data"
OUTPUT_FILE = DATA_DIR / "competitor-data.json"
URLS = [
    "https://togetherhosting.com/",
    "https://paulkeys.dev/",
    "https://paulkeys.org/"
    
]

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------ Logging ------------------------ #
def log_info(msg: str):
    print(f"\033[1;37m[{datetime.now()}] - {msg}\033[0m")

def log_warn(msg: str):
    print(f"\033[1;33m[{datetime.now()}] ⚠️ {msg}\033[0m")

def log_error(msg: str):
    print(f"\033[0;31m[{datetime.now()}] ERROR: {msg}\033[0m")

# ------------------------ Scraper ------------------------ #
def scrape_site(url: str) -> dict:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html_content = response.text
    except requests.RequestException as e:
        log_error(f"Failed to fetch {url}: {e}")
        return {}

    soup = BeautifulSoup(html_content, "html.parser")

    def get_meta(name: str):
        tag = soup.find("meta", attrs={"name": name})
        return tag["content"].strip() if tag and tag.get("content") else ""

    data = {
        "domain": url.split("/")[2],
        "url": url,
        "title": soup.title.string.strip() if soup.title else "",
        "description": get_meta("description"),
        "keywords": get_meta("keywords"),
        "h1": soup.h1.string.strip() if soup.h1 else "",
        "robots": get_meta("robots"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Logging warnings for missing content
    if not data["title"]:
        log_warn(f"No title on {url}")
    if not data["description"]:
        log_warn(f"No description on {url}")
    if not data["robots"]:
        log_warn(f"No robots tag on {url}")

    return data

# ------------------------ Main ------------------------ #
def main():
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_data = []

    for url in URLS:
        log_info(f"Fetching {url}")
        result = scrape_site(url)
        if result:
            all_data.append(result)
            log_info(f"Collected {result['domain']}")

    # Save JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    log_info(f"Saved structured data to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
