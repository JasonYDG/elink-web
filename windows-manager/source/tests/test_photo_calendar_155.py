"""UI byte oracle, direct commit failures, crop bounds and unchanged hardware foundation."""
import datetime,struct,unittest,json,hashlib
from pathlib import Path
from test_photo_calendar import PhotoMachine
from test_firmware import BASE,STATE,FIRMWARE_DIR,ROOT
from protocol import image_packets
from lunar import lunar_fields
from photo_calendar import date_column,next_term,TERM_SECONDS
from render import photo_calendar_frame,frame_png
from builtin_gallery import native,gallery

class Photo155(unittest.TestCase):
    def ready(self,day):
        m=PhotoMachine();m.draw(year=day.year,month=day.month,day=day.day,weekday=(day.weekday()+1)%7,force=128);m.finish()
        ly,lm,ld=lunar_fields(day)
        for off,value in ((16,ly),(20,lm),(24,ld-1)):m.uc.mem_write(BASE+0xdd98+off,struct.pack('<I',value))
        return m
    def test_real_compiled_column_matches_host_every_byte(self):
        # Today, next term, a two-digit countdown, year change, leap month and leap day.
        for day in map(datetime.date.fromisoformat,('2026-10-18','2026-10-23','2026-10-24','2027-01-01','2025-08-20','2024-02-29')):
            m=self.ready(day);source=native(gallery()[0]['path'])['frame'];frame=photo_calendar_frame(source,63)['frame']
            before=m.status()['display_generation']
            for p in list(image_packets(frame,55,128))[:-1]:m.cmd(p)
            m.cmd(b'\x9c\x03');self.assertEqual(m.status()['error'],0);m.finish()
            actual=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
            plate=date_column(day)['frame'];expected=bytearray(frame)
            for off in (0,4000):expected[off:off+1216]=plate[off:off+1216]
            self.assertEqual(actual,bytes(expected),day)
            self.assertEqual(m.status()['display_generation'],before+1)
            self.assertEqual(m.flash_events,[])
            if day==datetime.date(2026,10,18):
                (FIRMWARE_DIR/'photo-calendar-preview.png').write_bytes(frame_png(actual))
                (FIRMWARE_DIR/'photo-calendar-preview.bin').write_bytes(actual)
        self.assertEqual(next_term(datetime.date(2026,10,18)),('霜降','5天后'))
        self.assertEqual(next_term(datetime.date(2026,10,23)),('霜降','今日'))
        baseline=(ROOT/'source/reference/hmclock-bwr-baseline-app.bin').read_bytes()
        self.assertEqual(struct.unpack_from('<24I',baseline,0x7d6c),TERM_SECONDS)
    def test_direct_commit_never_displays_incomplete_bad_checksum_or_busy_frame(self):
        m=self.ready(datetime.date(2026,10,18));frame=bytes(8000);packets=list(image_packets(frame,8,128))
        m.cmd(packets[0]);m.cmd(packets[1]);before=m.status()['display_generation'];m.cmd(b'\x9c\x03')
        self.assertEqual(m.status()['error'],1);self.assertEqual(m.status()['display_mode'],1)
        for p in packets[2:-1]:m.cmd(p)
        m.uc.mem_write(STATE+16,b'\x01\x00');m.cmd(b'\x9c\x03');self.assertEqual(m.status()['error'],1)
        self.assertEqual(m.status()['display_generation'],before)
        m.uc.mem_write(STATE+16,bytes(2));m.uc.mem_write(STATE+8,b'\x01');m.cmd(b'\x9c\x03');self.assertEqual(m.status()['error'],2)
        m.uc.mem_write(STATE+8,b'\x00');m.cmd(b'\x9c\x03');m.finish();self.assertEqual(m.status()['display_generation'],before+1)
    def test_horizontal_crop_bounds_and_exact_native_pixels(self):
        frame=bytes(i%256 for i in range(8000))
        for start in (0,42,84):
            cropped=photo_calendar_frame(frame,start)['frame']
            for plane in (0,4000):
                for x in range(174):self.assertEqual(cropped[plane+(249-x)*16:plane+(250-x)*16],frame[plane+(249-min(start,76)-x)*16:plane+(250-min(start,76)-x)*16])
        for x in (-1,85,1.5,True,'42',None):
            with self.assertRaises(ValueError):photo_calendar_frame(frame,x)
    def test_only_application_type_and_render_regions_change_since_155(self):
        old=(ROOT/'build/firmware-1.5.5/elink-bwr-1.5.5-app.bin').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),'de0309a79c82fd88297a6717e6e3cccf51282e4e6a98b936fa6c477c11669bb4')
        after=json.loads((FIRMWARE_DIR/'manifest.json').read_text())
        new=(FIRMWARE_DIR/('elink-bwr-'+after['version']+'-app.bin')).read_bytes()
        # These are application render/font sections, plus individual application call relocations.
        allowed=[(0x2cc4,0x31c8),(0x7eb4,0x8500),(0x8600,0xa46c),(0xa48c,0xc2a0),(0xc3c4,0xd2b0),(0xe2f0,0xe2f4)]
        before=json.loads((ROOT/'build/firmware-1.5.5/manifest.json').read_text())
        from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
        calls={0x2274:'product_boot_battery',0xde26:'product_sync_valid',0xdf16:'product_view',0xdf2c:'product_control',0xe12c:'product_refresh',0xe13e:'product_finish',0xe172:'product_minute_tick'}
        for off,name in calls.items():
            allowed.append((off,off+4))
            for raw,meta in ((old,before),(new,after)):
                address=BASE+off if off<0xddd4 else int(meta['runtime_address'],16)+off-int(meta['runtime_load_offset'],16)
                call=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(raw[off:off+4],address))
                self.assertEqual(len(call),1);self.assertEqual(call[0].mnemonic,'bl')
                target=BASE+0x31c8 if name=='product_minute_tick' and name not in meta['product_symbols'] else int(meta['product_symbols'][name],16)&~1
                self.assertEqual(int(call[0].op_str.lstrip('#'),16),target)
        allowed.append((0xe0fc,0xe100))
        for raw,meta in ((old,before),(new,after)):
            self.assertEqual(struct.unpack_from('<I',raw,0xe0fc)[0],int(meta['product_symbols']['product_caps'],16))
        self.assertEqual(before['labels'],after['labels']);self.assertEqual(len(old),len(new))
        self.assertEqual(before['runtime_bytes'],after['runtime_bytes'])
        differences=[i for i,(a,b) in enumerate(zip(old,new)) if a!=b]
        self.assertFalse([hex(i) for i in differences if not any(a<=i<b for a,b in allowed)])
        # Every byte outside the exact application spans is covered, including boot/reset,
        # BLE, native SPI and panel drivers, CRC table, waveform and OTA code.
        for i in range(len(new)):
            if not any(a<=i<b for a,b in allowed):self.assertEqual(old[i],new[i],hex(i))

if __name__=='__main__':unittest.main()
