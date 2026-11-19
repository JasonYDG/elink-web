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
MONTHS_EN = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
WEEKDAYS_EN = "SUN MON TUE WED THU FRI SAT".split()
ENGLISH_LABELS = [(word, 30, 53) for word in MONTHS_EN] + [(word, 20, 90) for word in WEEKDAYS_EN]


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


def row(image, parts, center, baseline, gaps, colors):
    x = center - (sum(part.width for part in parts) + sum(gaps)) // 2
    for mask, gap, color in zip(parts, (*gaps, 0), colors, strict=True):
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


def english_letters(word, size, bottom):
    masks = [outline_ink(letter, size) for letter in word]
    x = 39 - (sum(mask.width for mask in masks) + 4) // 2
    for mask in masks:
        yield mask, x, bottom - mask.height
        x += mask.width + 2


def english_date(month, day, weekday, day_color=BLACK):
    image = backgrounds()["b-split-outline"]
    for label in (ENGLISH_LABELS[month-1], ENGLISH_LABELS[12+weekday]):
        for mask, x, y in english_letters(*label):
            place(image, mask, x, y, WHITE)
    centered(image, outline_ink(str(day), 112), 164, 104, day_color)
    return image


def layouts(month, day, day_color=BLACK):
    frames = backgrounds()
    split, halves, cards = frames.values()
    for mask, y in ((outline_ink(str(month), 46), 30), (outline_ink("月", 23), 73)):
        place(split, mask, (78 - mask.width) // 2, y, WHITE)
    row(split, (outline_ink(str(day), 112), outline_ink("日", 20)), 164, 104, (6,), (day_color, BLACK))
    for left, value, unit in ((0, month, "月"), (125, day, "日")):
        center = left + 62
        number = str(value)
        colors = (WHITE, WHITE) if left == 0 else (day_color, BLACK)
        row(halves, (outline_ink(number, 80), outline_ink(unit, 21)), center, 91, (5,), colors)
        centered(cards, outline_ink(unit, 21), center, 29, WHITE)
        centered(cards, outline_ink(number, 82), center, 105, day_color if left else BLACK)
    return frames


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for month, day, weekday, suffix in ((11, 18, 3, ""), (3, 28, 6, "-03-28")):
        for color, ink in ((BLACK, ""), (RED, "-red")):
            frames = layouts(month, day, color)
            frames["b-english"] = english_date(month, day, weekday, color)
            for name, image in frames.items():
                image.save(OUT / (name + ink + suffix + ".png"))
