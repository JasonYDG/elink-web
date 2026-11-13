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

    def test_small_ascii_is_only_enlarged_source_pixels_without_added_ink(self):
        for size in (12,14,15,16,17,18,20):
            original=fallback_cells('0123456789:/%AM',12)
            for ch,cell in cells(''.join(original),size).items():
                source=original[ch];box=source.getbbox()
                crop=source.crop((0,min(2,box[1]),max(5,box[2]),max(10,box[3])))
                enlarged=crop.resize((max(crop.width,cell.width-2),max(crop.height,size-1)),Image.Resampling.NEAREST)
                expected=Image.new('1',cell.size);expected.paste(enlarged,(1 if size>=16 else 0,(size-enlarged.height)//2))
                self.assertEqual(cell.tobytes(),expected.tobytes(),(size,ch))

    def test_every_native_small_glyph_keeps_its_counters_and_fits_its_original_slot(self):
        old=(ROOT/'build/firmware-1.5.14-repro/elink-bwr-1.5.14-app.bin').read_bytes()
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
                a,b=counters(before[ch]),counters(after[ch])
                self.assertEqual(len(a),len(b),(height,ch))
                self.assertLessEqual(b.count(1),a.count(1),(height,ch))
                self.assertGreaterEqual(sum(bool(p) for p in after[ch].get_flattened_data()),sum(bool(p) for p in before[ch].get_flattened_data()),(height,ch))

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
