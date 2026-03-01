from pathlib import Path
import requests

# -------------------------------------------------
# Base directories
# -------------------------------------------------
BASE_DIR = Path(__file__).parent.parent  # assuming this file is in external_api/
IMAGE_DIR = BASE_DIR / "backgrounds"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------
# Pexels API key
# -------------------------------------------------
PEXELS_API_KEY = "8RHQIOcQcqqjsy1KXtU7fogzwr92t50QUXzBkKS5WaE3sg9WZWiJbSDW"

# -------------------------------------------------
# Background categories & default queries
# -------------------------------------------------
DEFAULT_CATEGORIES = {
    "nature": "nature forest sea sky clouds galaxy",
    "technology": "technology digital computer abstract",
    "space": "space stars galaxy planets universe",
    "urban": "city urban street buildings night",
    "abstract": "abstract pattern colors shapes",
    "food": "food cuisine ingredients healthy",
}

# -------------------------------------------------
# Fetch images from Pexels
# -------------------------------------------------
def fetch_pexels_images(category: str = "nature", count: int = 5, query: str = None):
    """
    Fetch random images from Pexels for a given category.
    Saves them into IMAGE_DIR/category/.
    """
    # Determine query string
    query_str = query or DEFAULT_CATEGORIES.get(category, category)

    # Create category folder
    category_dir = IMAGE_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)

    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query_str}&per_page={count}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Pexels API error: {response.status_code} {response.text}")
        return

    data = response.json()
    for i, photo in enumerate(data.get("photos", [])):
        img_url = photo.get("src", {}).get("landscape")
        if img_url:
            img_data = requests.get(img_url).content
            out_path = category_dir / f"{category}_{i}.jpg"
            with open(out_path, "wb") as f:
                f.write(img_data)
            print(f"Downloaded: {out_path}")

# -------------------------------------------------
# Helper: Ensure at least `count` images exist
# -------------------------------------------------
def ensure_category_images(category: str = "nature", count: int = 5):
    """
    Ensure the category folder has images.
    Fetches from Pexels if folder is empty.
    """
    category_dir = IMAGE_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)
    if not any(category_dir.glob("*.*")):
        print(f"No images found for category '{category}'. Fetching from Pexels...")
        fetch_pexels_images(category=category, count=count)
    return list(category_dir.glob("*.*"))
