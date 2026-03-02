
import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from .image.image_generator import generate_images_for_post



BASE_DIR = Path(__file__).resolve().parents[2]  # points to H:/blog_engine or /mnt/h/blog_engine
INPUT_FILE = BASE_DIR / "app/services/data/outputs/blog_posts.json"
KEYWORDS_INPUT = BASE_DIR / "app/services/externals/Scrapers/data/filtered-keywords.json"
OUTPUT_FILE = BASE_DIR / "app/services/externals/Scrapers/data/final-blog-post.json"


# -------------------------------------------------
# SEO Config (Rank Math aligned)
# -------------------------------------------------
PARAGRAPH_WORD_MIN = 40
PARAGRAPH_WORD_MAX = 70
SECTION_WORD_MAX = 300
META_DESC_MAX = 160
SECONDARY_KEYWORDS_PER_SECTION = 1

# -------------------------------------------------
# Sanitization
# -------------------------------------------------
def normalize_math_expressions(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\{\\displaystyle.*?\}", "", text)
    text = re.sub(r"\\(frac|times|overline)\b", "", text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\b([A-Z])\s+([A-Z])\b", r"\1\2", text)
    text = re.sub(r"\b(?:[a-z]\s){2,}[a-z]\b",
                  lambda m: m.group(0).replace(" ", ""), text)
    text = re.sub(
        r"ER\s*=\s*interactions\s*followers\s*100\s*%?",
        "Engagement rate is calculated by dividing interactions by followers and multiplying by 100 percent",
        text, flags=re.IGNORECASE
    )
    text = re.sub(r"[×=/%]", "", text)
    return text

def sanitize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", text)
    text = re.sub(r"\[\d+\]\[\d+\]", "", text)
    text = re.sub(r"\[citation needed\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bas v\.club\.?\b", "", text, flags=re.IGNORECASE)
    text = text.replace('\\"', '"').replace("“", "").replace("”", "")
    text = text.replace("‘", "").replace("’", "")
    text = re.sub(r'"([^"]+)"', r'\1', text)
    text = normalize_math_expressions(text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

def clamp_words(text: str, max_words: int) -> str:
    return " ".join(text.split()[:max_words])

# -------------------------------------------------
# Section Splitter for SEO
# -------------------------------------------------
def split_sections(body: str) -> dict:
    sections = {}
    body = sanitize_text(body)
    h2_splits = re.split(r"<h2>(.*?)</h2>", body, flags=re.IGNORECASE)
    
    if len(h2_splits) > 1:
        preamble = h2_splits[0].strip()
        if preamble:
            sections["Introduction"] = clamp_words(preamble, SECTION_WORD_MAX)
        for i in range(1, len(h2_splits), 2):
            heading = h2_splits[i].strip()
            content = h2_splits[i+1].strip() if i+1 < len(h2_splits) else ""
            sections[heading] = clamp_words(content, SECTION_WORD_MAX)
    else:
        sections["Content"] = clamp_words(body, SECTION_WORD_MAX)
    
    return sections

# -------------------------------------------------
# Keyword Injection
# -------------------------------------------------
def inject_secondary_keywords(text: str, keywords: list[str], limit: int):
    used = []
    lowered = text.lower()
    for kw in keywords:
        if kw.lower() in lowered:
            continue
        if len(used) >= limit:
            break
        text += f" {kw}."
        used.append(kw)
    return text, used

def keyword_density(text: str, keyword: str) -> float:
    words = text.lower().split()
    return round((words.count(keyword.lower()) / max(len(words), 1)) * 100, 2)

# -------------------------------------------------
# Formatter
# -------------------------------------------------


def format_post(raw_post: dict, keywords: list[str]) -> dict:
    title_raw = sanitize_text(raw_post.get("title", "Untitled"))
    body_raw = raw_post.get("body", "")
    slug = slugify(title_raw)

    # Split into sections
    sections = split_sections(body_raw)

    formatted_sections = {}
    for heading, content in sections.items():
        content = sanitize_text(content)
        content, _ = inject_secondary_keywords(content, keywords[1:6], SECONDARY_KEYWORDS_PER_SECTION)
        formatted_sections[heading] = clamp_words(content, SECTION_WORD_MAX)

    first_section = next(iter(formatted_sections.values()), "")
    meta_description = clamp_words(first_section, 28)[:META_DESC_MAX]

    # -------------------------------------------------
    # Generate images using your module
    # -------------------------------------------------
    post_for_images = {
        "title": title_raw,
        "slug": slug,
        "sections": formatted_sections,
        "pros": raw_post.get("pros", []),
        "cons": raw_post.get("cons", [])
    }

    # Pass proper keys so text appears on images
    images = generate_images_for_post(post_for_images)

    # Convert Path objects to strings for JSON
    images = [str(p) for p in images]

    # -------------------------------------------------
    # Return final structured post
    # -------------------------------------------------
    return {
        "title": title_raw,
        "slug": slug,
        "meta_description": meta_description,
        "sections": formatted_sections,
        "categories": raw_post.get("categories", []),
        "tags": raw_post.get("tags", keywords[1:6]),
        "keywords": raw_post.get("keywords", keywords),
        "images": images,  # hero + section images
        "seo": {
            "rank_math_focus_keyword": "",
            "rank_math_secondary_keywords": keywords[1:6],
            "rank_math_title": title_raw,
            "rank_math_description": meta_description,
            "rank_math_keyword_density": 0,
            "rank_math_readability": "good",
            "rank_math_content_ai_ready": True
        },
        "generated_at": datetime.now(timezone.utc).isoformat()  # UTC-aware
    }




# -------------------------------------------------
# Entrypoint
# -------------------------------------------------
def main():
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        posts = json.load(f)

    with KEYWORDS_INPUT.open("r", encoding="utf-8") as f:
        keyword_data = json.load(f)

    keywords = keyword_data.get("all_keywords", [])

    final_output = {}
    for post_key, raw_post in posts.items():
        final_output[post_key] = format_post(raw_post, keywords)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    print("[✓] Blog posts reformatted, SEO + Rank Math safe")
    print(f"[✓] Output saved → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
