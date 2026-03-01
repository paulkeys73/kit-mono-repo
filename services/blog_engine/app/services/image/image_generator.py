from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from pathlib import Path
from datetime import datetime
from .image_config import *
from .image_templates import TEMPLATES
from .utils import load_font
from .external_api import pexels
import random
import numpy as np
import io

# -------------------------------------------------
# Directories
# -------------------------------------------------
BASE_DIR = Path(__file__).parent
IMAGE_DIR = BASE_DIR / "backgrounds"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------
# Background categories
# -------------------------------------------------
BACKGROUND_CATEGORIES = ["nature", "space", "technology", "abstract", "city", "gradient", "pattern", "noise"]
OVERLAY_CATEGORIES = ["nature", "space", "abstract", "gradient", "technology", "pattern"]

# -------------------------------------------------
# Text drawing utility (fixed)
# -------------------------------------------------
def draw_text(img: Image.Image, text: str, font: ImageFont.FreeTypeFont, xy: tuple[int,int],
              max_width: int, shadow=True, overlay=True):
    """
    Draw wrapped text with shadow and optional overlay behind text.
    Operates directly on the Image object (not draw.im).
    """
    draw = ImageDraw.Draw(img)
    lines = []
    words = text.split()
    line = ""
    for word in words:
        test_line = f"{line} {word}".strip()
        bbox = draw.textbbox((0,0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            line = test_line
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)

    x0, y0 = xy
    line_heights = []
    total_height = 0
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        h = bbox[3] - bbox[1] + 5
        line_heights.append(h)
        total_height += h

    # Overlay rectangle behind text
    if overlay:
        overlay_layer = Image.new("RGBA", img.size, (0,0,0,0))
        overlay_draw = ImageDraw.Draw(overlay_layer)
        overlay_draw.rectangle((x0-10, y0, x0 + max_width, y0 + total_height), fill=(0,0,0,120))
        img.alpha_composite(overlay_layer)

    # Draw text with optional shadow
    for i, line in enumerate(lines):
        h = line_heights[i]
        if shadow:
            draw.text((x0+2, y0+2), line, font=font, fill=(0,0,0))
        draw.text((x0, y0), line, font=font, fill=TEXT_COLOR)
        y0 += h

    return y0

# -------------------------------------------------
# Dynamic background generator
# -------------------------------------------------
def generate_background(width: int, height: int, category: str = "nature") -> Image.Image:
    img = None
    category_files = pexels.ensure_category_images(category, count=5)

    if category_files:
        img_path = random.choice(category_files)
        img_data = open(img_path, "rb").read()
        img = Image.open(io.BytesIO(img_data)).convert("RGBA").resize((width, height))

    if img is None:
        img = Image.new("RGBA", (width, height), (255,255,255,255))
        draw = ImageDraw.Draw(img)
        if category in ["space", "random"]:
            start_color = tuple(random.randint(100,200) for _ in range(3))
            end_color = tuple(random.randint(50,150) for _ in range(3))
            for y in range(height):
                ratio = y/height
                color = tuple(int(start_color[i]*(1-ratio)+end_color[i]*ratio) for i in range(3)) + (255,)
                draw.line([(0,y),(width,y)], fill=color)
        elif category == "pattern":
            stripe_width = 50
            colors = [(200,200,255,255),(220,220,240,255)]
            for x in range(-height,width,stripe_width):
                draw.polygon([(x,0),(x+stripe_width,0),(x+height+stripe_width,height),(x+height,height)],
                             fill=random.choice(colors))
        elif category == "technology":
            arr = np.random.randint(200,255,(height,width,3),dtype=np.uint8)
            img = Image.fromarray(arr).convert("RGBA")
        else:
            img = Image.new("RGBA",(width,height),(150,150,150,255))

    return img

# -------------------------------------------------
# Layer subtle overlay with optional text
# -------------------------------------------------
def apply_overlay(base_img: Image.Image, text_data: dict = None) -> Image.Image:
    overlay_category = random.choice(OVERLAY_CATEGORIES)
    overlay_img = generate_background(base_img.width, base_img.height, category=overlay_category)
    overlay_img = overlay_img.convert("RGBA")

    # Create alpha mask for transparency (~20%)
    overlay_mask = Image.new("L", overlay_img.size, 50)
    overlay_img.putalpha(overlay_mask)
    base_img.alpha_composite(overlay_img)

    # Draw text on top
    if text_data:
        font_title = load_font(FONT_SIZE_TITLE)
        font_subtitle = load_font(FONT_SIZE_SUBTITLE)
        if "title" in text_data:
            draw_text(base_img, text_data["title"], font_title, xy=(50, 50), max_width=base_img.width-100)
        if "subtitle" in text_data:
            draw_text(base_img, text_data["subtitle"], font_subtitle, xy=(50, 200), max_width=base_img.width-100)

    return base_img

# -------------------------------------------------
# Generate a single image
# -------------------------------------------------
def generate_image(template: str, text_data: dict, output_name: str,
                   avatar: Image.Image=None, icons: list[Image.Image]=None,
                   category: str = None) -> Path:
    if category is None:
        category = random.choice(BACKGROUND_CATEGORIES)

    img = generate_background(IMAGE_WIDTH, IMAGE_HEIGHT, category=category)

    # Draw template elements first
    draw = ImageDraw.Draw(img)
    draw.font_title = load_font(FONT_SIZE_TITLE)
    draw.font_subtitle = load_font(FONT_SIZE_SUBTITLE)

    if template not in TEMPLATES:
        raise ValueError(f"Unknown template: {template}")

    if template == "hero":
        TEMPLATES[template](draw, **text_data, avatar=avatar)
    elif template in ["pros","cons"]:
        TEMPLATES[template](draw, **text_data, icons=icons)
    else:
        TEMPLATES[template](draw, **text_data)

    # Apply overlay and add layered text
    img = apply_overlay(img, text_data)

    output_path = OUTPUT_DIR / f"{output_name}.{IMAGE_FORMAT.lower()}"
    img.convert("RGB").save(output_path, IMAGE_FORMAT)
    print(f"Generated: {output_path} ({category} + overlay + text)")
    return output_path

# -------------------------------------------------
# Generate images for a blog post
# -------------------------------------------------
def generate_images_for_post(post: dict) -> list[Path]:
    created = []
    title = post.get("title","Untitled")
    slug = post.get("slug","post")

    created.append(
        generate_image(
            template="hero",
            text_data={"title": title, "subtitle":"Practical guide & insights"},
            output_name=f"{slug}-hero"
        )
    )

    for idx, section in enumerate(list(post.get("sections",{}).keys())[:2]):
        created.append(
            generate_image(
                template="section",
                text_data={"heading": section},
                output_name=f"{slug}-section-{idx+1}"
            )
        )

    if "pros" in post:
        created.append(
            generate_image(
                template="pros",
                text_data={"items": post["pros"]},
                output_name=f"{slug}-pros"
            )
        )
    if "cons" in post:
        created.append(
            generate_image(
                template="cons",
                text_data={"items": post["cons"]},
                output_name=f"{slug}-cons"
            )
        )

    return created
