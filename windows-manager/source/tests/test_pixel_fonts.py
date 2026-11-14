"""Original pixel-font strokes, compiled glyph decoding and exact hardware preservation."""
import hashlib,json,struct,unittest
from unittest.mock import patch
from PIL import Image
from test_firmware import ROOT,FIRMWARE_DIR,BASE
from test_product_ui import ProductMachine
from bitmap_fonts import cells,fallback_cells,text_mask


def pixel_asset_ranges(meta):
    """Only declared font slots and the fixed-size boot illustration may change."""
    asset=int(meta['state_file_offset'],16)+32
    assert meta['boot_asset_bytes']==1697
    return [(0x7eb4,0x8500),(0x90a4,0x9300),(0xa48c,0xb580),
            (0xb780,0xba00),(0xc2a0,0xc8a4),(asset,asset+1697)]


class PixelFonts(unittest.TestCase):
    def test_original_pixel_strokes_and_only_integer_enlargement(self):
        with patch('bitmap_fonts.ImageFont.truetype',side_effect=AssertionError('Outline rasterization is forbidden')):
            # Small glyphs have separate ink-height/counter checks; large glyphs stay exact.
            for height,native,scale in ((24,12,2),(28,12,2),(32,16,2),(40,16,2),(64,16,4)):
                value='Aa09/%…今日天后农历星期'
                source=fallback_cells(value,native)
                for ch,actual in cells(value,height).items():
                    if height==40 and ch.isascii():continue # Boot title has its own bold-cap regression.
                    original=source[ch];zoom=original.resize((original.width*scale,native*scale),Image.Resampling.NEAREST)
                    width=original.width*height//native
                    expected=Image.new('1',(width,height));expected.paste(zoom,((width-zoom.width)//2,(height-zoom.height)//2))
                    self.assertEqual(actual.size,expected.size)
                    self.assertEqual(actual.tobytes(),expected.tobytes(),(height,ch))
            for height,native,scale,width in ((44,12,4,27),):
                for ch in '0123456789':
                    original=fallback_cells(ch,native)[ch];original=original.crop(original.getbbox())
                    zoom=original.resize((original.width*scale,original.height*scale),Image.Resampling.NEAREST)
                    expected=Image.new('1',(width,height));expected.paste(zoom,((width-zoom.width)//2,(height-zoom.height)//2))
                    self.assertEqual(cells(ch,height)[ch].tobytes(),expected.tobytes(),(height,ch))
            with self.assertRaises(ValueError):text_mask('\U0010ffff',12)

    def test_real_clock_decoder_uses_new_pixel_digits_inside_the_original_minute_window(self):
        for hour,minute in ((0,0),(9,58),(12,34),(23,59)):
            m=ProductMachine();actual=m.draw(h=hour,minute=minute,force=128)
            expected=Image.new('1',(250,122))
            for label,x,y in ((f'{hour%12 or 12:02}',11,25),(':',111,29),(f'{minute:02}',139,25)):
                mask=text_mask(label,66);expected.paste(mask,(x,y))
            for y in range(24,96):
                for x in range(11,241):
                    pos=(249-x)*16+y//8;bit=128>>(y%8)
                    self.assertEqual(not bool(actual[pos]&bit),bool(expected.getpixel((x,y))),(hour,minute,x,y))
            m.finish()

    def test_only_font_assets_two_ui_functions_version_and_id_change_from_verified_1513(self):
        baseline=ROOT/'build/firmware-1.5.13-font-baseline'
        before=json.loads((baseline/'manifest.json').read_text());after=json.loads((FIRMWARE_DIR/'manifest.json').read_text())
        old=(baseline/'elink-bwr-1.5.13-app.bin').read_bytes();new=(FIRMWARE_DIR/f'elink-bwr-{after["version"]}-app.bin').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),'b6347e11f4a6c305d5b6540e61e71b564bbff2d623d26677205064f6be443c75')
        self.assertEqual(len(old),len(new))
        for key in ('labels','runtime_address','runtime_load_offset','runtime_bytes','helper_address','helper_bytes','state_address','state_file_offset','boot_identity_address','boot_identity_bytes','product_symbols'):
            self.assertEqual(before[key],after[key],key)
        ranges=pixel_asset_ranges(after);version=old.index(b'V1.5.13\0')
        self.assertEqual(new[version:version+8],('V'+after['version']+'\0').encode())
        ranges.extend(((version,version+8),(int(after['state_file_offset'],16)+28,int(after['state_file_offset'],16)+32)))
        functions=json.loads((baseline/'product-functions.json').read_text())
        self.assertEqual(functions,json.loads((FIRMWARE_DIR/'product-functions.json').read_text()))
        for name in ('product_battery','product_boot_battery'):
            f=functions[name];ranges.append((f['address']-BASE,f['address']-BASE+f['bytes']))
        for offset,(a,b) in enumerate(zip(old,new)):
            if a!=b:self.assertTrue(any(lo<=offset<hi for lo,hi in ranges),hex(offset))
        for name,function in functions.items():
            if name in ('product_battery','product_boot_battery'):continue
            offset=function['address']-BASE;size=function['bytes']
            self.assertEqual(old[offset:offset+size],new[offset:offset+size],name)


if __name__=='__main__':unittest.main()
