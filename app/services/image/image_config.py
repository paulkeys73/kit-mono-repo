from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "generated"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_WIDTH = 1200
IMAGE_HEIGHT = 628  # OG-friendly
IMAGE_FORMAT = "PNG"
BACKGROUND_COLOR = (245, 245, 245)
TEXT_COLOR = (30, 30, 30)

FONT_PATH = BASE_DIR / "fonts" / "Inter-Bold.ttf"  # optional
FONT_SIZE_TITLE = 64
FONT_SIZE_SUBTITLE = 32
