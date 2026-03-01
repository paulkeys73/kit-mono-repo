import json
import os
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv
from collections import defaultdict

# -----------------------------
# Resolve base directory
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------
# Load .env
# -----------------------------
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".env"))
load_dotenv(ENV_PATH)

# -----------------------------
# Paths
# -----------------------------
INPUT_FILE = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "Best-Count.json"))
OUTPUT_FILE = os.path.join(BASE_DIR, "Data", "ProductsOnSales.json")

# -----------------------------
# Validation
# -----------------------------
if not os.path.exists(INPUT_FILE):
    raise RuntimeError(f"❌ INPUT_FILE not found: {INPUT_FILE}")

# -----------------------------
# Helpers
# -----------------------------
def load_json(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data: List[Dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def extract_price_range(product: Dict) -> Tuple[Optional[str], Optional[str]]:
    price_range = product.get("priceRange")
    if not price_range:
        return None, None
    return (
        price_range.get("min", {}).get("amount"),
        price_range.get("max", {}).get("amount"),
    )

def get_variant_prices(variant: Dict) -> Tuple[Optional[float], Optional[float]]:
    price = variant.get("price")
    compare = variant.get("compareAtPrice")

    def to_float(v):
        if v is None:
            return None
        if isinstance(v, dict):
            return float(v.get("amount"))
        return float(v)

    try:
        return to_float(price), to_float(compare)
    except Exception:
        return None, None

def is_variant_on_sale(variant: Dict) -> bool:
    if variant.get("onSale") is True:
        return True
    price, compare = get_variant_prices(variant)
    if price is None or compare is None:
        return False
    return compare > price

def sale_decision(product: Dict) -> Tuple[bool, str, Optional[Dict]]:
    variants = product.get("variants", [])
    for variant in variants:
        if is_variant_on_sale(variant):
            return True, "variant_on_sale", variant

    min_price, max_price = extract_price_range(product)
    if min_price is None or max_price is None:
        return False, "missing_variant_and_priceRange", None

    try:
        if float(max_price) > float(min_price):
            return True, "priceRange_spread", None
        else:
            return False, "prices_equal", None
    except ValueError:
        return False, "invalid_price_format", None

# -----------------------------
# Main
# -----------------------------
def main():
    print("📦 Loading Best-Count products...")
    products = load_json(INPUT_FILE)
    print(f"🔍 Processing {len(products)} records")

    on_sale_products = []
    skip_reasons = defaultdict(int)
    skip_samples = []

    for product in products:
        try:
            is_sale, reason, winning_variant = sale_decision(product)
            if is_sale:
                # Keep full product structure
                product_copy = product.copy()
                product_copy["status"] = "on_sale"
                if winning_variant:
                    product_copy["winning_variant"] = winning_variant
                on_sale_products.append(product_copy)
            else:
                skip_reasons[reason] += 1
                if len(skip_samples) < 10:
                    skip_samples.append({
                        "id": product.get("id"),
                        "title": product.get("title"),
                        "reason": reason,
                        "keys": list(product.keys())
                    })
        except Exception as e:
            skip_reasons["exception"] += 1
            if len(skip_samples) < 10:
                skip_samples.append({
                    "id": product.get("id"),
                    "title": product.get("title"),
                    "reason": "exception",
                    "error": str(e),
                })

    save_json(OUTPUT_FILE, on_sale_products)

    print("\n✅ Completed")
    print(f"💸 On-sale products: {len(on_sale_products)}")
    print("⏭️ Skip breakdown:")
    for reason, count in skip_reasons.items():
        print(f"   - {reason}: {count}")

    if skip_samples:
        print("\n🔎 Sample skipped products:")
        for s in skip_samples:
            print(f"   • {s['title']} → {s['reason']} | keys: {s.get('keys')}")

    print(f"\n📄 Output written to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
