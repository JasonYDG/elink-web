"""Run actual patched Thumb code; only external ROM/SPI/BUSY hardware is stubbed."""
import sys,struct,json,zlib,unittest,os
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source/backend'))
from protocol import image_packets,decode_status,sync_packet
BASE=0x7fc0000;STATE=BASE+0x11980;END=BASE+0x1ff00
FIRMWARE_DIR=Path(os.environ.get('ELINK_TEST_FIRMWARE_DIR',ROOT/'build/firmware'))
BOOTSTRAP_DIR=Path(os.environ.get('ELINK_TEST_BOOTSTRAP_DIR',ROOT/'source/reference/bootstrap-1.0.5'))
def firmware_file(suffix,directory=FIRMWARE_DIR):
    meta=json.loads((directory/'manifest.json').read_text())
    return directory/('elink-bwr-'+meta['version']+suffix)

class Machine:
    def __init__(self,firmware_dir=None):
        directory=Path(firmware_dir) if firmware_dir else FIRMWARE_DIR
        self.meta=json.loads((directory/'manifest.json').read_text())
        self.b=(directory/('elink-bwr-'+self.meta['version']+'-app.bin')).read_bytes()
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB);self.uc.mem_map(BASE,0x20000);self.uc.mem_write(BASE,self.b)
        self.uc.mem_map(0x50000000,0x10000);self.uc.mem_map(0x7f00000,0x20000);self.uc.mem_map(0xe000e000,0x1000)
        self.busy=0;self.msg=None;self.commands=[];self.gpio=[];self.calls=[];self.pin_values={}
        if not hasattr(self,'flash'):self.flash=bytearray(b'\xff'*0x40000)
        self.flash_events=[]
        self.decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.cold_boot()
    def cold_boot(self,raw=None):
        if raw is not None:self.b=raw
        self.uc.mem_write(BASE,self.b);self.booting=True
        reset=struct.unpack_from('<I',self.b,4)[0]
        self.uc.emu_start(reset,BASE+0x518,count=20000)
        self.booting=False
        assert self.uc.reg_read(UC_ARM_REG_PC)==BASE+0x518, 'Native cold initialization did not complete'
        self.boot_stack=self.uc.reg_read(UC_ARM_REG_SP)
        assert self.boot_stack==BASE+0x10c18
        self.uc.reg_write(UC_ARM_REG_SP,BASE+0x1d000)
        if self.meta.get('boot_identity_address'):
            # DB-init boot page runs after the native five-pad GPIO/geometry setup.
            self.uc.reg_write(UC_ARM_REG_R1,0x07210120)
            self.uc.reg_write(UC_ARM_REG_R2,122);self.uc.reg_write(UC_ARM_REG_R3,250)
            self.uc.mem_write(BASE+0x1d000,struct.pack('<I',0x23))
            self.run(BASE+0x3ea0,0x23111000)
    def word(self,a):return struct.unpack('<I',self.uc.mem_read(a,4))[0]
    def hook(self,uc,a,size,_):
        helper=int(self.meta.get('helper_address','0'),16)
        if BASE+0x11480<=a<STATE or helper<=a<helper+self.meta.get('helper_bytes',0) or (getattr(self,'booting',False) and BASE+0x110<=a<BASE+0x150):
            ins=next(self.decoder.disasm(bytes(uc.mem_read(a,size)),a))
            assert size==2 or ins.mnemonic=='bl', str(ins)
        r0=uc.reg_read(UC_ARM_REG_R0);r1=uc.reg_read(UC_ARM_REG_R1)
        skip=True
        if self.meta.get('offline_reminders') and a==BASE+0x6828:
            r2=uc.reg_read(UC_ARM_REG_R2);assert 0<=r0 and r0+r1<=len(self.flash)
            uc.mem_write(r2,bytes(self.flash[r0:r0+r1]));uc.reg_write(UC_ARM_REG_R0,r1)
        elif self.meta.get('offline_reminders') and a==BASE+0x67c4:
            count=uc.reg_read(UC_ARM_REG_R2);assert count<=256-(r0&255),'NOR page program must not wrap'
            assert 0<=r0 and r0+count<=len(self.flash)
            for i,v in enumerate(uc.mem_read(r1,count)):self.flash[r0+i]&=v
            self.flash_events.append(('write',r0,count))
        elif self.meta.get('offline_reminders') and a==BASE+0x671c:
            assert r0%4096==0 and r1%4096==0 and r0+r1<=len(self.flash)
            self.flash[r0:r0+r1]=b'\xff'*r1;self.flash_events.append(('erase',r0,r1))
        elif self.meta.get('offline_reminders') and a in (BASE+0x42e8,BASE+0x6990):pass
        elif a==BASE+0x4368:uc.reg_write(UC_ARM_REG_R0,0) # SPI boundary: unspecified chip, persistence must refuse.
        elif a==0x7f0283e:uc.reg_write(UC_ARM_REG_R0,0xfd)
        elif a==0x7f1bbb0:
            assert uc.reg_read(UC_ARM_REG_SP)%8==0
            self.msg=BASE+0x1c000;uc.mem_write(self.msg,bytes(64));uc.reg_write(UC_ARM_REG_R0,self.msg)
        elif a==0x7f1bbe2:self.published=bytes(uc.mem_read(r0+6,struct.unpack('<H',uc.mem_read(r0+4,2))[0]))
        elif a==BASE+0x3bdc:uc.reg_write(UC_ARM_REG_R0,self.busy)
        elif a in (BASE+0x3f04,BASE+0x3f68,BASE+0x40e8,BASE+0x27f4,BASE+0x2cc4,BASE+0x31c8,BASE+0x6af0):self.calls.append(a)
        elif a in (BASE+0x3c10,BASE+0x3be8,BASE+0x3cf4,BASE+0x4140):self.commands.append((a,r0,r1))
        elif a==BASE+0x4ff4:self.gpio.append((r0,r1,uc.reg_read(UC_ARM_REG_R2)))
        elif a==BASE+0x505c:self.pin_values[r0]=r1
        elif a in (BASE+0x6c94,BASE+0x6c9c):uc.emu_stop();return
        else:skip=False
        if skip:uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def run(self,address,r0=0):
        self.uc.reg_write(UC_ARM_REG_R0,r0);self.uc.reg_write(UC_ARM_REG_LR,END|1)
        self.uc.emu_start(address|1,END,count=1000000)
    def cmd(self,b):
        p=BASE+0x1b000
        self.uc.mem_write(p,struct.pack('<BBHH',0,0,6,len(b))+b)
        self.uc.reg_write(UC_ARM_REG_R4,p)
        self.run(BASE+0x6c98)
        assert self.uc.reg_read(UC_ARM_REG_SP)==BASE+0x1d000
    def status(self):
        self.cmd(b'\x93');return decode_status(self.published)

class Firmware(unittest.TestCase):
    def test_template_refresh_records_pending_sleep_disable_during_ble_event(self):
        m=Machine()
        sleep_control=BASE+0x124cc
        m.uc.mem_write(sleep_control+3,b'\x01')
        m.uc.mem_write(sleep_control+4,b'\x81')
        frame=b'\xff'*4000+bytes(4000)
        for packet in image_packets(frame,11):m.cmd(packet)
        self.assertEqual(bytes(m.uc.mem_read(sleep_control+4,1)),b'\x80',
                         'Pending ARCH_SLEEP_OFF must be marked valid while BLE holds sleep_md')
        self.assertTrue(m.status()['busy'])
    def test_native_repeat_boot_page_calls_do_not_repaint_completed_boot(self):
        m=Machine();m.run(BASE+0x2224)
        m.busy=0;m.run(int(m.meta['labels']['finish'],16))
        before=len(m.commands);generation=m.status()['display_generation']
        m.run(BASE+0x2224)
        self.assertEqual(len(m.commands),before)
        self.assertEqual(m.status()['display_generation'],generation)
        self.assertFalse(m.status()['busy'])
        # A long-running clock wraps the u16 generation; it must not become a boot page.
        m.cmd(sync_packet())
        m.uc.mem_write(STATE+18,bytes(2))
        m.run(BASE+0x2224)
        self.assertEqual(len(m.commands),before)
        self.assertFalse(m.status()['busy'])
    def test_native_cold_start_and_rom_owned_regions_cannot_erase_overlay(self):
        m=Machine();meta=m.meta
        runtime=int(meta['runtime_address'],16);offset=int(meta['runtime_load_offset'],16);size=meta['runtime_bytes']
        self.assertEqual(bytes(m.uc.mem_read(runtime,size)),m.b[offset:offset+size])
        self.assertEqual(bytes(m.uc.mem_read(BASE+0x110,0x400)),bytes(0x400))
        self.assertEqual(struct.unpack_from('<4I',m.b,0xdbe4),(BASE+0x110,BASE+0x110,0x400,BASE+0x7088))
        # Subsequent TRNG filling, patch installation and full non-retained heap use.
        m.uc.mem_write(BASE+0xc0,b'\xa5'*0x450)
        m.uc.mem_write(BASE+0x10c18,b'\x5a'*(2048+12))
        self.assertEqual(bytes(m.uc.mem_read(runtime,size)),m.b[offset:offset+size])
        self.assertEqual(m.status()['firmware_id'],meta['firmware_id'])
    def test_own_boot_screen_decodes_both_color_planes_and_uses_full_refresh(self):
        import hashlib
        m=Machine();m.run(BASE+0x2224)
        frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
        if m.meta.get('boot_identity_address'):
            sys.path.insert(0,str(ROOT/'source/firmware'))
            from build import boot_asset,identity_preview
            from render import quantize
            baseline=(ROOT/'source/reference/hmclock-bwr-baseline-app.bin').read_bytes()
            expected=quantize(identity_preview(boot_asset(m.meta['version'])[0],m.b,'00:00:00:00:00:00',m.meta['version']))['frame']
            self.assertEqual(frame,expected)
        else:self.assertEqual(hashlib.sha256(frame).hexdigest(),m.meta['boot_frame_sha256'])
        self.assertTrue(any(a==BASE+0x3c10 and r0==0x22 and r1==0xf7 for a,r0,r1 in m.commands))
        self.assertIn(b'ELINK-BWR-',m.b);self.assertTrue(m.status()['busy'])
    def test_frame_checksum_sequencing_and_display_receipt(self):
        m=Machine();frame=bytes((i*31)%256 for i in range(8000));packets=list(image_packets(frame,321))
        m.cmd(packets[0]);m.cmd(b'\x96\x01\x00\x01');self.assertEqual(m.status()['error'],1)
        for p in packets[1:-1]:m.cmd(p)
        self.assertEqual(bytes(m.uc.mem_read(BASE+0xdedc,4000)),frame[:4000])
        self.assertEqual(bytes(m.uc.mem_read(BASE+0xf15c,4000)),frame[4000:])
        before=m.status();self.assertEqual(before['received'],8000)
        m.cmd(packets[-1]);s=m.status();self.assertTrue(s['busy']);self.assertEqual(s['display_generation'],0)
        m.busy=1;m.run(int(m.meta['labels']['finish'],16));self.assertTrue(m.status()['busy'])
        m.busy=0;m.run(int(m.meta['labels']['finish'],16));self.assertEqual(m.status()['display_generation'],1)
        m.run(int(m.meta['labels']['finish'],16));self.assertEqual(m.status()['display_generation'],1)
        self.assertEqual([v for v in m.gpio if v[0] in (2,0x25,0x29)],[(2,0x300,1),(0x25,0x300,1),(0x29,0x300,1)])
        self.assertTrue(any(a==BASE+0x3c10 and r0==0x22 and r1==0xf7 for a,r0,r1 in m.commands))
    def test_reject_bad_lengths_bounds_checksum_and_busy(self):
        m=Machine()
        for b in [b'',b'\x94',b'\x94\x03\x0a',b'\x94\x02\x00',b'\x95',b'\x96\xff\xff\x00',b'\x97\x00\x00']:
            m.cmd(b);self.assertEqual(m.status()['error'],1 if b else 0)
        m.cmd(b'\x95\x01\x00\x00\x00');m.cmd(b'\x97\x01\x00');self.assertEqual(m.status()['error'],1)
        m.uc.mem_write(STATE+8,b'\x01');m.cmd(b'\x95\x01\x00\x00\x00');self.assertEqual(m.status()['error'],2)
    def test_original_clock_command_requires_valid_time(self):
        m=Machine();m.cmd(b'\x90');self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC),BASE+0x6c9c)
        m.uc.mem_write(STATE+7,b'\x01');m.cmd(bytes([0x91])+bytes(11))
        self.assertEqual(m.status()['error'],1);self.assertFalse(m.status()['time_initialized'])
        m.cmd(sync_packet());self.assertEqual(m.status()['display_mode'],0)
        self.assertTrue(m.status()['time_initialized'])
    def test_refresh_policy(self):
        m=Machine();m.cmd(b'\x94\x02\x03')
        choices=[]
        for _ in range(6):
            m.run(BASE+0x4174);choices.append([v for a,c,v in m.commands if a==BASE+0x3c10 and c==0x22][-1])
        # A refresh with no successfully prepared clock reference must remain full.
        self.assertEqual(choices,[0xf7]*6)
    def test_banks_and_native_config_preserved(self):
        spi=firmware_file('-spi.bin').read_bytes();old=(ROOT/'source/reference/hmclock-bwr-baseline-spi.bin').read_bytes()
        for bank in [0x2000,0x14000]:
            size,crc=struct.unpack_from('<II',spi,bank+4)
            self.assertEqual(zlib.crc32(spi[bank+64:bank+64+size]),crc)
        self.assertEqual(spi[:0x18b0],old[:0x18b0]);self.assertEqual(spi[0x38000:],old[0x38000:])
    def test_wake_window_refresh_timing_and_transfer_expiry(self):
        m=Machine();m.cmd(bytes([0x99,3,5,40]));s=m.status()
        self.assertEqual((s['clock_refresh_minutes'],s['advertise_every_minutes'],s['advertise_window_seconds']),(3,5,40))
        window=int(m.meta['labels']['window'],16);m.run(window)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_R0),4000);self.assertEqual(m.uc.reg_read(UC_ARM_REG_R1),BASE+0x277d)
        m.uc.mem_write(BASE+0x124cc+0x48,b'\xff'*4)
        m.uc.mem_write(BASE+0x104dc+0x2c,b'\0'*4)
        for _ in range(4):m.run(int(m.meta['labels']['adv'],16))
        self.assertNotIn(BASE+0x6af0,m.calls)
        m.run(int(m.meta['labels']['adv'],16));self.assertEqual(m.calls.count(BASE+0x6af0),1)
        m.cmd(b'\x95\x01\x00\x00\x00')
        for _ in range(3):m.run(int(m.meta['labels']['adv'],16))
        self.assertEqual(m.status()['display_mode'],0);self.assertEqual(m.status()['error'],3)
        # Clock timing is exercised through the actual replacement entry in test_product_ui.
if __name__=='__main__':unittest.main()
