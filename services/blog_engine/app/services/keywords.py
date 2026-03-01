import json
from pathlib import Path
from datetime import datetime, timezone

# -------------------------------------------------
# Paths
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent / "externals" / "Scrapers" / "data"

INPUT_FILE = BASE_DIR / "competitor-data.json"
OUTPUT_FILE = BASE_DIR / "filtered-keywords.json"


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def normalize_keyword(keyword: str) -> str:
    return keyword.strip().lower()


def extract_keywords(entry: dict) -> list[str]:
    raw = entry.get("keywords", "")
    if not raw:
        return []

    return [
        normalize_keyword(k)
        for k in raw.split(",")
        if k.strip()
    ]


# -------------------------------------------------
# Main processing
# -------------------------------------------------
def build_keyword_index(data: list[dict]) -> dict:
    all_keywords = set()
    by_domain = {}

    for entry in data:
        domain = entry.get("domain") or "unknown"
        keywords = extract_keywords(entry)

        if not keywords:
            continue

        all_keywords.update(keywords)

        by_domain.setdefault(domain, set()).update(keywords)

    return {
        "all_keywords": sorted(all_keywords),
        "by_domain": {
            domain: sorted(keywords)
            for domain, keywords in by_domain.items()
        },
        "meta": {
            "total_keywords": len(all_keywords),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    }


# -------------------------------------------------
# Entrypoint
# -------------------------------------------------
def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with INPUT_FILE.open("r", encoding="utf-8") as f:
        competitor_data = json.load(f)

    keyword_index = build_keyword_index(competitor_data)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(keyword_index, f, indent=2, ensure_ascii=False)

    print(f"[✓] Keywords extracted: {keyword_index['meta']['total_keywords']}")
    print(f"[✓] Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
