"""Execute new application paths; SPI bus is the simulated hardware boundary."""
import hashlib
import json
import struct
import unittest
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_R0
from test_firmware import BASE, STATE, ROOT, FIRMWARE_DIR
from test_product_ui import ProductMachine, frame_matches
from protocol import image_packets


class PhotoMachine(ProductMachine):
    def __init__(self):
        self.flash = bytearray(b'\xff' * 0x80000)
        self.id_commands = []
        super().__init__()

    def hook(self, uc, address, size, data):
        if address == BASE + 0x4368:
            self.id_commands.append(uc.reg_read(UC_ARM_REG_R0))
            reply = (0, 0, 0, 0, 0xa1, 0x12)[len(self.id_commands) - 1]
            uc.reg_write(UC_ARM_REG_R0, reply)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        return super().hook(uc, address, size, data)


def upload(machine, frame, payload=17):
    machine.cmd(b'\x95' + struct.pack('<HH', 51, sum(frame) & 65535))
    for off in range(0, 8000, payload):
        machine.cmd(b'\x96' + struct.pack('<H', off) + frame[off:off + payload])
    machine.cmd(b'\x97' + struct.pack('<H', 51))
    machine.finish()


class PhotoCalendar(unittest.TestCase):
    def test_photo_date_refresh_preserves_left_image_and_existing_views(self):
        m = PhotoMachine()
        m.draw(year=2026, month=10, day=18, weekday=0, force=128)
        m.finish()
        frame = bytes((i * 31) & 255 for i in range(8000))
        upload(m, frame)
        m.cmd(b'\x9c\x03')
        self.assertEqual(m.status()['error'], 0)
        self.assertEqual(m.status()['display_mode'], 6)
        m.finish()
        before = bytes(m.uc.mem_read(BASE + 0xdedc, 4000)) + bytes(m.uc.mem_read(BASE + 0xf15c, 4000))
        for off in (0, 4000):
            self.assertEqual(before[off + 1216:off + 4000], frame[off + 1216:off + 4000])
        from bitmap_fonts import text_mask
        self.assertTrue(frame_matches(before, '2026/10', 12, 212-text_mask('2026/10',12).width//2, 2))
        self.assertTrue(frame_matches(before, '星期日', 18, 185, 62))
        generation = m.status()['display_generation']
        m.draw(year=2026, month=10, day=18, weekday=0, minute=59)
        self.assertEqual(m.status()['display_generation'], generation)
        after = m.draw(year=2026, month=10, day=19, weekday=1)
        m.finish()
        self.assertEqual(m.status()['display_generation'], generation + 1)
        self.assertTrue(frame_matches(after, '星期一', 18, 185, 62))
        for off in (0, 4000):
            self.assertEqual(after[off + 1216:off + 4000], before[off + 1216:off + 4000])
        self.assertNotEqual(before[:1216], after[:1216])
        m.cmd(b'\x9c\x01')
        self.assertEqual(m.status()['display_mode'], 3)
        m.finish()
        self.assertEqual(m.flash_events, [])

    def test_all_days_are_native_44px_pixels_after_compressed_font_decode(self):
        from bitmap_fonts import text_mask
        m=PhotoMachine();functions=json.loads((FIRMWARE_DIR/'product-functions.json').read_text())
        for day in range(1,32):
            m.uc.mem_write(BASE+0xdedc,b'\xff'*4000);m.uc.mem_write(BASE+0xf15c,bytes(4000))
            m.run(functions['photo_day']['address'],day)
            mask=text_mask(f'{day:02}',44);expected=bytearray(4000)
            self.assertEqual(mask.size,(54,44))
            for y in range(44):
                for x in range(54):
                    if mask.getpixel((x,y)):expected[(249-185-x)*16+(15+y)//8]|=128>>((15+y)%8)
            self.assertEqual(bytes(m.uc.mem_read(BASE+0xf15c,4000)),bytes(expected),day)
            self.assertEqual(bytes(m.uc.mem_read(BASE+0xdedc,4000)),bytes(v^255 for v in expected),day)
        self.assertEqual(m.flash_events,[])

    def test_large_packets_old_packets_and_oversize_boundary(self):
        for size in (17, 128):
            m = PhotoMachine()
            frame = bytes(i & 255 for i in range(8000))
            upload(m, frame, size)
            self.assertEqual(m.status()['received'], 8000)
            self.assertEqual(bytes(m.uc.mem_read(BASE + 0xdedc, 4000)), frame[:4000])
            self.assertEqual(bytes(m.uc.mem_read(BASE + 0xf15c, 4000)), frame[4000:])
        m = PhotoMachine()
        m.cmd(b'\x95\x01\x00\x00\x00')
        m.cmd(b'\x96\x00\x00' + bytes(129))
        self.assertEqual(m.status()['error'], 1)
        self.assertEqual(m.status()['received'], 0)

    def test_photo_rejects_missing_time_missing_image_and_busy(self):
        m = PhotoMachine()
        m.cmd(b'\x9c\x03')
        self.assertEqual(m.status()['error'], 1)
        m.draw(force=128)
        m.cmd(b'\x9c\x03')
        self.assertEqual(m.status()['error'], 2)
        m.finish()
        m.cmd(b'\x9c\x03')
        self.assertEqual(m.status()['error'], 1)

    def test_flash_diagnostic_reads_both_high_ends_without_writes(self):
        m = PhotoMachine()
        m.flash[0x40000:0x40004] = b'ABCD'
        m.flash[0x7fffc:0x80000] = b'WXYZ'
        m.cmd(b'\xbc')
        self.assertEqual(m.published, b'EFD1\x01\x80\x12\xa1ABCDWXYZ')
        self.assertEqual(m.id_commands, [0x90, 0, 0, 0, 0, 0])
        self.assertEqual(m.flash_events, [])
        m.cmd(b'\xbc\x00')
        self.assertEqual(m.status()['error'], 1)
        m.uc.mem_write(STATE + 8, b'\x01')
        m.cmd(b'\xbc')
        self.assertEqual(m.status()['error'], 2)
        self.assertEqual(len(m.id_commands), 6)

    def test_all_native_bytes_and_protected_spi_regions_unchanged(self):
        old = (ROOT / 'build/firmware-modules/elink-bwr-1.5.2-app.bin').read_bytes()
        meta = json.loads((FIRMWARE_DIR / 'manifest.json').read_text())
        new = (FIRMWARE_DIR / ('elink-bwr-' + meta['version'] + '-app.bin')).read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), 'd9e5c3a3283994fac9d9af46d81eacd1b5f74e650931b4efc1321ac29d98430e')
        # Application font data is compressed losslessly; the stricter 1.5.5 comparison validates each relocated BL.
        allowed = [(0x2cc4, 0x31c8), (0x7eb4, 0x8500), (0x8600, 0xa46c), (0xa48c,0xba00),
                   (0xba00, 0xc2a0), (0xc3c4,0xd2b0), (0x2274,0x2278), (0xde04, 0xe2d4), (0xe2f0, 0xe2f4)]
        self.assertEqual(len(old), len(new))
        for i, (a, b) in enumerate(zip(old, new)):
            if a != b:
                self.assertTrue(any(start <= i < end for start, end in allowed), hex(i))
        runtime_source = int(meta['runtime_load_offset'], 16)
        runtime_address = int(meta['runtime_address'], 16)
        refresh = runtime_source + int(meta['labels']['refresh'], 16) - 1 - runtime_address
        for start,end in ((refresh,0xe12c),(0xe130,0xe13e),(0xe142,0xe172),(0xe176,0xe2d4)):
            self.assertEqual(old[start:end],new[start:end],hex(start))
        self.assertEqual(old[0xe2f4:], new[0xe2f4:],
                         'Boot asset and existing hardware helpers must remain exact')
        spi = (FIRMWARE_DIR / ('elink-bwr-' + meta['version'] + '-spi.bin')).read_bytes()
        device = (ROOT / 'firmware-test/20261018-512k.bin').read_bytes()
        self.assertEqual(spi[:0x2000], device[:0x2000])
        self.assertEqual(spi[0x26000:0x3b000], device[0x26000:0x3b000])


if __name__ == '__main__':
    unittest.main()
