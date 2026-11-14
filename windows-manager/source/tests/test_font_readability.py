"""Native 250x122 text geometry: visible cap height, gaps, counters and font slots."""
from pathlib import Path
import struct,unittest
from PIL import Image
from bitmap_fonts import cells,fallback_cells,text_mask,native_font
from test_firmware import ROOT,FIRMWARE_DIR


def counters(mask):
    white={(x,y) for y in range(mask.height) for x in range(mask.width) if not mask.getpixel((x,y))};areas=[]
    while white:
        todo=[white.pop()];area=0;border=False
        while todo:
            x,y=todo.pop();area+=1;border|=x in (0,mask.width-1) or y in (0,mask.height-1)
            for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if p in white:white.remove(p);todo.append(p)
        if not border:areas.append(area)
    return sorted(areas)


def native_cells(raw,base,height):
    result={}
    for i in range(struct.unpack_from('<H',raw,base)[0]):
        code,offset=struct.unpack_from('<HH',raw,base+2+i*4);p=base+offset
        advance,w,h,bx,by=struct.unpack_from('<BBBbb',raw,p);mask=Image.new('1',(advance,height))
        for y in range(h):
            for x in range(w):
                if raw[p+5+y*((w+7)//8)+x//8]&(128>>(x%8)):mask.putpixel((bx+x,by+y),1)
        result[chr(code)]=mask
    return result


class FontReadability(unittest.TestCase):
    def test_small_digits_fill_the_requested_height_and_fit_the_real_columns(self):
        for size,minimum in ((12,11),(14,13),(15,14),(18,17)):
            for ch,cell in cells('0123456789',size).items():
                box=cell.getbbox();self.assertGreaterEqual(box[3]-box[1],minimum,(size,ch))
        self.assertLessEqual(12+text_mask('2026/11/13',14).width,96)
        self.assertLessEqual(218+text_mask('100%',12).width,250)
        self.assertLess(20+text_mask('AA:AA:AA:AA:AA:AA',12).width,176)
        self.assertLessEqual(162+text_mask('2026/11/13',14).width,250)
        self.assertLessEqual(text_mask('闰八月廿五',12).width,76)
        for n in range(17):self.assertLessEqual(36+text_mask(str(n)+'天后',12).width,76)
        self.assertLessEqual(208+text_mask('待提醒',12).width,250)
        self.assertLessEqual(text_mask('早餐后服…',16).width,72)
        for size in (12,14,16,18,20):
            for cell in cells('ｱ｡…，龘',size).values():
                self.assertEqual(cell.height,size)
                box=cell.getbbox()
                if box:self.assertLessEqual(box[2],cell.width)

    def test_small_ascii_uses_the_native_bold_bitmap_source(self):
        for size in (12,14,15,16,17,18,20):
            original=fallback_cells('0123456789:/%AM',14)
            for ch,cell in cells(''.join(original),size).items():
                source=original[ch];box=source.getbbox()
                crop=source.crop((0,min(2,box[1]),8,max(12,box[3])))
                enlarged=crop.resize((8,min(size,max(crop.height,size-1))),Image.Resampling.NEAREST)
                expected=Image.new('1',cell.size);expected.paste(enlarged,((cell.width-8)//2,(size-enlarged.height)//2))
                self.assertEqual(cell.tobytes(),expected.tobytes(),(size,ch))

    def test_compiled_bold_glyphs_fit_their_slots_and_keep_critical_counters_open(self):
        old=(ROOT/'build/firmware-1.5.15-release/elink-bwr-1.5.15-app.bin').read_bytes()
        import json
        meta=json.loads((FIRMWARE_DIR/'manifest.json').read_text('utf-8'))
        current=(FIRMWARE_DIR/f'elink-bwr-{meta["version"]}-app.bin').read_bytes()
        for base,height,limit in ((0x7eb4,12,1612),(0x90a4,14,604),(0xc2a0,15,292),(0xa48c,18,4340)):
            before=native_cells(old,base,height);after=cells(''.join(before),height)
            compiled=native_cells(current,base,height)
            self.assertEqual(set(compiled),set(after))
            self.assertLessEqual(len(native_font(''.join(before),height)),limit)
            for ch in before:
                self.assertEqual(compiled[ch].size,after[ch].size,(height,ch))
                self.assertEqual(compiled[ch].tobytes(),after[ch].tobytes(),(height,ch))
            ink=lambda glyphs:sum(sum(bool(p) for p in cell.get_flattened_data()) for cell in glyphs.values())
            self.assertGreater(ink(after),ink(before)*1.25,height)
            for ch,minimum in (('0',1),('8',2),('B',2),('日',2),('月',1)):
                if ch in after:self.assertGreaterEqual(len(counters(after[ch])),minimum,(height,ch))

    def test_numeric_and_native_cjk_vertical_strokes_are_two_pixels_wide(self):
        from product_build import REQUIRED,SMALL_REQUIRED
        for size in (12,14,15,16,17,18,20):
            chars='0123456789'
            if size==12:chars+=''.join(ch for ch in SMALL_REQUIRED if ord(ch)>127)
            if size==14:chars+='星期日一二三四五六'
            if size==18:chars+=''.join(ch for ch in REQUIRED if ord(ch)>127)
            if size==16:chars+='早餐后服药今日任务提醒'
            for ch,cell in cells(chars,size).items():
                for y in range(cell.height):
                    run=0
                    for x in range(cell.width+1):
                        if x<cell.width and cell.getpixel((x,y)):run+=1
                        elif run:
                            self.assertGreaterEqual(run,2,(size,ch,x,y))
                            run=0

    def test_large_digit_tables_and_all_code_remain_identical_to_1514(self):
        old=(ROOT/'build/firmware-1.5.14-repro/elink-bwr-1.5.14-app.bin').read_bytes()
        import json
        meta=json.loads((FIRMWARE_DIR/'manifest.json').read_text('utf-8'));new=(FIRMWARE_DIR/f'elink-bwr-{meta["version"]}-app.bin').read_bytes()
        for lo,hi in ((0xb780,0xba00),(0xc3c4,0xc8a4)):self.assertEqual(old[lo:hi],new[lo:hi])
        functions=json.loads((ROOT/'build/firmware-1.5.14-repro/product-functions.json').read_text('utf-8'))
        self.assertEqual(functions,json.loads((FIRMWARE_DIR/'product-functions.json').read_text('utf-8')))
        for name,f in functions.items():
            offset=f['address']-0x7fc0000;self.assertEqual(old[offset:offset+f['bytes']],new[offset:offset+f['bytes']],name)


if __name__=='__main__':unittest.main()
