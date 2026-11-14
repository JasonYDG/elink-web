"""Every solar-term glyph: real compiled pixels, intact strokes, separated voids."""
import json,struct,unittest
from collections import deque
from PIL import Image
from bitmap_fonts import fallback_cells,solar_term_cells
from photo_calendar import TERMS
from test_firmware import ROOT,BASE
from test_product_ui import ProductMachine
from test_font_readability import native_cells


def regions(points,diagonal=False):
    remaining=set(points);result=[]
    offsets=[(dx,dy) for dy in (-1,0,1) for dx in (-1,0,1) if (dx or dy) and (diagonal or abs(dx)+abs(dy)==1)]
    while remaining:
        first=remaining.pop();todo=deque([first]);group={first}
        while todo:
            x,y=todo.popleft()
            for dx,dy in offsets:
                p=(x+dx,y+dy)
                if p in remaining:remaining.remove(p);todo.append(p);group.add(p)
        result.append(group)
    return result


class SolarTermFonts(unittest.TestCase):
    def test_all_twenty_four_names_match_the_native_table_and_cover_twenty_seven_glyphs(self):
        m=ProductMachine();names=[]
        for address in struct.unpack_from('<24I',m.b,0x7dcc):
            start=address-BASE;names.append(m.b[start:].split(b'\0',1)[0].decode('utf-8'))
        self.assertEqual(names,TERMS);self.assertEqual(len(TERMS),24)
        self.assertEqual(set(solar_term_cells()),set(''.join(TERMS)));self.assertEqual(len(solar_term_cells()),27)

    def test_every_compiled_term_glyph_keeps_source_strokes_separate_strokes_and_counters(self):
        m=ProductMachine();compiled=native_cells(m.b,0xa48c,18)
        all_pixels={(x,y) for y in range(18) for x in range(18)}
        old=(ROOT/'build/firmware-1.5.19-final/elink-bwr-1.5.19-app.bin').read_bytes()
        previous=native_cells(old,0xa48c,18)
        for ch,expected in solar_term_cells().items():
            actual=compiled[ch];self.assertEqual(actual.size,(18,18));self.assertEqual(actual.tobytes(),expected.tobytes(),ch)
            ink={(x,y) for x,y in all_pixels if actual.getpixel((x,y))}
            self.assertTrue(any(all((x+dx,y+dy) in ink for dx,dy in ((0,0),(1,0),(0,1),(1,1))) for x,y in ink),ch+' needs reinforced main strokes')
            if ch=='雪':self.assertEqual(actual.tobytes(),previous[ch].tobytes());continue
            source=Image.new('1',(18,18));source.paste(fallback_cells(ch,16)[ch],(1,1))
            reference={(x,y) for x,y in all_pixels if source.getpixel((x,y))}
            self.assertTrue(reference<=ink,ch+' must not drop any original ink pixel')
            original_strokes=regions(reference,True);new_strokes=regions(ink,True)
            self.assertEqual(len(new_strokes),len(original_strokes),ch+' must not merge separate strokes')
            self.assertTrue(all(group&reference for group in new_strokes),ch+' must not add isolated dots')
            self.assertEqual(len(regions(ink)),len(original_strokes),ch+' must not rely on diagonal-only contacts')
            original_white=regions(all_pixels-reference);self.assertEqual(len(regions(all_pixels-ink)),len(original_white),ch+' must preserve whitespace topology')
            for hole in original_white:
                if not any(x in (0,17) or y in (0,17) for x,y in hole):self.assertGreaterEqual(len(hole-ink),min(2,len(hole)),ch+' counter must remain open')

    def test_non_term_main_glyphs_keep_the_previous_pixels(self):
        m=ProductMachine();old=(ROOT/'build/firmware-1.5.19-final/elink-bwr-1.5.19-app.bin').read_bytes()
        before=native_cells(old,0xa48c,18);after=native_cells(m.b,0xa48c,18)
        for ch in set(before)-set(solar_term_cells()):self.assertEqual(before[ch].tobytes(),after[ch].tobytes(),ch)


if __name__=='__main__':unittest.main()
