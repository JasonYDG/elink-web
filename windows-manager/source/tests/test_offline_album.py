"""Execute compiled album code against a bounded NOR flash hardware model."""
import struct,unittest,zlib
from test_photo_calendar import PhotoMachine
from test_firmware import BASE,STATE,END
from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_LR,UC_ARM_REG_R0
from protocol import image_packets

class AlbumMachine(PhotoMachine):
    def hook(self,uc,address,size,data):
        if address==BASE+0x4368:
            self.id_commands.append(uc.reg_read(UC_ARM_REG_R0))
            reply=(0,0,0,0,0xa1,0x12)[(len(self.id_commands)-1)%6]
            uc.reg_write(UC_ARM_REG_R0,reply);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
        return super().hook(uc,address,size,data)
    def run(self,address,r0=0):
        self.uc.reg_write(UC_ARM_REG_R0,r0);self.uc.reg_write(UC_ARM_REG_LR,END|1)
        self.uc.emu_start(address|1,END,count=5000000)
        if self.uc.reg_read(UC_ARM_REG_PC) not in (END,BASE+0x6c94,BASE+0x6c9c):raise AssertionError(hex(self.uc.reg_read(UC_ARM_REG_PC)))
    def album(self):
        self.cmd(b'\xbd\x00');assert self.status()['error']==0
        self.cmd(b'\xbd\x00');return self.published
    def frame(self):return bytes(self.uc.mem_read(BASE+0xdedc,4000))+bytes(self.uc.mem_read(BASE+0xf15c,4000))
    def minute(self):
        self.uc.mem_write(BASE+0x104dc+44,bytes(4));self.run(int(self.meta['labels']['adv'],16))
    def stage(self,frames):
        self.cmd(b'\xbd\x01');assert self.status()['error']==0
        for i,frame in enumerate(frames):
            for p in list(image_packets(frame,10+i,128))[:-1]:self.cmd(p)
            for step in range(32):self.cmd(b'\xbd\x02'+bytes((i,42))+struct.pack('<I',zlib.crc32(frame))+bytes([step]))
            assert self.status()['error']==0,self.status()
    def play(self,mode=0,minutes=60):
        self.cmd(b'\xbd\x03'+bytes([mode])+struct.pack('<H',minutes));assert self.status()['error']==0,self.status();self.finish()

class OfflineAlbum(unittest.TestCase):
    def test_native_minute_callback_with_nonzero_seconds_advances_album(self):
        m=AlbumMachine();m.draw(h=9,minute=7,force=128);m.finish()
        frames=[bytes([17])*8000,bytes([34])*8000];m.stage(frames);m.play(minutes=60)
        m.uc.mem_write(BASE+0x104dc+4,struct.pack('<I',1))
        m.uc.mem_write(BASE+0x104dc+44,struct.pack('<I',37))
        m.uc.mem_write(BASE+0x124cc+72,b'\xff'*4)
        m.run(BASE+0x25c0)
        self.assertEqual(struct.unpack('<I',m.uc.mem_read(BASE+0x104dc+44,4))[0],37)
        self.assertEqual(struct.unpack('<I',m.uc.mem_read(BASE+0x104dc+40,4))[0],8)
        self.assertEqual(struct.unpack_from('<H',m.album(),10)[0],1,'Native minute callbacks preserve synchronization seconds')
        for _ in range(59):m.run(BASE+0x25c0);m.finish()
        self.assertEqual(m.frame(),frames[1]);self.assertEqual(m.album()[7],1)

    def test_calendar_and_timer_changes_preserve_all_native_regions(self):
        import hashlib,json
        from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
        from test_firmware import ROOT,FIRMWARE_DIR
        before=json.loads((ROOT/'build/firmware-1.5.8/manifest.json').read_text())
        after=json.loads((FIRMWARE_DIR/'manifest.json').read_text())
        old=(ROOT/'build/firmware-1.5.8/elink-bwr-1.5.8-app.bin').read_bytes()
        new=(FIRMWARE_DIR/('elink-bwr-'+after['version']+'-app.bin')).read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),'c927bf68dc368aed55c2b7ea37cded516636ad9e47781647763b1bfa2bed9464')
        self.assertEqual(len(old),len(new));self.assertEqual(before['runtime_bytes'],after['runtime_bytes']);self.assertEqual(before['labels'],after['labels'])
        allowed=[(0x2cc4,0x31c8),(0x7eb4,0x8500),(0x8600,0x90a4),(0x9300,0xa46c),(0xa48c,0xc2a0),(0xc8a4,0xd2b0),(0xe2f0,0xe2f4),(0xe0fc,0xe100)]
        # test_album_seven independently compares every retained 18px glyph after unused glyph removal.
        calls={0x2274:'product_boot_battery',0xde26:'product_sync_valid',0xdf16:'product_view',0xdf2c:'product_control',0xe12c:'product_refresh',0xe13e:'product_finish',0x2d54:'product_album_tick',0x8e0c:'product_album_restore',0x9978:'product_album_finish',0x99b2:'product_album_finish',0xe172:'product_minute_tick'}
        for off,name in calls.items():
            allowed.append((off,off+4))
            for raw,meta in ((old,before),(new,after)):
                address=BASE+off if off<0xddd4 else int(meta['runtime_address'],16)+off-int(meta['runtime_load_offset'],16)
                call=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(raw[off:off+4],address))
                self.assertEqual(len(call),1);self.assertEqual(call[0].mnemonic,'bl')
                self.assertEqual(int(call[0].op_str.lstrip('#'),16),int(meta['product_symbols'][name],16)&~1)
        self.assertFalse([hex(i) for i,(a,b) in enumerate(zip(old,new)) if a!=b and not any(lo<=i<hi for lo,hi in allowed)])

    def test_save_steps_are_bounded_ordered_crc_checked_and_restartable(self):
        from unicorn.arm_const import UC_ARM_REG_R1
        class TracedAlbum(AlbumMachine):
            def hook(self,uc,a,size,data):
                if a==BASE+0x6828 and hasattr(self,'reads'):self.reads.append(uc.reg_read(UC_ARM_REG_R1))
                if a==BASE+0x6828 and getattr(self,'corrupt_read',False):
                    self.flash[uc.reg_read(UC_ARM_REG_R0)]^=1;self.corrupt_read=False
                return super().hook(uc,a,size,data)
        m=TracedAlbum();old=bytes([17])*8000;new=bytes((i*31)%256 for i in range(8000))
        m.stage([old]);m.play();m.cmd(b'\xbd\x01')
        for p in list(image_packets(new,99,128))[:-1]:m.cmd(p)
        command=b'\xbd\x02\0\x2a'+struct.pack('<I',zlib.crc32(new))
        for step in range(32):
            before=len(m.flash_events);m.reads=[]
            m.cmd(command+bytes([step]));self.assertEqual(m.status()['error'],0)
            events=m.flash_events[before:]
            self.assertEqual(sum(n for op,a,n in events if op=='write'),250)
            self.assertLessEqual(sum(op=='write' for op,a,n in events),2)
            self.assertEqual([n for op,a,n in events if op=='erase'],[4096] if step in (0,16) else [])
            self.assertEqual(sum(m.reads),250,'No full-frame reread inside a save step')
            if step==15:
                m.cmd(command+bytes([step]));self.assertEqual(m.status()['error'],1)
                m.cmd(b'\xbd\x03\0\x3c\0');self.assertEqual(m.status()['error'],1)
        self.assertEqual(m.flash[0x42000:0x42000+8000],new)
        m.cold_boot();m.run(BASE+0x2224);m.finish();m.minute();m.finish()
        self.assertEqual(m.frame(),old,'Uncommitted new bank must never become active')
        # A lost save reply can restart the transaction without stopping or erasing the old album.
        m.cmd(b'\xbd\x01')
        for p in list(image_packets(new,100,128))[:-1]:m.cmd(p)
        m.cmd(command+b'\0');m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],0)
        for p in list(image_packets(new,101,128))[:-1]:m.cmd(p)
        for step in range(32):
            if step==31:m.corrupt_read=True
            m.cmd(command+bytes([step]))
        self.assertEqual(m.status()['error'],5)
        m.cmd(b'\xbd\x03\0\x3c\0');self.assertEqual(m.status()['error'],1)
        self.assertEqual(m.flash[0x4a000:0x4a000+8000],old)
        for _ in range(5):m.minute()
        m.play();self.assertEqual(m.frame(),old,'Expired partial upload must allow the committed album to resume')

    def test_foreign_flash_wrong_chip_and_invalid_commands_never_erase(self):
        for where in (0x40000,0x41fff,0x42000,0x51fff):
            m=AlbumMachine();m.flash[where]=0;m.cmd(b'\xbd\x01')
            self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,[])
        m=AlbumMachine()
        for packet in (b'\xbd',b'\xbd\x03\0\x3b\0',b'\xbd\x03\x02\x3c\0',b'\xbd\x05',b'\xbd\x02'+bytes(6)):
            m.cmd(packet);self.assertNotEqual(m.status()['error'],0)
        self.assertEqual(m.flash_events,[])
        # The native SPI-ID function still executes; substitute only its bus response.
        m=AlbumMachine();m.id_commands=[0];m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,[])

    def test_metadata_commit_power_cuts_keep_an_entire_old_or_new_album(self):
        m=AlbumMachine();old=bytes([17])*8000;new=bytes([34])*8000
        m.stage([old]);m.play();m.stage([new])
        ram=bytes(m.uc.mem_read(BASE,0x20000));flash=bytes(m.flash)
        for cut in (1,2,3):
            m.uc.mem_write(BASE,ram);m.flash[:]=flash;m.flash_events=[]
            # Unicorn registered the original bound method; inject through a second hardware-event hook.
            from unicorn import UC_HOOK_CODE
            def fail_after(uc,address,size,data):
                if len(m.flash_events)>=cut:raise InterruptedError('power cut')
            token=m.uc.hook_add(UC_HOOK_CODE,fail_after)
            with self.assertRaises(InterruptedError):m.cmd(b'\xbd\x03\0\x3c\0')
            m.uc.hook_del(token);m.cold_boot();m.run(BASE+0x2224);m.finish();m.minute();m.finish()
            self.assertEqual(m.frame(),new if cut==3 else old,cut)
            self.assertEqual(m.flash[0x4a000:0x4a000+8000],old,'Old image bank must never be touched by replacement')

    def test_stale_valid_metadata_is_not_accepted_after_program_failure(self):
        class FailedMetadata(AlbumMachine):
            def hook(self,uc,a,size,data):
                if getattr(self,'fail_metadata',False) and a in (BASE+0x671c,BASE+0x67c4) and 0x40000<=uc.reg_read(UC_ARM_REG_R0)<0x42000:
                    uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
                return super().hook(uc,a,size,data)
        m=FailedMetadata();old=bytes([17])*8000;new=bytes([34])*8000
        m.stage([old]);m.play();m.stage([new]);m.fail_metadata=True
        m.cmd(b'\xbd\x03\0\x3c\0');self.assertEqual(m.status()['error'],5)
        self.assertEqual(struct.unpack_from('<I',m.album(),28)[0],zlib.crc32(old))
        m.fail_metadata=False;m.cold_boot();m.run(BASE+0x2224);m.finish();m.minute();m.finish()
        self.assertEqual(m.frame(),old)

    def test_calendar_crop_daily_update_and_corrupt_frame_stops(self):
        from render import photo_calendar_frame
        m=AlbumMachine();m.draw(day=18,weekday=0,force=128);m.finish()
        frame=bytes((i*19)%256 for i in range(8000));m.stage([frame]);m.play(mode=1,minutes=1440)
        expected=photo_calendar_frame(frame,42)['frame'];before=m.frame()
        for off in (0,4000):self.assertEqual(before[off+1216:off+4000],expected[off+1216:off+4000])
        generation=m.status()['display_generation'];m.draw(day=18,weekday=0,minute=59);self.assertEqual(m.status()['display_generation'],generation)
        m.draw(day=19,weekday=1);m.finish();self.assertEqual(m.status()['display_generation'],generation+1)
        for off in (0,4000):self.assertEqual(m.frame()[off+1216:off+4000],before[off+1216:off+4000])
        m.flash[0x4a000]^=1;m.cold_boot();m.run(BASE+0x2224);m.finish();generation=m.status()['display_generation'];m.minute()
        self.assertEqual(m.status()['error'],5);self.assertEqual(m.status()['display_generation'],generation)
        self.assertEqual(m.album()[6],0)

    def test_busy_ota_and_reminder_priority_then_same_photo_restores(self):
        from test_offline_reminders import OfflineReminders
        import datetime
        m=AlbumMachine();m.draw(day=6,h=9,minute=0,force=128);m.finish();m.cmd(b'\xb3'+struct.pack('<i',28800))
        due=int(datetime.datetime(2026,10,6,1,1,tzinfo=datetime.timezone.utc).timestamp())
        OfflineReminders().install(m,due=due,options={'duration_minutes':1})
        frame=bytes([23])*8000;m.stage([frame]);m.play();m.draw(day=6,h=9,minute=1);m.finish()
        self.assertEqual(m.status()['display_mode'],2)
        m.draw(day=6,h=9,minute=2);m.finish();self.assertEqual(m.status()['display_mode'],7);self.assertEqual(m.frame(),frame)
        before=m.album()[10:12]
        for addr,value in ((STATE+8,b'\x01'),(BASE+0x10564,b'\x01\0\0\0')):
            m.uc.mem_write(addr,value);m.minute();m.uc.mem_write(addr,bytes(len(value)))
            self.assertEqual(m.album()[10:12],before)

    def test_native_spi_driver_sends_high_address_bytes_without_aliasing(self):
        from unicorn.arm_const import UC_ARM_REG_R1,UC_ARM_REG_R2
        class BusMachine(AlbumMachine):
            def hook(self,uc,a,size,data):
                if getattr(self,'wire_test',False):
                    if a in (BASE+0x671c,BASE+0x67c4,BASE+0x6828):return
                    if a==BASE+0x4368:
                        self.wire.append(uc.reg_read(UC_ARM_REG_R0)&255);uc.reg_write(UC_ARM_REG_R0,0x5a);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
                    if a in (BASE+0x69b0,BASE+0x6990,BASE+0x42d8,BASE+0x2ad0):
                        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
                return super().hook(uc,a,size,data)
        m=BusMachine();m.wire_test=True;m.wire=[];buffer=BASE+0x1b100
        m.uc.reg_write(UC_ARM_REG_R1,8);m.uc.reg_write(UC_ARM_REG_R2,buffer);m.run(BASE+0x6828,0x51ff0)
        self.assertEqual(m.wire[:5],[0x0b,5,0x1f,0xf0,0]);self.assertEqual(bytes(m.uc.mem_read(buffer,8)),b'\x5a'*8)
        m.wire=[];m.uc.mem_write(buffer,b'1234');m.uc.reg_write(UC_ARM_REG_R1,buffer);m.uc.reg_write(UC_ARM_REG_R2,4);m.run(BASE+0x67c4,0x51f00)
        self.assertEqual(m.wire,[2,5,0x1f,0,*b'1234'])
        m.wire=[];m.uc.reg_write(UC_ARM_REG_R1,8192);m.run(BASE+0x671c,0x4a000)
        self.assertEqual(m.wire,[0x20,4,0xa0,0,0x20,4,0xb0,0])

    def test_four_slots_order_wrap_and_full_day_interval(self):
        m=AlbumMachine();frames=[bytes([n])*8000 for n in (10,20,30,40)];m.stage(frames);m.play(minutes=1440)
        for index in (1,2,3,0):
            for _ in range(1439):m.minute()
            self.assertFalse(m.status()['busy']);m.minute();m.finish();self.assertEqual(m.frame(),frames[index])
        self.assertEqual(m.album()[7],0)
        m.cmd(b'\xbd\x01')
        for i,frame in enumerate(frames):
            for p in list(image_packets(frame,10+i,128))[:-1]:m.cmd(p)
            for step in range(32):m.cmd(b'\xbd\x02'+bytes((i,42))+struct.pack('<I',zlib.crc32(frame))+bytes([step]))
        events=list(m.flash_events);m.cmd(b'\xbd\x02\x04\x2a'+bytes(4));self.assertEqual(m.status()['error'],1);self.assertEqual(m.flash_events,events)

    def test_install_rotate_without_time_and_restore_after_cold_boot(self):
        m=AlbumMachine();frames=[bytes((i*k)%256 for i in range(8000)) for k in (13,31)]
        m.stage(frames);m.play();self.assertEqual(m.frame(),frames[0]);self.assertEqual(m.album()[7],0)
        events=list(m.flash_events)
        for _ in range(59):m.minute()
        self.assertFalse(m.status()['busy']);m.minute();self.assertTrue(m.status()['busy']);m.finish()
        self.assertEqual(m.frame(),frames[1]);self.assertEqual(m.album()[7],1)
        self.assertEqual(m.flash_events,events,'Playback must not erase or program flash')
        m.cold_boot();m.run(BASE+0x2224);m.finish();m.minute();m.finish()
        self.assertFalse(m.status()['time_initialized']);self.assertEqual(m.frame(),frames[0])
        self.assertTrue(all(0x40000<=a and a+n<=0x52000 for _,a,n in events))
        m.cmd(b'\xbd\x04');self.assertEqual(m.status()['error'],0)
        m.cold_boot();m.run(BASE+0x2224);m.finish();m.minute();self.assertEqual(m.album()[6],0)

if __name__=='__main__':unittest.main()
