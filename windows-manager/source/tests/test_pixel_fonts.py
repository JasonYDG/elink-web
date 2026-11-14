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
            for height,native,width in ((44,32,27),):
                for ch in '0123456789':
                    source_ch='O' if ch=='0' else ch
                    original=fallback_cells(source_ch,native)[source_ch];original=original.crop(original.getbbox())
                    zoom=original.resize((20,32),Image.Resampling.NEAREST)
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

    def test_stroke_refresh_changes_only_verified_application_spans_and_hook_relocations(self):
        baseline=ROOT/'build/firmware-1.5.20-release'
        before=json.loads((baseline/'manifest.json').read_text());after=json.loads((FIRMWARE_DIR/'manifest.json').read_text())
        old=(baseline/'elink-bwr-1.5.20-app.bin').read_bytes();new=(FIRMWARE_DIR/f'elink-bwr-{after["version"]}-app.bin').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),'311f37be98b763694973c8192a37735b2d8921b0ab1930c67ce1b27e483c25f2')
        self.assertEqual(len(old),len(new))
        for key in ('labels','runtime_address','runtime_load_offset','runtime_bytes','helper_address','helper_bytes','state_address','state_file_offset','boot_identity_address','boot_identity_bytes'):
            self.assertEqual(before[key],after[key],key)
        self.assertEqual(new.count(('V'+after['version']+'\0').encode()),1)
        self.assertEqual(before['product_symbols']['product_boot_battery'],after['product_symbols']['product_boot_battery'])
        self.assertEqual(old[0x2248:0x2298],new[0x2248:0x2298],'Native startup hook stays byte-identical')
        asset=int(after['state_file_offset'],16)+32
        self.assertEqual(old[asset:asset+1697],new[asset:asset+1697])
        ranges=pixel_asset_ranges(after)+[(0x2cc4,0x31c8),(0x8600,0x90a4),(0x9300,0xa46c),
                                       (0xb580,0xb780),(0xba00,0xc2a0),(0xc8a4,0xd2b0),(0xe2f0,0xe2f4)]
        from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
        for off,name in {0xde26:'product_sync_valid',0xdf16:'product_view',0xdf2c:'product_control',
                         0xe12c:'product_refresh',0xe13e:'product_finish',0xe172:'product_minute_tick'}.items():
            ranges.append((off,off+4))
            address=int(after['runtime_address'],16)+off-int(after['runtime_load_offset'],16)
            call=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(new[off:off+4],address))
            self.assertEqual(len(call),1);self.assertEqual(call[0].mnemonic,'bl')
            self.assertEqual(int(call[0].op_str.lstrip('#'),16),int(after['product_symbols'][name],16)&~1)
        ranges.append((0xe0fc,0xe100))
        self.assertEqual(struct.unpack_from('<I',new,0xe0fc)[0],int(after['product_symbols']['product_caps'],16))
        for offset,(a,b) in enumerate(zip(old,new)):
            if a!=b:self.assertTrue(any(lo<=offset<hi for lo,hi in ranges),hex(offset))


if __name__=='__main__':unittest.main()
