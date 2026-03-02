from PIL import ImageDraw, ImageFont, Image, ImageFilter
from .image_config import *
import random

# ----------------------
# Text drawing utility with overlay & shadow
# ----------------------
def draw_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, xy: tuple[int,int], max_width: int, shadow=True, overlay=True):
    """
    Draw wrapped text within max_width with optional shadow & overlay.
    """
    # Wrap text
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

    # Compute total height of all lines
    total_height = 0
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        total_height += bbox[3] - bbox[1] + 5

    # Draw single overlay rectangle behind entire block
    if overlay:
        draw.rectangle((x0-10, y0, x0 + max_width, y0 + total_height), fill=(0,0,0,120))

    # Draw each line with optional shadow
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        h = bbox[3] - bbox[1]
        if shadow:
            draw.text((x0+2, y0+2), line, font=font, fill=(0,0,0))
        draw.text((x0, y0), line, font=font, fill=TEXT_COLOR)
        y0 += h + 5

    return y0

# ----------------------
# Dynamic background generator
# ----------------------
def generate_background(width: int, height: int, style: str="gradient") -> Image.Image:
    img = Image.new("RGB", (width, height), (255,255,255))
    draw = ImageDraw.Draw(img)

    if style == "gradient":
        start_color = tuple(random.randint(100,200) for _ in range(3))
        end_color = tuple(random.randint(50,150) for _ in range(3))
        for y in range(height):
            ratio = y / height
            color = tuple(int(start_color[i]*(1-ratio) + end_color[i]*ratio) for i in range(3))
            draw.line([(0,y),(width,y)], fill=color)
    elif style == "pattern":
        stripe_width = 50
        colors = [(200,200,255),(220,220,240)]
        for x in range(-height, width, stripe_width):
            draw.polygon([(x,0),(x+stripe_width,0),(x+height+stripe_width,height),(x+height,height)], fill=random.choice(colors))
    elif style == "noise":
        import numpy as np
        arr = np.random.randint(200,255,(height,width,3),dtype=np.uint8)
        img = Image.fromarray(arr)
    else:
        img = Image.new("RGB",(width,height),(150,150,150))
    return img

# ----------------------
# Templates
# ----------------------
def hero_template(draw: ImageDraw.Draw, title: str, subtitle: str, avatar: Image.Image=None):
    if avatar:
        avatar = avatar.resize((128,128))
        draw.bitmap((IMAGE_WIDTH-160,60), avatar)
    draw_text(draw, title, draw.font_title, (60,180), IMAGE_WIDTH-120)
    draw_text(draw, subtitle, draw.font_subtitle, (60,300), IMAGE_WIDTH-120)

def section_template(draw: ImageDraw.Draw, heading: str, icon: Image.Image=None):
    if icon:
        icon = icon.resize((64,64))
        draw.bitmap((60,260), icon)
    draw_text(draw, heading, draw.font_title, (60+70 if icon else 60, 260), IMAGE_WIDTH-120)

def pros_template(draw: ImageDraw.Draw, items: list[str], icons: list[Image.Image]=None):
    y = 180
    icon_size = 32
    for i, item in enumerate(items):
        if icons and i < len(icons):
            icon = icons[i].resize((icon_size,icon_size))
            draw.bitmap((60,y), icon)
        else:
            draw.ellipse((60,y,60+icon_size,y+icon_size), fill=(34,139,34))
        draw_text(draw, item, draw.font_subtitle, (110,y), IMAGE_WIDTH-160)
        y += icon_size + 20

def cons_template(draw: ImageDraw.Draw, items: list[str], icons: list[Image.Image]=None):
    y = 180
    icon_size = 32
    for i, item in enumerate(items):
        if icons and i < len(icons):
            icon = icons[i].resize((icon_size,icon_size))
            draw.bitmap((60,y), icon)
        else:
            draw.ellipse((60,y,60+icon_size,y+icon_size), fill=(220,20,60))
        draw_text(draw, item, draw.font_subtitle, (110,y), IMAGE_WIDTH-160)
        y += icon_size + 20

# ----------------------
# Template map
# ----------------------
TEMPLATES = {
    "hero": hero_template,
    "section": section_template,
    "pros": pros_template,
    "cons": cons_template
}
