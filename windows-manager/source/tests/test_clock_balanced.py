"""Decode real compiled SPI payloads, including the native border's LUT selection."""
import unittest
from test_product_ui import ProductMachine,BASE
from test_firmware import END
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_SP

class NativeDisplay(ProductMachine):
    def __init__(self):self.reloads=[];self.recording=False;self.ram_command=0;super().__init__();self.native_display=True
    def run(self,address,r0=0):
        self.uc.reg_write(UC_ARM_REG_R0,r0);self.uc.reg_write(UC_ARM_REG_LR,END|1)
        self.uc.emu_start(address|1,END,count=8000000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==END or (address==BASE+0x6c98 and self.uc.reg_read(UC_ARM_REG_PC) in (BASE+0x6c94,BASE+0x6c9c)),hex(self.uc.reg_read(UC_ARM_REG_PC))
        assert self.uc.reg_read(UC_ARM_REG_SP)==BASE+0x1d000
    def hook(self,uc,address,size,data):
        if getattr(self,'native_display',False):
            if address==BASE+0x3f68:return
            if address==BASE+0x40e8:self.reloads.append({0x24:bytearray(),0x26:bytearray()});self.recording=True;return
            if address==BASE+0x4174:self.recording=False
            if address==BASE+0x3be8:self.ram_command=uc.reg_read(UC_ARM_REG_R0)
            if self.recording and self.ram_command in (0x24,0x26) and address in (BASE+0x4140,BASE+0x3cf4):
                b=bytes([uc.reg_read(UC_ARM_REG_R0)&255]) if address==BASE+0x4140 else bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
                self.reloads[-1][self.ram_command].extend(b);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
        return super().hook(uc,address,size,data)
def polarity_frames(lut,row):
    """Signed source-level frame tally, not charge or simulated optical density."""
    total=0
    for group in range(7):
        for phase,length in enumerate(lut[35+group*5:39+group*5]):
            level=(lut[row*7+group]>>(6-2*phase))&3
            assert level!=3
            total+={0:0,1:1,2:-1}[level]*length*(lut[39+group*5]+1)
    return total

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

    def test_dark_mode_compensates_new_black_and_removed_ink_then_commits_one_generation(self):
        m,old,new=self.pair(2);self.assertEqual(m.status()['display_generation'],1)
        m.stream.clear();m.run(BASE+0x4208)
        self.assertTrue(m.status()['busy']);self.assertEqual(m.status()['display_generation'],1)
        self.assertEqual(len(m.stream),8070)
        mask=bytes(a^b for a,b in zip(old[:4000],new[:4000]))
        self.assertEqual(bytes(m.stream[:4000]),bytes(255^b for b in mask))
        self.assertEqual(bytes(m.stream[4000:8000]),bytes(a&b for a,b in zip(new[:4000],mask)))
        lut=bytes(m.stream[-70:]);self.assertEqual(lut[:7],m.b[0xdc68:0xdc6f])
        self.assertEqual(lut[14:21],m.b[0xdc6f:0xdc76]);self.assertEqual(lut[7:14]+lut[21:28],bytes(14))
        self.assertEqual(lut[28:],m.b[0xdc68+28:0xdc68+70])
        m.run(BASE+0x4208);self.assertFalse(m.status()['busy']);self.assertEqual(m.status()['display_generation'],2)
        self.assertEqual(bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000)),new)

    def test_a_failed_boost_never_commits_the_pending_minute(self):
        m,old,new=self.pair(2);m.run(BASE+0x4208);m.busy=1
        for _ in range(225):m.run(BASE+0x4208)
        self.assertEqual(m.status()['error'],4);self.assertEqual(m.status()['display_generation'],1)
        m.busy=0;m.draw(minute=7);self.assertEqual(m.update_sequence(),0xf7);m.finish()
        self.assertEqual(m.status()['display_generation'],2)

    def test_an_idle_callback_after_a_cleared_timeout_cannot_start_compensation(self):
        m,old,new=self.pair(2);m.run(BASE+0x4208);m.busy=1
        for _ in range(225):m.run(BASE+0x4208)
        self.assertEqual(m.status()['error'],4);m.cmd(b'\x94\x02\x3c');m.busy=0;m.stream.clear()
        generation=m.status()['display_generation'];m.run(BASE+0x4208)
        self.assertFalse(m.status()['busy']);self.assertEqual(m.status()['display_generation'],generation)
        self.assertFalse(m.stream,'No pending frame means no extra compensation or display update')

    def test_boost_restores_both_black_and_white_native_vectors_on_every_change(self):
        m=ProductMachine();m.cmd(b'\x94\x02\x3c');old=m.draw(minute=5,force=128);m.finish()
        for minute in (6,5,6):
            m.stream.clear();new=m.draw(minute=minute);m.stream.clear();m.run(BASE+0x4208)
            self.assertEqual(len(m.stream),8070)
            changed=bytes(a^b for a,b in zip(old[:4000],new[:4000]))
            self.assertEqual(bytes(m.stream[:4000]),bytes(255^b for b in changed))
            self.assertEqual(bytes(m.stream[4000:8000]),bytes(a&b for a,b in zip(new[:4000],changed)))
            lut=bytes(m.stream[-70:])
            self.assertEqual(lut[14:21],m.b[0xdc6f:0xdc76],'Every removed stroke needs the matching original white boost')
            self.assertEqual(lut[:7],m.b[0xdc68:0xdc6f]);self.assertEqual(lut[7:14]+lut[21:28],bytes(14))
            m.run(BASE+0x4208);self.assertFalse(m.status()['busy']);old=new

    def test_balanced_mode_repeats_native_balanced_strokes_before_committing(self):
        m,old,new=self.pair(1);first=bytes(m.stream)
        m.stream.clear();m.run(BASE+0x4208)
        self.assertTrue(m.status()['busy']);self.assertEqual(m.status()['display_generation'],1)
        self.assertEqual(bytes(m.stream),first,'Light compensation repeats the original balanced program, including white')
        m.run(BASE+0x4208);self.assertFalse(m.status()['busy']);self.assertEqual(m.status()['display_generation'],2)

    def test_continuous_round_trips_keep_polarity_counts_symmetric_and_commit_once(self):
        for mode in (1,2):
            m=ProductMachine();m.cmd(bytes([0x94,mode,60]));old=m.draw(minute=5,force=128);m.finish()
            initial=old;balance=[0]*32000
            for generation,minute in enumerate((6,5,8,9,8,5),2):
                m.stream.clear();new=m.draw(minute=minute);stages=[bytes(m.stream)]
                m.stream.clear();m.run(BASE+0x4208);stages.append(bytes(m.stream))
                self.assertEqual(m.status()['display_generation'],generation-1);self.assertTrue(m.status()['busy'])
                for stage in stages:
                    self.assertEqual(len(stage),8070);lut=stage[8000:]
                    self.assertEqual(lut[7:14]+lut[21:28],bytes(14))
                    for p,(a,b) in enumerate(zip(old[:4000],new[:4000])):
                        changed=a^b;self.assertEqual(stage[p],255^changed);self.assertEqual(stage[4000+p],b&changed)
                        for bit in range(8):
                            mask=1<<bit
                            if changed&mask:balance[p*8+bit]+=polarity_frames(lut,2 if b&mask else 0)
                m.run(BASE+0x4208);self.assertEqual(m.status()['display_generation'],generation);self.assertFalse(m.status()['busy'])
                old=new
            self.assertEqual(old,initial);self.assertFalse(any(balance),'Closed digit loops must not accumulate one-sided extra drive')

    def test_continuous_native_init_and_full_frame_reload_keep_the_successful_target(self):
        m=NativeDisplay();m.cmd(b'\x94\x02\x3c');target=m.draw(minute=5,force=128);m.finish()
        self.assertEqual(bytes(m.reloads[0][0x24])+bytes(m.reloads[0][0x26]),target)
        for generation,minute in enumerate((6,5),2):
            start=len(m.reloads);target=m.draw(minute=minute);m.finish()
            self.assertEqual(len(m.reloads)-start,2)
            for record in m.reloads[start:]:
                self.assertEqual(bytes(record[0x24])+bytes(record[0x26]),target,'Execute the real native reload, not a fixed success stub')
            self.assertEqual(m.status()['display_generation'],generation);self.assertFalse(m.status()['busy'])

if __name__=='__main__':unittest.main()
