"""Pack the approved native pixels into read-only glyphs in the OTA application."""
from itertools import groupby
from pathlib import Path
import struct
import sys

from PIL import ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from preview_large_date import ENGLISH_LABELS, backgrounds, english_letters, layouts


def spans(flags):
    for flag, items in groupby(enumerate(flags), lambda item: bool(item[1])):
        if flag:
            indices = [index for index, _ in items]
            yield indices[0], indices[-1] + 1


def pack_glyph(mask):
    out = bytearray()
    previous = []
    repeats = 0
    for y in range(mask.height):
        edges = [edge for span in spans(mask.getpixel((x, y)) for x in range(mask.width)) for edge in span]
        assert len(edges) in (2, 4, 6, 8) and edges[0] < 64
        if edges == previous and repeats < 45:
            repeats += 1
            continue
        if repeats:
            out.append(80 + repeats)
            repeats = 0
        delta = [x - p for x, p in zip(edges, previous)]
        if len(previous) == len(edges) <= 4 and all(abs(d) <= 1 for d in delta):
            out.append(sum((d + 1) * 3**i for i, d in enumerate(delta)))
        elif len(edges) <= 4:
            out.extend(((128 if len(edges) == 2 else 192) + edges[0], *edges[1:]))
        else:
            out.extend((126 if len(edges) == 6 else 127, *edges))
        previous = edges
    if repeats:
        out.append(80 + repeats)
    assert len(out) <= 255
    return bytes(out)


def build_atlas():
    glyphs = {}
    records = bytearray()
    for style, background in backgrounds().items():
        split = 78 if style == "b-split-outline" else 125
        for side, limit in enumerate((12, 31)):
            left, right = (0, split) if side == 0 else (split, 250)
            for value in range(1, limit + 1):
                frame = layouts(value, 1)[style] if side == 0 else layouts(1, value)[style]
                mask = ImageChops.difference(frame, background).convert("L")
                mask = mask.crop((left, 0, right, 122))
                stamps = bytearray()
                for top, bottom in spans(mask.getprojection()[1]):
                    band = mask.crop((0, top, mask.width, bottom))
                    for x, end in spans(band.getprojection()[0]):
                        piece = band.crop((x, 0, end, band.height))
                        box = piece.getbbox()
                        glyph = pack_glyph(piece.crop(box))
                        index = glyphs.setdefault(glyph, len(glyphs) + 1)
                        stamps.extend((index, left + x + box[0], top + box[1]))
                assert len(stamps) == (6 if value < 10 else 9)
                if side:
                    # The day unit is the first stamp on cards and the last on inline layouts.
                    unit = 0 if style == "f-cards" else len(stamps) - 3
                    for i in range(0, len(stamps), 3):
                        if i != unit:
                            stamps[i+2] |= 128  # The high bit of y marks a colorable day digit.
                records.extend(stamps)
    assert len(records) == 3 * 333
    for label in ENGLISH_LABELS:
        for mask, x, y in english_letters(*label):
            glyph = pack_glyph(mask)
            records.extend((glyphs.setdefault(glyph, len(glyphs) + 1), x, y))
    offset = len(records) + 3 * len(glyphs)
    for glyph in glyphs:
        records.extend(struct.pack('<HB', offset, len(glyph)))
        offset += len(glyph)
    return bytes(records) + b''.join(glyphs), len(glyphs)
