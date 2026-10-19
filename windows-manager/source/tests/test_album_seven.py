"""Real compiled seven-frame paths and read-only retrieval; NOR/ROM are simulated."""
import unittest,struct,zlib,json,hashlib
from test_offline_album import AlbumMachine
from test_firmware import ROOT,BASE,FIRMWARE_DIR
from protocol import decode_album

class SevenAlbum(unittest.TestCase):
    def test_retained_state_size_and_long_transport_probe_preserve_storage_and_pixels(self):
        m=AlbumMachine();base=BASE+0x12140;m.uc.mem_write(base,b'\xa5'*160);m.run(int(m.meta['product_symbols']['product_album_init'],16))
        state=bytes(m.uc.mem_read(base,160));self.assertEqual(state[:104],bytes(104));self.assertEqual(state[124:],b'\xa5'*36)
        self.assertEqual(m.meta['offline_album']['state_bytes'],124)
        frame=m.frame();before=m.status()
        for size in (131,136):
            m.cmd(b'\x93'+bytes(size-1));self.assertEqual(m.status()['error'],1)
            m.cmd(bytes((0x94,before['mode'],before['full_every'])));self.assertEqual(m.status()['error'],0)
            self.assertEqual(m.frame(),frame);self.assertEqual(m.flash_events,[])

    def test_seven_frames_readback_wrap_and_cold_start_without_clock(self):
        m=AlbumMachine();frames=[bytes((i*k+index)%256 for i in range(8000)) for index,k in enumerate((3,5,7,11,13,17,19))]
        m.uc.mem_write(BASE+0x121c0,b'\xa5'*32)
        m.stage(frames);m.play(minutes=1440)
        a=decode_album(m.album());self.assertEqual((a['capacity'],a['count'],a['protocol_version']),(7,7,3))
        self.assertEqual(a['crc32'],[zlib.crc32(f) for f in frames]);self.assertEqual(m.frame(),frames[0])
        events=list(m.flash_events)
        for slot,frame in enumerate(frames):
            actual=bytearray()
            for off in range(0,8000,128):
                m.cmd(b'\xbd\x05'+bytes([slot])+struct.pack('<H',off));actual.extend(m.published);self.assertEqual(m.status()['error'],0)
            self.assertEqual(actual,frame)
        self.assertEqual(m.flash_events,events,'Retrieval must never program or erase Flash')
        # Set only the application elapsed counter; the actual next-frame and wrap paths execute.
        for index in (1,2,3,4,5,6,0):
            m.uc.mem_write(BASE+0x12140+112,struct.pack('<H',1440));m.minute();m.finish();self.assertEqual(m.frame(),frames[index])
        self.assertEqual(bytes(m.uc.mem_read(BASE+0x121c0,32)),b'\xa5'*32,'Retained-state boundary unchanged')
        self.assertTrue(all(0x40000<=a and a+n<=0x5e000 for _,a,n in events))
        m.cold_boot();m.run(BASE+0x2224);m.finish();m.minute();m.finish();self.assertEqual(m.frame(),frames[0]);self.assertFalse(m.status()['time_initialized'])

    def test_legacy_four_frame_config_and_pixels_migrate_without_writing(self):
        m=AlbumMachine();frames=[bytes([31+i])*8000 for i in range(4)];c=bytearray(40)
        c[:4]=b'ELG1';struct.pack_into('<IHBB',c,4,14,0,0,0) # sequence followed by overwritten CRC below
        struct.pack_into('<HBB',c,12,1440,4,0);struct.pack_into('<4I',c,16,*[zlib.crc32(f) for f in frames]);c[32:36]=bytes((0,20,40,76));c[36:40]=bytes((1,1,254,255));struct.pack_into('<I',c,8,zlib.crc32(c[:8]+c[12:38]))
        m.flash[0x40000:0x40028]=c
        for i,f in enumerate(frames):m.flash[0x4a000+i*8192:0x4a000+i*8192+8000]=f
        before=bytes(m.flash);m.cold_boot();m.run(BASE+0x2224);m.finish();m.minute();m.finish()
        self.assertEqual(m.frame(),frames[0]);a=decode_album(m.album());self.assertEqual(a['count'],4);self.assertEqual(a['photo_x'],[0,20,40,76]);self.assertEqual(m.flash,before)
        m.play(minutes=60);a=decode_album(m.album());self.assertEqual(a['sequence'],15);self.assertEqual(a['interval_minutes'],60);self.assertEqual(a['count'],4)

    def test_new_range_foreign_data_and_out_of_bounds_reads_never_write(self):
        for where in (0x52000,0x57fff,0x58000,0x5dfff):
            m=AlbumMachine();m.flash[where]=0;m.cmd(b'\xbd\x01');self.assertEqual(m.status()['error'],6);self.assertEqual(m.flash_events,[])
        m=AlbumMachine();m.stage([bytes([53])*8000]);m.play();events=list(m.flash_events)
        for packet in (b'\xbd\x05\x01\0\0',b'\xbd\x05\0\x40\x1f',b'\xbd\x05\xff\0\0',b'\xbd\x05\0\xff\xff'):
            m.cmd(packet);self.assertNotEqual(m.status()['error'],0)
        self.assertEqual(m.flash_events,events)

    def test_protected_native_bytes_unchanged_and_live_glyphs_identical(self):
        from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
        before=json.loads((ROOT/'build/firmware-1.5.10/manifest.json').read_text());after=json.loads((FIRMWARE_DIR/'manifest.json').read_text())
        old=(ROOT/'build/firmware-1.5.10/elink-bwr-1.5.10-app.bin').read_bytes();new=(FIRMWARE_DIR/f'elink-bwr-{after["version"]}-app.bin').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),'af8942121ecb2b84e2973ae6402c23a2b46c5193cb1af9364a00cd071e826058')
        initial_page=int(after['state_file_offset'],16)+7
        self.assertEqual((old[initial_page],new[initial_page]),(0,4))
        regions=[(0x2cc4,0x31c8),(0x8600,0x90a4),(0x9300,0xa46c),(0xa48c,0xb780),(0xb780,0xc2a0),(0xc8a4,0xd2b0),(0xe2f0,0xe2f4),(initial_page,initial_page+1)]
        calls={0x2274:'product_boot_battery',0xde26:'product_sync_valid',0xdf16:'product_view',0xdf2c:'product_control',0xe12c:'product_refresh',0xe13e:'product_finish',0xe172:'product_minute_tick'}
        for off,name in calls.items():
            regions.append((off,off+4))
            for raw,meta in ((old,before),(new,after)):
                addr=BASE+off if off<0xddd4 else int(meta['runtime_address'],16)+off-int(meta['runtime_load_offset'],16)
                ins=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(raw[off:off+4],addr));self.assertEqual(len(ins),1);self.assertEqual(ins[0].mnemonic,'bl');self.assertEqual(int(ins[0].op_str.lstrip('#'),16),int(meta['product_symbols'][name],16)&~1)
        self.assertEqual(len(old),len(new));self.assertEqual(before['runtime_bytes'],after['runtime_bytes'])
        stray=[hex(i) for i,(a,b) in enumerate(zip(old,new)) if a!=b and not any(lo<=i<hi for lo,hi in regions)];self.assertEqual(stray,[])
        def cells(raw,base):
            out={}
            for i in range(struct.unpack_from('<H',raw,base)[0]):
                ch,off=struct.unpack_from('<HH',raw,base+2+4*i);p=base+off;size=5+((raw[p+1]+7)//8)*raw[p+2];out[chr(ch)]=raw[p:p+size]
            return out
        a,b=cells(old,0xa48c),cells(new,0xa48c)
        self.assertEqual(set(a)-set(b),set('ACDEFLNKPMV%-第周'))
        for ch in b:self.assertEqual(a[ch],b[ch],ch)

if __name__=='__main__':unittest.main()
