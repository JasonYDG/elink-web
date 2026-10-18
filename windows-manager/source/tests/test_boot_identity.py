"""Execute the real native ASCII renderer and per-device MAC formatter."""
import unittest,struct
from test_firmware import Machine,BASE,END,FIRMWARE_DIR
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R4,UC_ARM_REG_R7,UC_ARM_REG_PC,UC_ARM_REG_SP

class BootIdentity(unittest.TestCase):
    def test_distinct_mac_pixels_bounds_and_leds_off(self):
        frames=[]
        for address in ('18:BC:5A:6B:91:A7','18:BC:5A:6B:8E:BF','00:00:00:00:00:00','FF:FF:FF:FF:FF:FF','AA:AA:AA:AA:AA:AA'):
            m=Machine();draws=[]
            m.uc.mem_write(BASE+0x10520,bytes.fromhex(address.replace(':',''))[::-1])
            def capture(uc,a,size,_):
                if a==BASE+0x3b4c:
                    text=bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R2),19)).split(b'\0',1)[0]
                    draws.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1),text))
            m.uc.hook_add(UC_HOOK_CODE,capture)
            m.uc.mem_write(BASE+0xdedc-8,b'guard123')
            m.uc.mem_write(BASE+0xdedc+4000,b'guard456')
            m.uc.mem_write(BASE+0xf15c-8,b'guard789')
            m.uc.mem_write(BASE+0xf15c+4000,b'guardabc')
            m.run(BASE+0x2224)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC),END)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP),BASE+0x1d000)
            self.assertEqual(draws,[(19,61,b'BWR 2.13 / 250x122'),(218,87,b'--%'),(20,87,address.encode())])
            for addr,guard in ((0xdedc-8,b'guard123'),(0xdedc+4000,b'guard456'),(0xf15c-8,b'guard789'),(0xf15c+4000,b'guardabc')):
                self.assertEqual(bytes(m.uc.mem_read(BASE+addr,8)),guard)
            frames.append(bytes(m.uc.mem_read(BASE+0xdedc,4000)))
            import sys
            from pathlib import Path
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'firmware'))
            from build import boot_asset,identity_preview
            from render import quantize
            background=boot_asset(m.meta['version'])[0]
            baseline=(Path(__file__).resolve().parents[1]/'reference/hmclock-bwr-baseline-app.bin').read_bytes()
            expected=quantize(identity_preview(background,m.b,address,m.meta['version']))['frame']
            actual=frames[-1]+bytes(m.uc.mem_read(BASE+0xf15c,4000))
            self.assertEqual(actual,expected)
            if address=='18:BC:5A:6B:91:A7':
                from render import frame_png
                (FIRMWARE_DIR/'boot-preview-native.png').write_bytes(frame_png(actual))
            self.assertEqual([(pin,mode,value) for pin,mode,value in m.gpio if pin in (2,0x25,0x29)],[(2,0x300,1),(0x25,0x300,1),(0x29,0x300,1)])
            m.busy=0;m.run(BASE+0x4208)
            self.assertFalse(m.status()['busy'])
            self.assertTrue(all(value==1 for pin,mode,value in m.gpio if pin in (2,0x25,0x29)))
        self.assertEqual(len(set(frames)),5)
    def test_every_wake_drives_active_low_leds_high_before_pad_latch(self):
        # Execute the real periph_init tail: pads revert to pull-down after each wake.
        m=Machine();m.gpio.clear()
        sys_ctrl=0x50000012;m.uc.mem_write(sys_ctrl,struct.pack('<H',1))
        sp=BASE+0x1d000-24
        m.uc.mem_write(sp,struct.pack('<6I',0,0,0,0,0,END|1));m.uc.reg_write(UC_ARM_REG_SP,sp)
        m.uc.reg_write(UC_ARM_REG_R4,0x50000004);m.uc.reg_write(UC_ARM_REG_R7,0x20)
        m.uc.emu_start((BASE+0x6276)|1,END,count=10000)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC),END)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP),BASE+0x1d000)
        self.assertEqual(m.gpio,[(2,0x300,1),(0x25,0x300,1),(0x29,0x300,1)])
        self.assertEqual(struct.unpack('<H',m.uc.mem_read(sys_ctrl,2))[0],0x21)
if __name__=='__main__':unittest.main()
