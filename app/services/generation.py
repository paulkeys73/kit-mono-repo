#!/usr/bin/env python3
import json
from pathlib import Path

# ------------------------ Configuration ------------------------ #
BASE_DIR = Path(__file__).parent
SCRAPED_JSON = BASE_DIR / "externals" / "Scrapers" / "data" / "wiki_scraped_data.json"
COMPETITOR_JSON = BASE_DIR / "externals" / "Scrapers" / "data" / "competitor-data.json"

OUTPUT_DIR = BASE_DIR / "data" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "blog_posts.json"

# ------------------------ Load JSON ------------------------ #
def load_json_file(filename: Path):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            print(f"[INFO] Loading JSON file: {filename.name}")
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load {filename}: {e}")
        return {}

# ------------------------ Deduplicate Lines ------------------------ #
def deduplicate_text(text: str) -> str:
    seen = set()
    lines = text.splitlines()
    deduped = []
    for line in lines:
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            deduped.append(line)
    return "\n".join(deduped)

# ------------------------ Build Blog Content ------------------------ #
def build_blog_content(topic: str, sections: dict, competitors: list[dict] = None) -> dict:
    body_html = ""

    # Use "Overview" as intro if available
    intro = deduplicate_text(sections.get("Overview", next(iter(sections.values()), "Content will be updated soon.")))
    body_html += f"<h2>Introduction</h2>\n<p>{intro.replace('\n', '</p><p>')}</p>\n"

    # Add remaining sections
    for sec_name, sec_text in sections.items():
        if sec_name.lower() == "overview":
            continue
        sec_text = deduplicate_text(sec_text)
        body_html += f"<h2>{sec_name}</h2>\n<p>{sec_text.replace('\n', '</p><p>')}</p>\n"

    # Aggregate competitor metadata (optional, only for content enrichment)
    competitor_html = ""
    if competitors:
        for comp in competitors:
            comp_title = comp.get("title", comp.get("domain", "Competitor"))
            comp_url = comp.get("url", "#")
            comp_desc = comp.get("description", "No details provided.")
            competitor_html += (
                f"<p>We analyzed <a href='{comp_url}'>{comp_title}</a>. "
                f"Their positioning highlights: {comp_desc}</p>\n"
            )

    if competitor_html:
        body_html += f"<h2>Competitor Insights</h2>\n{competitor_html}"

    # Conclusion
    body_html += (
        f"<h2>Conclusion</h2>\n"
        f"<p>This guide explored <strong>{topic}</strong>, combining factual insights from Wikipedia "
        f"and competitor data. Use this information to make better decisions and stay ahead.</p>"
    )

    # Prepare metadata
    title = topic
    meta = f"Learn about {topic}."
    slug = topic.lower().replace(" ", "-")
    keywords = [topic, "guide", "reference"]

    categories = ["Guides", "SEO Content"]
    tags = [topic] + keywords[:3]

    return {
        "title": title,
        "meta": meta,
        "body": body_html,
        "categories": categories,
        "tags": tags,
        "keywords": keywords,
        "slug": slug
    }

# ------------------------ Main ------------------------ #
if __name__ == "__main__":
    scraped_data = load_json_file(SCRAPED_JSON)
    competitors = load_json_file(COMPETITOR_JSON)

    all_posts = {}
    for topic, content in scraped_data.items():
        post = build_blog_content(topic, content.get("sections", {}), competitors)
        all_posts[topic] = post

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    print(f"[INFO] All blog posts generated and saved to {OUTPUT_FILE}")
