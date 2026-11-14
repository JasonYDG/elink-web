"""Requested type changes measured in real compiled 250x122 buffers."""
import struct,unittest,sys
from PIL import Image
from bitmap_fonts import cells,text_mask
from test_firmware import ROOT,BASE,STATE
from test_product_ui import ProductMachine,frame_matches
from test_font_readability import native_cells,counters
sys.path.insert(0,str(ROOT/'source/tools'))
from preview_firmware import frame_image


class UiTypography(unittest.TestCase):
    def test_boot_bold_title_is_larger_and_shares_the_version_bottom(self):
        m=ProductMachine();m.run(BASE+0x2224)
        raw=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000));im=frame_image(raw)
        def box(rect,color):
            mask=Image.new('1',im.size)
            for y in range(rect[1],rect[3]):
                for x in range(rect[0],rect[2]):
                    if im.getpixel((x,y))==color:mask.putpixel((x,y),1)
            return mask.getbbox()
        logo=box((20,18,140,56),(0,0,0));version=box((148,18,244,56),(190,0,0))
        self.assertEqual(logo[3]-logo[1],24);self.assertGreaterEqual(logo[2]-logo[0],100)
        self.assertEqual(logo[3],version[3]);self.assertEqual(logo[3],44)
        old=Image.open(ROOT/'releases/firmware-1.5.17-test/previews/default.png').convert('RGB')
        ink=[y for y in range(18,56) for x in range(20,140) if old.getpixel((x,y))==(0,0,0)]
        self.assertEqual(max(ink)-min(ink)+1,20)
        self.assertLessEqual(19+text_mask('BWR 2.13 / 250x122',18).width,244)

    def test_native_header_battery_text_matches_both_icon_edges(self):
        for mode in (0,3):
            for adc,label in ((1706,'100%'),(0,'--%')):
                m=ProductMachine();m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',adc));m.uc.mem_write(STATE+7,bytes([mode]))
                frame=m.draw(force=128);self.assertTrue(frame_matches(frame,label,12,218,4))
                im=frame_image(frame);ys=[y for y in range(20) for x in range(218,250) if im.getpixel((x,y))==(0,0,0)]
                self.assertEqual((min(ys),max(ys)),(4,14))
                for y in (4,14):
                    for x in range(194,211):self.assertEqual(im.getpixel((x,y)),(0,0,0))

    def test_lcd_digits_join_continuously_and_keep_open_counters(self):
        from product_build import clock_digits
        self.assertEqual(ProductMachine().b[0xc3c4:0xc8a4],clock_digits(b''),'Every compiled LCD glyph must match the fixed bitmap table')
        probes=((25,5),(42,18),(42,45),(25,60),(8,45),(8,18),(25,32))
        expected=('1111110','0110000','1101101','1111001','0110011','1011011','1011111','1110000','1111111','1111011')
        for n,pattern in enumerate(expected):
            mask=cells(str(n),66)[str(n)];self.assertEqual(mask.size,(50,66))
            self.assertEqual(''.join('1' if mask.getpixel(p) else '0' for p in probes),pattern)
            self.assertEqual(len(counters(mask.point(lambda p:0 if p else 255))),1,'Each digit must form one connected ink shape')
        self.assertEqual(len(counters(cells('0',66)['0'])),1)
        self.assertEqual(len(counters(cells('8',66)['8'])),2)
        for ch in ('0','8'):
            for x in (*range(6,10),*range(40,44)):self.assertTrue(cells(ch,66)[ch].getpixel((x,33)))
        self.assertEqual(cells(':',66)[':'].width,28)

    def test_snow_hint_keeps_rain_dots_and_lower_bars_separate(self):
        snow=native_cells(ProductMachine().b,0xa48c,18)['雪']
        self.assertEqual(snow.size,(18,18));self.assertEqual(snow.getbbox(),(1,1,17,18))
        for y in (6,8):
            for x in (4,5,11,12):self.assertTrue(snow.getpixel((x,y)))
        for y in (5,7,9,12,15):
            for x in (4,5,11,12):self.assertFalse(snow.getpixel((x,y)),(x,y))
        for y in (10,11,13,14,16,17):
            for x in range(4,13):self.assertTrue(snow.getpixel((x,y)))

    def test_calendar_thin_upper_horizontals_are_two_rows_and_eight_has_two_counters(self):
        raw=(ROOT/'build/firmware-1.5.17-release/elink-bwr-1.5.17-app.bin').read_bytes();old=native_cells(raw,0xa48c,18)
        glyphs=native_cells(ProductMachine().b,0xa48c,18)
        for ch in '午年六':
            current=glyphs[ch]
            self.assertEqual(current.getbbox(),old[ch].getbbox());bars=0
            for y in range(9):
                run=[]
                for x in range(19):
                    if x<18 and old[ch].getpixel((x,y)):run.append(x)
                    else:
                        if len(run)>=10:
                            bars+=1
                            for xx in run:self.assertTrue(current.getpixel((xx,y+1)),(ch,xx,y))
                        run=[]
            self.assertGreater(bars,0,ch)
        eight=glyphs['8'];self.assertEqual(eight.getbbox(),(1,1,11,17));self.assertEqual(eight.width,12)
        self.assertEqual(len(counters(eight)),2)
        for days in range(17):self.assertLessEqual(text_mask(str(days)+'天后',18).width,73)


if __name__=='__main__':unittest.main()
