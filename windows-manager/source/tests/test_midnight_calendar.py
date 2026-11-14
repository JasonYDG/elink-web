"""Exercise the real native minute callback, including its noon/midnight0x80 flags."""
import struct,unittest,json,hashlib
from datetime import datetime
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_SP
from test_product_ui import ProductMachine,BASE,STATE,END
from test_firmware import ROOT,FIRMWARE_DIR
from lunar import lunar_fields

class NativeMinuteMachine(ProductMachine):
    def at(self,dt,mode=3):
        ly,lm,ld=lunar_fields(dt.date())
        for off,v in ((8,dt.year),(12,(dt.weekday()+1)%7),(16,ly),(20,lm),(24,ld-1)):
            self.uc.mem_write(BASE+0xdd98+off,struct.pack('<I',v))
        for off,v in ((28,dt.month-1),(32,dt.day-1),(36,dt.hour),(40,dt.minute),(44,dt.second)):
            self.uc.mem_write(BASE+0x104dc+off,struct.pack('<I',v))
        self.uc.mem_write(STATE+7,bytes([mode]));self.uc.mem_write(STATE+27,b'\x01')
        self.uc.reg_write(UC_ARM_REG_R0,128);self.uc.reg_write(UC_ARM_REG_LR,END|1)
        self.uc.emu_start(BASE+0x2cc5,END,count=2500000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==END
        self.finish()
        self.uc.mem_write(BASE+0x104dc+4,struct.pack('<I',1))
        self.uc.mem_write(BASE+0x104dc+44,struct.pack('<I',dt.second))
        self.uc.mem_write(BASE+0x124cc+72,b'\xff'*4)
        return self

    def tick(self):
        self.uc.reg_write(UC_ARM_REG_LR,END|1)
        self.uc.emu_start(BASE+0x25c1,END,count=5000000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==END
        assert self.uc.reg_read(UC_ARM_REG_SP)==BASE+0x1d000

class MidnightCalendar(unittest.TestCase):
    def test_native_noon_does_not_refresh_any_calendar_mode(self):
        for mode in (3,6,8):
            m=NativeMinuteMachine().at(datetime(2026,11,14,11,59,37),mode)
            commands=len(m.commands);generation=m.status()['display_generation'];old=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
            m.tick()
            self.assertEqual((m.word(BASE+0x104dc+36),m.word(BASE+0x104dc+40)),(12,0))
            self.assertEqual(m.word(BASE+0x104dc+32),13)
            self.assertFalse(m.status()['busy'],'Native noon0x80 is not a calendar date change')
            self.assertEqual(len(m.commands),commands);self.assertEqual(m.status()['display_generation'],generation)
            self.assertEqual(bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000)),old)

    def test_native_midnight_month_year_and_leap_boundaries_refresh_exactly_once(self):
        for start,end in ((datetime(2026,11,14,23,59,37),datetime(2026,11,15)),
                          (datetime(2026,11,30,23,59),datetime(2026,12,1)),
                          (datetime(2026,12,31,23,59),datetime(2027,1,1)),
                          (datetime(2024,2,28,23,59),datetime(2024,2,29)),
                          (datetime(2024,2,29,23,59),datetime(2024,3,1))):
            m=NativeMinuteMachine().at(start);generation=m.status()['display_generation'];m.commands.clear()
            m.tick();self.assertEqual((m.word(BASE+0xdd98+8),m.word(BASE+0x104dc+28),m.word(BASE+0x104dc+32),m.word(BASE+0x104dc+36)),(end.year,end.month-1,end.day-1,0))
            self.assertTrue(m.status()['busy']);m.finish()
            self.assertEqual(m.status()['display_generation'],generation+1)
            self.assertEqual(sum(c[0]==BASE+0x3c10 and c[1]==0x22 for c in m.commands),1)
            before=len(m.commands);m.tick();self.assertFalse(m.status()['busy']);self.assertEqual(len(m.commands),before)

    def test_calendar_still_allows_explicit_same_day_redraw_at_noon(self):
        m=NativeMinuteMachine().at(datetime(2026,11,14,12,0))
        generation=m.status()['display_generation'];m.cmd(b'\x9c\x01');self.assertTrue(m.status()['busy']);m.finish()
        self.assertEqual(m.status()['display_generation'],generation+1)

    def test_missed_midnight_refresh_retries_on_next_native_minute(self):
        m=NativeMinuteMachine().at(datetime(2026,11,14,23,59));generation=m.status()['display_generation']
        m.cmd(b'\x99\x3c\x01\x00') # An hourly clock setting must not postpone a calendar date update.
        m.uc.mem_write(STATE+8,b'\x01');m.tick();self.assertEqual(m.status()['display_generation'],generation)
        m.uc.mem_write(STATE+8,b'\x00');m.tick();self.assertTrue(m.status()['busy']);m.finish()
        self.assertEqual(m.status()['display_generation'],generation+1)

    def test_photo_calendar_midnight_updates_only_the_date_column(self):
        for mode in (6,8):
            m=NativeMinuteMachine().at(datetime(2026,11,14,23,59),mode)
            before=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
            generation=m.status()['display_generation'];m.tick();m.finish()
            after=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
            self.assertEqual(m.status()['display_generation'],generation+1)
            for plane in (0,4000):self.assertEqual(before[plane+1216:plane+4000],after[plane+1216:plane+4000])
            self.assertNotEqual(before[:1216],after[:1216])

    def test_explicit_new_photo_on_the_same_day_is_not_suppressed(self):
        from test_photo_calendar_155 import Photo155
        from protocol import image_packets
        m=Photo155().ready(datetime(2026,11,14).date())
        for token in (101,102):
            frame=bytearray(b'\xff'*4000+bytes(4000));frame[2000]=token
            for packet in list(image_packets(bytes(frame),token,128))[:-1]:m.cmd(packet)
            generation=m.status()['display_generation'];m.cmd(b'\x9c\x03');self.assertTrue(m.status()['busy']);m.finish()
            self.assertEqual(m.status()['display_generation'],generation+1)
            self.assertEqual(m.uc.mem_read(BASE+0xdedc+2000,1)[0],token)

    def test_only_application_dispatch_refresh_view_relocations_version_and_id_change_since_1521(self):
        old=(ROOT/'build/firmware-1.5.21-final-checked/elink-bwr-1.5.21-app.bin').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),'9454dec64dcf2c614e76b067402778d5aa9d3461c86a6d097ad4393c6e1aa4ae')
        meta=json.loads((FIRMWARE_DIR/'manifest.json').read_text('utf-8'))
        new=(FIRMWARE_DIR/f'elink-bwr-{meta["version"]}-app.bin').read_bytes();self.assertEqual(len(new),len(old))
        self.assertEqual(new.count(('V'+meta['version']+'\0').encode()),1)
        allowed=((0x2cc4,0x31c8),(0x8600,0x90a4),(0x9300,0xa46c),(0xba00,0xc2a0),
                 (0xe0fc,0xe100),(0xe13e,0xe142),(0xe2f0,0xe2f4))
        self.assertFalse([hex(i) for i,(a,b) in enumerate(zip(old,new)) if a!=b and not any(lo<=i<hi for lo,hi in allowed)])

if __name__=='__main__':unittest.main()
