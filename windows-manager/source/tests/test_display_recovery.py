"""Fault injection at physical BUSY and receive-RAM boundaries."""
import struct,unittest
from test_firmware import Machine,ROOT,BASE,STATE,END
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_LR,UC_ARM_REG_SP
from protocol import image_packets

class RadioMachine(Machine):
    def __init__(self):
        self.timers=[];self.cancelled=[]
        super().__init__()
    def hook(self,uc,a,size,_):
        # Execute native advertising/disconnect. Model only ROM messages/timers.
        if a==BASE+0x6af0:return
        if a==BASE+0x27a0:
            uc.reg_write(UC_ARM_REG_R0,BASE+0x1c000)
        elif a==BASE+0x27f4:
            delay=uc.reg_read(UC_ARM_REG_R0)
            assert delay>0,'SDK zero-delay timer asserts forever'
            self.timers.append((delay,uc.reg_read(UC_ARM_REG_R1)))
            uc.reg_write(UC_ARM_REG_R0,1)
        elif a==BASE+0x2830:self.cancelled.append(uc.reg_read(UC_ARM_REG_R0))
        elif a==0x07f1bf1a:uc.reg_write(UC_ARM_REG_R0,3)
        elif a in (BASE+0x2588,BASE+0x2ad0,0x07f1beb6):pass
        else:return super().hook(uc,a,size,_)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))

class DisplayRecovery(unittest.TestCase):
    def machine(self):return Machine()
    def test_continuous_advertising_and_remote_disconnect_use_native_start(self):
        m=RadioMachine();m.run(BASE+0x6af0)
        self.assertEqual(m.timers,[])
        self.assertEqual(bytes(m.uc.mem_read(BASE+0x104dc,1)),b'\x01')
        self.assertEqual(bytes(m.uc.mem_read(BASE+0x124cc+15,1)),b'\0')
        packet=BASE+0x1b000;m.uc.mem_write(packet,b'\0\0\x13')
        m.uc.reg_write(UC_ARM_REG_R1,packet)
        m.uc.reg_write(UC_ARM_REG_R2,0);m.uc.reg_write(UC_ARM_REG_R3,0)
        m.run(BASE+0x4514)
        self.assertEqual(m.timers,[])
        self.assertEqual(bytes(m.uc.mem_read(BASE+0x104dc,1)),b'\x01')
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP),BASE+0x1d000)
        self.assertNotIn(BASE+0x2cc4,m.calls)
        self.assertEqual(m.commands,[])
        m.cmd(b'\x99\x01\x01\x28')
        m.uc.mem_write(BASE+0x104dc,b'\0');m.run(BASE+0x6af0)
        self.assertEqual(m.timers,[(4000,BASE+0x277d)])
        m.cmd(b'\x99\x01\x01\0');self.assertEqual(m.status()['advertise_window_seconds'],0)
        for window in (1,9,121,255):
            m.cmd(bytes([0x99,1,1,window]));self.assertEqual(m.status()['error'],1)
    def test_shared_initialization_supplies_powered_reset_and_settle_delay(self):
        m=self.machine();address=int(m.meta['panel_reset_address'],16)
        m.uc.mem_write(BASE+0x10550,struct.pack('<I',16))
        native_call=next(m.decoder.disasm(m.b[0x3f74:0x3f78],BASE+0x3f74))
        self.assertEqual(native_call.mnemonic,'bl')
        self.assertEqual(int(native_call.op_str.lstrip('#'),16),address&~1)
        count=0;events=[]
        def trace(uc,a,size,_):
            nonlocal count
            count+=1
            if a==BASE+0x505c:events.append((count,uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
        m.uc.hook_add(UC_HOOK_CODE,trace)
        m.uc.reg_write(UC_ARM_REG_LR,END|1)
        m.uc.emu_start(address,END,count=1000000)
        self.assertEqual([(pin,value) for _,pin,value in events],[(16,0),(16,1)])
        self.assertGreaterEqual(events[1][0]-events[0][0],80000)
        self.assertGreaterEqual(count-events[1][0],360000)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP),BASE+0x1d000)
    def test_native_geometry_can_be_read_without_triggering_refresh(self):
        m=self.machine();config=bytes((i*3)%256 for i in range(128))
        m.uc.mem_write(BASE+0x104dc,config);m.cmd(b'\x9b')
        self.assertEqual(m.published,config);self.assertEqual(m.commands,[])
        m.cmd(b'\x9b\0');self.assertEqual(m.status()['error'],1)
    def test_receive_ram_readback_detects_mutation_and_rejects_invalid_reads(self):
        m=self.machine();frame=bytes((i*31)%256 for i in range(8000))
        for p in list(image_packets(frame,22))[:-1]:m.cmd(p)
        output=bytearray()
        for plane in (0,4000):
            for off in range(0,4000,128):
                m.cmd(b'\x9a'+struct.pack('<H',plane+off))
                self.assertEqual(len(m.published),128)
                output.extend(m.published[:min(128,4000-off)])
        self.assertEqual(output,frame)
        m.uc.mem_write(BASE+0xdedc+3,b'\x55')
        m.cmd(b'\x9a\0\0');self.assertNotEqual(m.published,frame[:128])
        for p in (b'\x9a',b'\x9a\x40\x1f',b'\x9a\xff\xff'):
            m.cmd(p);self.assertEqual(m.status()['error'],1)
    def test_stuck_busy_powers_off_without_false_success_and_allows_retry(self):
        m=self.machine();m.run(BASE+0x4174);m.busy=1
        for _ in range(224):m.run(BASE+0x4208)
        self.assertTrue(m.status()['busy']);self.assertEqual(m.status()['error'],0)
        m.run(BASE+0x4208);s=m.status()
        self.assertFalse(s['busy']);self.assertEqual(s['error'],4)
        self.assertEqual(s['display_generation'],0)
        self.assertTrue(any(a==BASE+0x3c10 and c==0x10 and v==1 for a,c,v in m.commands))
        self.assertEqual(m.pin_values[0x23 if m.meta.get('boot_identity_address') else 0],0)
        self.assertEqual(bytes(m.uc.mem_read(BASE+0x17758+3,1)),b'\x01')
        self.assertEqual(bytes(m.uc.mem_read(BASE+0x177b4,1)),b'\x01')
        m.cmd(b'\x95\x02\x00\x00\x00');s=m.status()
        self.assertEqual(s['error'],0);self.assertEqual(s['display_mode'],1)
        m.run(BASE+0x4174);self.assertEqual(bytes(m.uc.mem_read(STATE+26,1)),b'\0')
    def test_normal_busy_completion_keeps_generation_and_sleep_contract(self):
        m=self.machine();m.run(BASE+0x4174);m.busy=1
        for _ in range(10):m.run(BASE+0x4208)
        m.busy=0;m.run(BASE+0x4208);s=m.status()
        self.assertFalse(s['busy']);self.assertEqual(s['error'],0)
        self.assertEqual(s['display_generation'],1)
        m.run(BASE+0x4208);self.assertEqual(m.status()['display_generation'],1)
if __name__=='__main__':unittest.main()
