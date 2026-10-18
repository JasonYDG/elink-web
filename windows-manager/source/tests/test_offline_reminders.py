"""Actual Thumb schedule upload, NOR page boundaries, offline firing and OTA isolation."""
import os,sys,struct,zlib,unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_product_ui import ProductMachine
from test_firmware import BASE,STATE
from protocol import reminder_metadata,decode_reminder_runtime

class OfflineReminders(unittest.TestCase):
    def assert_reminder_pixels(self,actual,frame):
        # Device battery refresh owns exactly the reserved top-right region.
        for plane in (0,4000):
            for x in range(250):
                for y in range(122):
                    if x>=176 and 8<=y<=22:continue
                    pos=plane+(249-x)*16+(y>>3);mask=128>>(y&7)
                    self.assertEqual(actual[pos]&mask,frame[pos]&mask)
        self.assertNotEqual(actual,frame,'Reserved status area must use the live native battery renderer')
    def test_interrupted_install_releases_clock_after_three_minute_ticks(self):
        m=ProductMachine();m.draw(force=128);m.finish();m.cmd(b'\x99\x05\x01\0')
        m.cmd(b'\xb0\0'+struct.pack('<III',1,1800000000,0));m.cmd(b'\xb1\0\0bad')
        for minute in (1,2,3):m.draw(minute=minute)
        m.cmd(b'\xb4\0');self.assertEqual(m.published[7]&1,0)
        self.assertEqual(m.flash[0x26010],255,'An interrupted frame must never become ready')
        before=m.status()['display_generation'];m.draw(minute=5);m.finish();self.assertEqual(m.status()['display_generation'],before+1)
    def install(self,m,slot=0,token=123,due=None,options=None,large=False):
        due=due or int(datetime(2026,10,6,1,10,tzinfo=timezone.utc).timestamp())
        frame=bytes((i*19)%256 for i in range(4000))+bytes((i*7)%256 for i in range(4000))
        m.cmd(b'\xb0'+bytes([slot])+struct.pack('<III',token,due,zlib.crc32(frame)))
        self.assertEqual(m.status()['error'],0)
        for off in range(0,8000,17):m.cmd(b'\xb1'+struct.pack('<H',off)+frame[off:off+17])
        if options is not None:
            meta=reminder_metadata('晚间服药',options,large=large)
            for off in range(0,156,18):
                if off==144:
                    m.cmd(b'\xb2'+struct.pack('<I',token));self.assertEqual(m.status()['error'],1)
                    self.assertEqual(m.flash[0x26000+slot*8192+16],255,'Partial policy must not enable a reminder')
                m.cmd(bytes([0xb8,off])+meta[off:off+18])
            m.flash[0x26000+slot*8192+172]^=1
            m.cmd(b'\xb2'+struct.pack('<I',token));self.assertEqual(m.status()['error'],1)
            self.assertEqual(m.flash[0x26000+slot*8192+16],255,'Corrupt metadata CRC must not enable a reminder')
            m.flash[0x26000+slot*8192+172]^=1
        m.cmd(b'\xb2'+struct.pack('<I',token));self.assertEqual(m.status()['error'],0)
        return frame
    def test_offline_due_once_fires_after_both_refresh_phases_without_host(self):
        m=ProductMachine();m.draw(year=2026,month=10,day=6,h=9,minute=5,force=128);m.finish()
        m.cmd(b'\x99\x05\x01\0');m.cmd(b'\xb3'+struct.pack('<i',28800));before=m.status()['display_generation']
        frame=self.install(m)
        self.assertEqual(m.status()['display_generation'],before,'Installation must not repaint the screen')
        self.assertEqual(m.status()['display_mode'],0,'Installation must retain clock mode')
        m.draw(day=6,h=9,minute=9);self.assertFalse(m.status()['busy'])
        actual=m.draw(day=6,h=9,minute=10);self.assert_reminder_pixels(actual,frame)
        self.assertEqual(m.flash[0x26010],254,'No success mark before actual BUSY completion')
        m.finish();self.assertEqual(m.flash[0x26010],252);self.assertEqual(m.status()['display_mode'],2)
        generation=m.status()['display_generation'];m.draw(day=6,h=9,minute=11);self.assertEqual(m.status()['display_generation'],generation)
        self.assertTrue(all(0x26000<=a and a+n<=0x36000 for _,a,n in m.flash_events),'Schedule writes must not touch OTA or panel settings')
    def test_atomic_crc_readback_partial_upload_and_restart(self):
        m=ProductMachine();m.cmd(b'\xb0\0'+struct.pack('<III',1,1800000000,0));m.cmd(b'\xb1\0\0bad')
        self.assertEqual(m.flash[0x26010],255);m.cmd(b'\xb2'+struct.pack('<I',1));self.assertEqual(m.status()['error'],1)
        frame=self.install(m,slot=1,token=99)
        for off in range(0,8000,128):
            m.cmd(b'\xb7\x01'+struct.pack('<H',off));self.assertEqual(m.published,frame[off:off+128])
        # Real cold scatter resets RAM, while the separate NOR device survives.
        m.cold_boot();m.cmd(b'\xb4\x01');self.assertEqual(m.published[:5],b'ERM1\x01');self.assertEqual(m.published[6],254)
        self.assertEqual(struct.unpack_from('<I',m.published,8)[0],99);self.assertEqual(m.published[23],0,'Clock must be resynchronized after full power loss')
        m.cmd(b'\xb5\x01'+struct.pack('<I',98));self.assertEqual(m.status()['error'],1)
        m.cmd(b'\xb5\x01'+struct.pack('<I',99));self.assertEqual(m.flash[0x28010],248)
    def test_busy_bounds_occupied_slot_corruption_and_netherlands_dst(self):
        m=ProductMachine();m.cmd(b'\xb3'+struct.pack('<i',28800));self.install(m)
        original=bytes(m.flash);m.cmd(b'\xb0\0'+struct.pack('<III',2,1800000000,0));self.assertEqual(m.status()['error'],2)
        m.cmd(b'\xb0\x08'+struct.pack('<III',2,1800000000,0));self.assertEqual(m.status()['error'],1);self.assertEqual(bytes(m.flash),original)
        m.uc.mem_write(STATE+8,b'\x01');m.cmd(b'\xb5\0'+struct.pack('<I',123));self.assertEqual(m.status()['error'],2);m.uc.mem_write(STATE+8,b'\0')
        m.flash[0x26000+192]^=1;m.draw(day=6,h=9,minute=10,force=128);m.finish();self.assertEqual(m.flash[0x26010],248)
        # October repeated hour: UTC due still compares against the correct DST bit.
        n=ProductMachine();n.cmd(b'\x9f\x01\x01');n.cmd(b'\xb3'+struct.pack('<i',7200))
        due=int(datetime(2026,10,25,1,10,tzinfo=timezone.utc).timestamp());frame=self.install(n,due=due)
        n.draw(day=25,weekday=0,h=2,minute=10,force=128);n.finish();self.assertEqual(n.flash[0x26010],254)
        actual=n.draw(day=25,weekday=0,h=3,minute=10);self.assert_reminder_pixels(actual,frame);n.finish();self.assertEqual(n.flash[0x26010],252)

    def test_summary_periodic_daily_repeat_duration_and_weekday_rollover(self):
        m=ProductMachine();m.draw(day=6,h=9,minute=0,force=128);m.finish();m.cmd(b'\xb3'+struct.pack('<i',28800))
        m.cmd(b'\xb9');m.finish();self.assertEqual(m.status()['display_mode'],5)
        self.assertIn('今日无任务'.encode(),[d[2] for d in m.draws])
        due=int(datetime(2026,10,6,1,12,tzinfo=timezone.utc).timestamp())
        frame=self.install(m,due=due,options={'repeat_mask':127,'check_minutes':5,'duration_minutes':1,'utc_offset':28800})
        m.cmd(b'\xb9');m.finish();generation=m.status()['display_generation']
        m.draw(day=6,h=9,minute=11);self.assertEqual(m.status()['display_generation'],generation,'No unchanged summary repaint')
        m.draw(day=6,h=9,minute=12);m.finish();self.assertEqual(m.status()['display_mode'],5,'Periodic checks defer to their aligned minute')
        actual=m.draw(day=6,h=9,minute=15);self.assert_reminder_pixels(actual,frame);m.finish()
        m.cmd(b'\xbb\0');runtime=decode_reminder_runtime(m.published)
        self.assertEqual(runtime['last_due'],due);self.assertEqual(runtime['next_due'],due+86400)
        self.assertEqual(m.flash[0x26010],254,'Recurring alarm stays enabled without Flash erase per occurrence')
        m.draw(day=6,h=9,minute=16);m.finish();self.assertEqual(m.status()['display_mode'],5,'Duration expiry returns summary, not the old clock')
        m.draw(day=7,h=9,minute=15);m.finish();m.cmd(b'\xbb\0');self.assertEqual(decode_reminder_runtime(m.published)['last_due'],due+86400)
        m.cold_boot();m.cmd(b'\xb3'+struct.pack('<i',28800));m.draw(day=7,h=10,minute=0);m.finish();m.cmd(b'\xbb\0')
        self.assertEqual(decode_reminder_runtime(m.published)['next_due'],due+2*86400,'Cold restart skips missed repeat events after time calibration')
        n=ProductMachine();n.draw(day=6,h=9,minute=0,force=128);n.finish();n.cmd(b'\xb3'+struct.pack('<i',28800))
        self.install(n,due=due,options={'repeat_mask':16,'check_minutes':1,'duration_minutes':0,'utc_offset':28800})
        n.cmd(b'\xbb\0');self.assertEqual(decode_reminder_runtime(n.published)['next_due'],due+2*86400,'Thursday-only starts on Thursday')
        n.draw(day=6,h=9,minute=12);n.finish();self.assertEqual(n.flash[0x26010],254)
        n.draw(day=8,h=9,minute=12);n.finish();n.cmd(b'\xbb\0');self.assertEqual(decode_reminder_runtime(n.published)['next_due'],due+9*86400)

    def test_large_summary_exact_pixels_completed_count_and_four_row_bounds(self):
        from test_product_ui import frame_matches
        m=ProductMachine();m.draw(day=6,h=9,minute=0,force=128);m.finish();m.cmd(b'\xb3'+struct.pack('<i',28800))
        due=int(datetime(2026,10,6,1,10,tzinfo=timezone.utc).timestamp())
        self.install(m,due=due,options={'repeat_mask':127,'check_minutes':1,'duration_minutes':1,'utc_offset':28800},large=True)
        m.cmd(b'\xb9');m.finish()
        frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
        for value,size,x,y in (('今日任务',18,8,1),('09:10',18,8,29),('晚间服药',16,68,30),('2026/10/06',14,162,108)):
            self.assertTrue(frame_matches(frame,value,size,x,y),value+' must retain every exact-size source pixel')
            if value in ('今日任务','09:10'):self.assertTrue(frame_matches(frame,value,size,x,y,plane='red'))
        m.draw(day=6,h=9,minute=10);m.finish();m.draw(day=6,h=9,minute=11);m.finish()
        self.assertIn((8,110,'待提醒0项'.encode()),m.draws,'Today-completed recurrence must not count as pending today')
        for slot in range(1,5):self.install(m,slot=slot,token=123+slot,due=due+slot*3600,options={},large=True)
        m.draws.clear();m.cmd(b'\xb9');m.finish()
        self.assertIn((8,110,'另有1项'.encode()),m.draws)
        self.assertIn((208,90,'待提醒'.encode()),m.draws,'Status right edge must align to header/footer at x=244')
        frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
        for row,time in enumerate(('09:10','10:10','11:10','12:10')):self.assertTrue(frame_matches(frame,time,18,8,27+row*20,plane='red'))
        for x in range(68,244):
            for y in range(27,105):
                pos=(249-x)*16+(y>>3);self.assertFalse(frame[4000+pos]&(128>>(y&7)),'Task names/status must retain black ink')
        for x in range(250):
            for y in range(105,122):
                pos=(249-x)*16+(y>>3);self.assertFalse(frame[4000+pos]&(128>>(y&7)),'No hidden fifth red time may overwrite the black footer')
        self.assertTrue(frame_matches(frame,'晚间服药',16,68,88))
        self.assertTrue(frame_matches(frame,'2026/10/06',14,162,108))

if __name__=='__main__':unittest.main()
