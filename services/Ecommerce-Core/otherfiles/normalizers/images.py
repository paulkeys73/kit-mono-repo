from typing import Dict, Any, List

def normalize_images(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collects all images for a product, prioritizing the main variant images.
    Ensures each image has 'src' and 'alt', and deduplicates by 'src'.
    """
    images = []
    seen = set()

    # 1️⃣ Prioritize main variant image (first variant with an image)
    main_variant_img = None
    for variant in raw.get("variants", []):
        url = variant.get("variantUrl")
        if url:
            main_variant_img = {"src": url, "alt": raw.get("title") or ""}
            seen.add(url)
            images.append(main_variant_img)
            break  # only take first variant image as primary

    # 2️⃣ Add remaining product-level images
    for img in raw.get("images", []):
        src = img.get("src") or img.get("url") or ""
        alt = img.get("alt") or raw.get("title") or ""
        if src and src not in seen:
            seen.add(src)
            images.append({"src": src, "alt": alt})

    # 3️⃣ Add remaining variant-level images (all except main)
    for variant in raw.get("variants", []):
        url = variant.get("variantUrl")
        if url and url not in seen:
            seen.add(url)
            images.append({"src": url, "alt": raw.get("title") or ""})

        for vimg in variant.get("images", []):
            src = vimg.get("src") or vimg.get("url") or ""
            alt = vimg.get("alt") or raw.get("title") or ""
            if src and src not in seen:
                seen.add(src)
                images.append({"src": src, "alt": alt})

    return images
