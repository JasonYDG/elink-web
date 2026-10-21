"""Bounded first-use checks execute the exact candidate application; no hardware writes."""
import unittest
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1
from test_offline_album import AlbumMachine
from test_firmware import BASE

class TracedAlbum(AlbumMachine):
    def hook(self,uc,a,size,data):
        if a==BASE+0x6828 and hasattr(self,'reads'):
            self.reads.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
            if getattr(self,'corrupt_metadata',False) and uc.reg_read(UC_ARM_REG_R0)==0x40000 and self.flash_events:
                self.flash[0x40000]^=1;self.corrupt_metadata=False
        return super().hook(uc,a,size,data)

class AlbumPreflight(unittest.TestCase):
    def test_all_120_chunks_are_read_only_bounded_and_required_before_metadata(self):
        m=TracedAlbum();m.reads=[];frame=m.frame()
        m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,[])
        m.reads=[]
        for part in range(120):
            before=len(m.reads);m.cmd(bytes((0xbd,6,part)))
            self.assertEqual(m.published,b'ELAP'+bytes((part+1,120,0,0)))
            self.assertEqual(sum(n for a,n in m.reads[before:]),1024)
            self.assertEqual(m.flash_events,[])
        self.assertEqual(sum(n for a,n in m.reads),120*1024)
        self.assertEqual(m.frame(),frame)
        m.reads=[];m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],0)
        self.assertLessEqual(sum(n for a,n in m.reads),104,'Begin must not scan the full region again')
        self.assertEqual([event[0] for event in m.flash_events],['erase','write','write'])
        self.assertTrue(all(0x40000<=a and a+n<=0x41000 for op,a,n in m.flash_events))

    def test_foreign_bytes_at_each_range_boundary_never_allow_initialization(self):
        for where in (0x40000,0x403ff,0x40400,0x41fff,0x52000,0x5dfff):
            m=TracedAlbum();m.flash[where]=0;m.reads=[]
            failing=(where-0x40000)//1024
            for part in range(failing+1):m.cmd(bytes((0xbd,6,part)))
            self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,[])
            m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,[])

    def test_order_duplicate_restart_and_power_loss_preserve_the_guard(self):
        m=TracedAlbum();m.cmd(b'\xbd\x06\x01');self.assertEqual(m.status()['error'],1)
        m.cmd(b'\xbd\x06\x00');m.cmd(b'\xbd\x06\x01');m.cmd(b'\xbd\x06\x01')
        self.assertEqual(m.published,b'ELAP\x02\x78\x00\x00')
        m.cmd(b'\xbd\x06\x00');self.assertEqual(m.published,b'ELAP\x01\x78\x00\x00')
        for part in range(1,120):m.cmd(bytes((0xbd,6,part)))
        m.cold_boot();m.run(BASE+0x2224);m.finish();m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,[])
        for packet in (b'\xbd\x06',b'\xbd\x06\x78',b'\xbd\x06\xff',b'\xbd\x06\0\0'):
            m.cmd(packet);self.assertEqual(m.status()['error'],1);self.assertEqual(m.flash_events,[])

    def test_failed_metadata_creation_consumes_the_check_and_never_erases_again(self):
        m=TracedAlbum();m.reads=[]
        for part in range(120):m.cmd(bytes((0xbd,6,part)))
        m.corrupt_metadata=True;m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],6)
        events=list(m.flash_events);m.cmd(b'\xbd\x01')
        self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,events)

if __name__=='__main__':unittest.main()
