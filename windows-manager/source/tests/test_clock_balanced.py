"""Decode real compiled SPI payloads, including the native border's LUT selection."""
import unittest
from test_product_ui import ProductMachine,BASE

class ClockBalanced(unittest.TestCase):
    def pair(self,mode=1,start=5,end=6):
        m=ProductMachine();m.cmd(bytes([0x94,mode,60]))
        old=m.draw(minute=start,force=128);m.finish();m.stream.clear();m.commands.clear()
        new=m.draw(minute=end)
        return m,old,new

    def test_native_border_lut1_and_all_unchanged_pixels_are_neutral(self):
        for mode in (1,2):
            m,old,new=self.pair(mode)
            self.assertEqual(m.stream[-70+7:-70+14],[0]*7,'Native border5 follows LUT1, which must be neutral')
            self.assertEqual(len(m.stream),8070)
            drive,red,lut=map(bytes,(m.stream[:4000],m.stream[4000:8000],m.stream[8000:]))
            for p in range(4000):
                changed=old[p]^new[p]
                self.assertEqual(drive[p],255^changed)
                self.assertEqual(red[p],new[p]&changed)
                for bit in (1,2,4,8,16,32,64,128):
                    row=2*bool(red[p]&bit)+bool(drive[p]&bit)
                    self.assertEqual(lut[row*7:row*7+7],
                        bytes(7) if not changed&bit else m.b[0xdc18+(7 if new[p]&bit else 0):0xdc18+(14 if new[p]&bit else 7)])
            self.assertEqual(new[4000:],bytes(4000));m.finish()

    def test_balanced_mode_uses_the_original_fast_pulses_and_timing(self):
        m,old,new=self.pair()
        lut=bytes(m.stream[-70:])
        self.assertEqual(lut[:7],m.b[0xdc18:0xdc1f])
        self.assertEqual(lut[14:21],m.b[0xdc1f:0xdc26])
        self.assertEqual(lut[28:],m.b[0xdc18+28:0xdc18+70])
        m.finish();self.assertEqual(m.status()['display_generation'],2)

    def test_dark_mode_boosts_only_new_black_ink_then_commits_one_generation(self):
        m,old,new=self.pair(2);self.assertEqual(m.status()['display_generation'],1)
        m.stream.clear();m.run(BASE+0x4208)
        self.assertTrue(m.status()['busy']);self.assertEqual(m.status()['display_generation'],1)
        self.assertEqual(len(m.stream),8070)
        mask=bytes((a^b)&(255^b) for a,b in zip(old[:4000],new[:4000]))
        self.assertEqual(bytes(m.stream[:4000]),bytes(255^b for b in mask))
        self.assertEqual(bytes(m.stream[4000:8000]),bytes(4000))
        lut=bytes(m.stream[-70:]);self.assertEqual(lut[:7],m.b[0xdc68:0xdc6f])
        self.assertEqual(lut[7:28],bytes(21));self.assertEqual(lut[28:],m.b[0xdc68+28:0xdc68+70])
        m.run(BASE+0x4208);self.assertFalse(m.status()['busy']);self.assertEqual(m.status()['display_generation'],2)
        self.assertEqual(bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000)),new)

    def test_a_failed_boost_never_commits_the_pending_minute(self):
        m,old,new=self.pair(2);m.run(BASE+0x4208);m.busy=1
        for _ in range(225):m.run(BASE+0x4208)
        self.assertEqual(m.status()['error'],4);self.assertEqual(m.status()['display_generation'],1)
        m.busy=0;m.draw(minute=7);self.assertEqual(m.update_sequence(),0xf7);m.finish()
        self.assertEqual(m.status()['display_generation'],2)

if __name__=='__main__':unittest.main()
