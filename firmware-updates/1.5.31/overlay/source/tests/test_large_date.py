import unittest
import json
import struct
from datetime import datetime, timedelta
from pathlib import Path
import sys
from PIL import Image, ImageChops

from test_midnight_calendar import BASE, FIRMWARE_DIR, NativeMinuteMachine
from protocol import sync_packet
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from preview_firmware import frame_image
from preview_large_date import BLACK, RED, english_date, layouts


def expected_frames(date):
    frames = {}
    for color, suffix in ((BLACK,''), (RED,'-red')):
        styles = layouts(date.month,date.day,color)
        styles['english'] = english_date(date.month,date.day,(date.weekday()+1)%7,color)
        frames.update((name+suffix,img) for name,img in styles.items())
    return frames


class LargeDate(unittest.TestCase):
    def test_english_labels_are_centered_with_the_approved_gap(self):
        background=Image.new('RGB',(78,122),RED)
        for month in range(1,13):
            for weekday in range(7):
                image=english_date(month,18,weekday).crop((0,0,78,122))
                ink=ImageChops.difference(image,background)
                _,top,_,bottom=ink.getbbox()
                month_bottom=ink.crop((0,0,78,61)).getbbox()[3]
                weekday_top=61+ink.crop((0,61,78,122)).getbbox()[1]
                self.assertLessEqual(abs(top-(122-bottom)),1)
                self.assertEqual(weekday_top-month_bottom,22)

    def test_native_pixels_for_every_date_in_a_leap_year(self):
        meta = json.loads((FIRMWARE_DIR / 'manifest.json').read_text())
        prefix = FIRMWARE_DIR / ('elink-bwr-' + meta['version'])
        flash = Path(str(prefix) + '-spi.bin').read_bytes()
        app = Path(str(prefix) + '-app.bin').read_bytes()
        start = json.loads((FIRMWARE_DIR / 'product-functions.json').read_text())['large_date']['address']
        cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        cpu.mem_map(BASE, 0x20000)
        cpu.mem_map(0x07f00000, 0x20000)
        cpu.mem_write(BASE, app)
        offset = int(meta['runtime_load_offset'], 16)
        cpu.mem_write(int(meta['runtime_address'],16), app[offset:offset+meta['runtime_bytes']])
        end = BASE+0x1f000

        def hardware(uc, address, size, unused):
            if address == BASE+0x6828:
                source, length = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
                uc.mem_write(uc.reg_read(UC_ARM_REG_R2), flash[source:source+length])
                uc.reg_write(UC_ARM_REG_R0, length)
            elif address == 0x07f1dfb8:
                uc.reg_write(UC_ARM_REG_R0, uc.reg_read(UC_ARM_REG_R0)//uc.reg_read(UC_ARM_REG_R1))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        for address in (BASE+0x6828, BASE+0x42e8, 0x07f1dfb8):
            cpu.hook_add(UC_HOOK_CODE, hardware, begin=address, end=address)
        for index in range(366):
            date = datetime(2028,1,1)+timedelta(days=index)
            cpu.mem_write(BASE+0x104dc+28, struct.pack('<II', date.month-1,date.day-1))
            cpu.mem_write(BASE+0xdd98+12, struct.pack('<I', (date.weekday()+1)%7))
            for style, expected in enumerate(expected_frames(date).values()):
                cpu.mem_write(BASE+0xdedc, b'\xff'*4000)
                cpu.mem_write(BASE+0xf15c, bytes(4000))
                cpu.reg_write(UC_ARM_REG_SP, BASE+0x1d000)
                cpu.reg_write(UC_ARM_REG_LR, end|1)
                cpu.reg_write(UC_ARM_REG_R0, style)
                cpu.emu_start(start|1,end,count=2500000)
                self.assertEqual((cpu.reg_read(UC_ARM_REG_PC),cpu.reg_read(UC_ARM_REG_R0)), (end,1))
                frame = b''.join(bytes(cpu.mem_read(BASE+off,4000)) for off in (0xdedc,0xf15c))
                self.assertTrue(frame_image(frame).tobytes()==expected.tobytes(), (date,style))

    def assert_frame(self, machine, date, style):
        frame = b''.join(bytes(machine.uc.mem_read(BASE + offset, 4000)) for offset in (0xdedc, 0xf15c))
        self.assertTrue(frame_image(frame).tobytes()==expected_frames(date)[style].tobytes(), (date,style))

    def test_selected_layout_survives_offline_midnight_in_either_ota_bank(self):
        for index, (style, start) in enumerate(zip(
                expected_frames(datetime(2026,11,18)),
                (datetime(2026, 11, 18, 23, 59, 37), datetime(2026, 12, 31, 23, 59),
                 datetime(2024, 2, 28, 23, 59), datetime(2026, 1, 31, 23, 59))*2, strict=True)):
            with self.subTest(style=style):
                m = NativeMinuteMachine().at(start)
                spi = (FIRMWARE_DIR / f"elink-bwr-{m.meta['version']}-spi.bin").read_bytes()
                bank = (0x2000, 0x14000)[index % 2]
                m.flash[bank:bank+0x12000] = spi[bank:bank+0x12000]
                m.cmd(bytes((0x9c, 4+index)))
                self.assertEqual(m.status()['error'], 0)
                self.assertTrue(m.status()['large_date'])
                self.assertTrue(m.status()['large_date_en'])
                self.assertTrue(m.status()['large_date_red'])
                m.finish()
                self.assert_frame(m, start, style)
                generation = m.status()['display_generation']
                m.tick()
                m.finish()
                self.assert_frame(m, start+timedelta(days=1), style)
                status = m.status()
                self.assertEqual((status['display_mode'],status['display_generation']), (9+index,generation+1))
                m.tick()
                self.assertFalse(m.status()['busy'])
                self.assertEqual(m.status()['display_generation'],generation+1)
                self.assertEqual(m.flash_events, [])

    def test_noon_and_manual_time_sync_keep_selected_layout(self):
        start = datetime(2026, 11, 18, 11, 59, 37)
        m = NativeMinuteMachine().at(start)
        spi = (FIRMWARE_DIR / f"elink-bwr-{m.meta['version']}-spi.bin").read_bytes()
        m.flash[:len(spi)] = spi
        for view, mode in ((5,10), (7,12), (8,13), (11,16)):
            m.at(start)
            m.cmd(bytes((0x9c,view)))
            m.finish()
            generation = m.status()['display_generation']
            m.tick()
            self.assertEqual(m.status()['display_generation'],generation)
            self.assertFalse(m.status()['busy'])
            for opcode in (0x91,0x9e):
                m.cmd(bytes([opcode])+sync_packet(start)[1:])
                self.assertEqual((m.status()['error'],m.status()['display_mode']), (0,mode))

    def test_missing_asset_bank_does_not_acknowledge_an_empty_screen(self):
        m = NativeMinuteMachine().at(datetime(2026, 11, 18, 10))
        gen = m.status()['display_generation']
        m.cmd(b'\x9c\x04')
        result = m.status()
        self.assertEqual((result['error'],result['busy'],result['display_generation']), (5,False,gen))
