import unittest,struct,sys,json,base64,hashlib
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/backend'),str(ROOT/'source/tests')]
from test_firmware import Machine,BASE,END,firmware_file
from ota import image,page_packets,validate_package,BOARD

class OtaMachine(Machine):
    def __init__(self):
        self.native=False;self.flash=bytearray((ROOT/'source/reference/hmclock-bwr-baseline-spi.bin').read_bytes());self.flash+=b'\xff'*(0x40000-len(self.flash));self.erases=[]
        super().__init__()
    def hook(self,uc,a,size,arg):
        if self.native and a==BASE+0x6c9c:return
        r0=uc.reg_read(UC_ARM_REG_R0);r1=uc.reg_read(UC_ARM_REG_R1);r2=uc.reg_read(UC_ARM_REG_R2)
        if a==0x7f1e0ac:uc.mem_write(r0,bytes(uc.mem_read(r1,r2)))
        elif a==BASE+0x6828:
            assert 0<=r0<0x40000 and r0+r1<=0x40000
            uc.mem_write(r2,bytes(self.flash[r0:r0+r1]));uc.reg_write(UC_ARM_REG_R0,r1)
        elif a==BASE+0x671c:
            length=(r1+4095)//4096*4096;self.erases.append((r0,length));self.flash[r0:r0+length]=b'\xff'*length
        elif a==BASE+0x67c4:
            b=bytes(uc.mem_read(r1,r2))
            for i,value in enumerate(b):self.flash[r0+i]&=value
        elif a in (BASE+0x42e8,BASE+0x6890,BASE+0x6990,BASE+0x2ad0):uc.reg_write(UC_ARM_REG_R0,0)
        else:return super().hook(uc,a,size,arg)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def cmd(self,b):
        self.native=False;super().cmd(b)
        if self.uc.reg_read(UC_ARM_REG_PC)==BASE+0x6c9c:
            self.native=True;self.uc.emu_start((BASE+0x6c9c)|1,END,count=20000);self.native=False

class Ota(unittest.TestCase):
    def test_malformed_ota_packets_do_not_reach_flash_erase(self):
        m=OtaMachine()
        for p in [b'\xa0',b'\xa0\x00\x01\x00',b'\xa2',b'\xa3']:
            m.cmd(p);self.assertEqual(m.status()['error'],1);self.assertFalse(m.erases)
    def test_actual_native_upload_invalid_until_commit_and_readback(self):
        m=OtaMachine();old=bytes(m.flash[0x2000:0x14000]);raw=m.b
        reminder=bytes((i*13)&255 for i in range(65536));m.flash[0x26000:0x36000]=reminder
        magic=raw.index(bytes.fromhex('79 13 a5 f9 86 ec 5a 06'));version=0xa50f0000+struct.unpack_from('<H',raw,magic+8)[0]
        wire=image(raw,version);m.cmd(b'\xa0\x00'+struct.pack('<H',len(raw)))
        self.assertEqual(m.erases,[(0x14000,((len(raw)+64+4095)//4096)*4096)])
        for off in range(0,len(wire),256):
            for packet in page_packets(wire[off:off+256]):m.cmd(packet)
        self.assertEqual(m.flash[0x14002],255)
        self.assertEqual(bytes(m.flash[0x2000:0x14000]),old)
        expected=bytearray(wire);expected[2]=255;expected[3]=old[3]+1
        for off in range(0,len(wire),128):
            m.cmd(b'\xa1'+struct.pack('<H',off));self.assertEqual(m.published,expected[off:off+128])
        m.cmd(b'\xa4');self.assertEqual(m.flash[0x14002],0xaa)
        self.assertEqual(bytes(m.flash[0x14040:0x14040+len(raw)]),raw)
        self.assertEqual(bytes(m.flash[0x2000:0x14000]),old)
        self.assertEqual(bytes(m.flash[0x26000:0x36000]),reminder,'Actual native OTA erase/program must preserve stored schedules')
    def test_abort_does_not_mark_incomplete_bank_valid(self):
        m=OtaMachine();m.cmd(b'\xa0\x00'+struct.pack('<H',len(m.b)))
        for p in page_packets(image(m.b,1)[:256]):m.cmd(p)
        m.cmd(b'\xa5');self.assertEqual(m.flash[0x14002],255)
        self.assertEqual(struct.unpack('<I',m.uc.mem_read(BASE+0x10558+12,4))[0],0)
    def test_package_identity_and_spi_rejection(self):
        raw=firmware_file('-app.bin').read_bytes()
        p={'format':'elink-update-1','board':BOARD,'application':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),'firmware_id':raw[0xe2f0:0xe2f4].hex()}
        self.assertEqual(validate_package(p)[0],raw)
        p['sha256']='0'*64
        with self.assertRaises(ValueError):validate_package(p)
if __name__=='__main__':unittest.main()
