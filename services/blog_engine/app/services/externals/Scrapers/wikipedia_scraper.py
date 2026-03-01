#wikipedia_scraper.py

#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
from pathlib import Path
import sys

# ------------------------ Configuration ------------------------ #
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_DIR / "wiki_scraped_data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/140.0.0.0 Safari/537.36"
}

class WikipediaScraper:
    SEARCH_URL = "https://en.wikipedia.org/w/api.php"

    def __init__(self):
        pass

    def search_page(self, topic: str) -> str:
        """Search Wikipedia and return the closest matching page title."""
        params = {
            "action": "query",
            "list": "search",
            "srsearch": topic,
            "format": "json",
            "utf8": 1
        }
        try:
            response = requests.get(self.SEARCH_URL, params=params, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            results = data.get("query", {}).get("search", [])
            if results:
                return results[0]["title"]
        except requests.RequestException as e:
            print(f"[ERROR] Wikipedia search failed for '{topic}': {e}")
        return ""

    def scrape_page(self, topic: str) -> dict:
        """Scrape main content from a Wikipedia page and format into SEO sections."""
        page_title = self.search_page(topic)
        if not page_title:
            print(f"[WARN] No Wikipedia page found for '{topic}'")
            return {"sections": {}, "summary": {}}

        topic_formatted = page_title.replace(" ", "_")
        url = f"https://en.wikipedia.org/wiki/{topic_formatted}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[ERROR] Failed to fetch {url}: {e}")
            return {"sections": {}, "summary": {}}

        soup = BeautifulSoup(response.text, "html.parser")
        content_div = soup.find("div", {"id": "mw-content-text"})
        if not content_div:
            return {"sections": {}, "summary": {}}

        sections = {}
        current_heading = f"{topic} Overview"
        sections[current_heading] = ""

        for element in content_div.find_all(["p", "h2", "h3"]):
            if element.name in ["h2", "h3"]:
                heading_text = element.get_text().strip()
                if any(skip in heading_text for skip in ["See also", "References", "External links", "Further reading"]):
                    break
                # Inject keyword into heading for SEO
                current_heading = f"{topic}: {heading_text}"
                sections[current_heading] = ""
            elif element.name == "p":
                para_text = element.get_text().strip()
                if para_text:
                    sections[current_heading] += para_text + "\n\n"

        sections = {k: v.strip() for k, v in sections.items() if v.strip()}

        # --------- SEO Summary --------- #
        first_para = next(iter(sections.values())).split("\n")[0] if sections else "Content will be updated soon."
        summary = {
            "title": topic,
            "meta": f"{topic} explained in detail with practical insights, key takeaways, and answers people search for.",
            "body": self.build_seo_body(sections, topic),
            "slug": topic.lower().replace(" ", "-"),
            "categories": ["Guides", "SEO Content"],
            "tags": [topic, "Wikipedia", "Complete Guide"]
        }

        return {"sections": sections, "summary": summary}

    def build_seo_body(self, sections: dict, topic: str) -> str:
        """Turn scraped sections into SEO-friendly HTML for WordPress."""
        body_html = ""
        used_sections = set()

        for sec_name, sec_text in sections.items():
            if sec_name in used_sections:
                continue
            used_sections.add(sec_name)
            paragraphs = "".join(f"<p>{p.strip()}</p>" for p in sec_text.split("\n") if p.strip())
            body_html += f"<h2>{sec_name}</h2>\n{paragraphs}\n"

        # Add SEO Conclusion CTA
        body_html += (
            f"<h2>Conclusion: {topic}</h2>\n"
            f"<p>We’ve broken down {topic} with actionable insights. "
            f"Share this guide, bookmark it, and explore more related content for deeper learning.</p>"
        )
        return body_html

    def scrape_and_save(self, topic: str):
        """Scrape one topic and save output."""
        data = self.scrape_page(topic)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({topic: data}, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Saved scraped topic '{topic}' to {OUTPUT_FILE}")


# ----------------- CLI ----------------- #
if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "what is carder007 reddit"
    scraper = WikipediaScraper()
    scraper.scrape_and_save(topic)
