"""Generate the month/day layout studies at the panel's native resolution."""
from functools import lru_cache
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "backend"))
from bitmap_fonts import INK, noto_path

OUT = SOURCE / "opendesign/mockups/large-date"
RED = (190, 0, 0)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


@lru_cache(maxsize=64)
def outline_ink(value, size):
    font = ImageFont.truetype(noto_path("noto_medium"), size)
    coverage = font.getmask(value, mode="L")
    mask = Image.frombytes("L", coverage.size, bytes(coverage))
    mask = mask.point(lambda level: 255 if level >= INK else 0, mode="1")
    return mask.crop(mask.getbbox())


def place(image, mask, x, y, color=BLACK):
    assert 0 <= x <= image.width - mask.width and 0 <= y <= image.height - mask.height
    image.paste(color, (x, y), mask)


def row(image, parts, center, baseline, gaps, color=BLACK):
    x = center - (sum(part.width for part in parts) + sum(gaps)) // 2
    for mask, gap in zip(parts, (*gaps, 0), strict=True):
        place(image, mask, x, baseline - mask.height, color)
        x += mask.width + gap


def centered(image, mask, center, bottom, color=BLACK):
    place(image, mask, center - mask.width // 2, bottom - mask.height, color)


def backgrounds():
    split = Image.new("RGB", (250, 122), WHITE)
    ImageDraw.Draw(split).rectangle((0, 0, 77, 121), fill=RED)
    halves = Image.new("RGB", split.size, WHITE)
    ImageDraw.Draw(halves).rectangle((0, 0, 124, 121), fill=RED)
    cards = Image.new("RGB", halves.size, WHITE)
    draw = ImageDraw.Draw(cards)
    for left in (0, 125):
        draw.rectangle((left + 5, 6, left + 119, 115), outline=BLACK, width=2)
        draw.rectangle((left + 5, 6, left + 119, 32), fill=RED)
    return {"b-split-outline": split, "d-halves-inline": halves, "f-cards": cards}


def layouts(month, day):
    frames = backgrounds()
    split, halves, cards = frames.values()
    for mask, y in ((outline_ink(str(month), 46), 30), (outline_ink("月", 23), 73)):
        place(split, mask, (78 - mask.width) // 2, y, WHITE)
    row(split, (outline_ink(str(day), 112), outline_ink("日", 20)), 164, 104, (6,))
    for left, value, unit in ((0, month, "月"), (125, day, "日")):
        center = left + 62
        number = str(value)
        color = WHITE if left == 0 else BLACK
        row(halves, (outline_ink(number, 80), outline_ink(unit, 21)), center, 91, (5,), color)
        centered(cards, outline_ink(unit, 21), center, 29, WHITE)
        centered(cards, outline_ink(number, 82), center, 105)
    return frames


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for month, day, suffix in ((11, 18, ""), (3, 28, "-03-28")):
        for name, image in layouts(month, day).items():
            image.save(OUT / (name + suffix + ".png"))
