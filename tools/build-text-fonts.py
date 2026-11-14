"""Freeze the existing host glyphs for browser rendering; never accesses a device."""
import hashlib
import json
import datetime
from pathlib import Path
import struct
import sys

WEB = Path(__file__).resolve().parents[1]
HOST = WEB / 'windows-manager/source'
sys.path.insert(0, str(HOST / 'backend'))
from bitmap_fonts import cells, font_source
from protocol import reminder_metadata
from render import render
from photo_calendar import date_column

SIZES = (12, 14, 16, 17, 18, 20, 24, 28, 32, 64)


def characters(size):
    native = 12 if size in (12, 14, 15, 24, 28, 44) else 16
    lines = font_source(native)
    points = (int(line.split()[1]) for line in lines if line.startswith('ENCODING ')) if native == 12 else (int(line.split(':')[0], 16) for line in lines)
    return ''.join(chr(cp) for cp in sorted(points) if cp >= 32 and not 0x7f <= cp <= 0x9f and not 0xd800 <= cp <= 0xdfff and (native != 12 or cp not in (0x3031, 0x3032)))


def build():
    manifest = {'format': 'ELF1', 'pixel_sources': ['terminus', 'fusion', 'unifont'], 'bitmap_hints': {'18': {'雪': 'Native grid with separate rain dots and lower horizontal strokes'}}, 'outline_rasterization': False, 'source': json.loads((HOST / 'fonts/preview-fonts.json').read_text('utf-8')), 'sizes': {}}
    for size in SIZES:
        glyphs = cells('0123456789:' if size == 64 else characters(size), size)
        index, pixels = bytearray(), bytearray()
        for ch, cell in sorted(glyphs.items()):
            assert 0 < cell.width <= 255 and cell.height == size
            packed = cell.tobytes()
            assert len(packed) == ((cell.width + 7) // 8) * size
            index.extend(struct.pack('<IIB', ord(ch), len(pixels), cell.width))
            pixels.extend(packed)
        raw = struct.pack('<4sII', b'ELF1', size, len(glyphs)) + index + pixels
        name = f'text-{size}.bin'
        (WEB / 'fonts' / name).write_bytes(raw)
        manifest['sizes'][size] = {'file': name, 'glyphs': len(glyphs), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        print(f'{size}px: {len(glyphs)} glyphs, {len(raw)} bytes', flush=True)
    (WEB / 'fonts/text-fonts.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    calendar = json.loads((WEB / 'fonts/calendar-glyphs.json').read_text('utf-8'))
    for size, group in calendar.items():
        for ch, cell in cells(''.join(group), int(size)).items():
            group[ch] = {'width': cell.width, 'bits': ''.join('1' if v else '0' for v in cell.get_flattened_data())}
    (WEB / 'fonts/calendar-glyphs.json').write_text(json.dumps(calendar, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    write_fixtures()


def write_fixtures():
    fixtures = {'glyphs': [], 'frames': [], 'metadata': [], 'date_columns': []}
    for size in SIZES:
        sample = '0123456789:' if size == 64 else 'Aa09/%…，。今日天后星期中文龘雪'
        for ch, cell in sorted(cells(sample, size).items()):
            fixtures['glyphs'].append({'size': size, 'char': ch, 'width': cell.width, 'hex': cell.tobytes().hex()})
    specs = [
        {'kind': 'notice', 'title': '任务提醒', 'body': '检查电量', 'footer': '2026/11/13 星期五'},
        {'kind': 'notice', 'title': '很长的公告标题需要缩小字号', 'body': '第一行任务内容\n第二行检查完成', 'footer': '中文 Aa09/%，。', 'red': False},
        {'kind': 'meeting', 'title': '会议室 A', 'occupied': True, 'body': '产品评审\n忽略第二行', 'footer': '10:00 - 11:30'},
        {'kind': 'meeting', 'title': '会议室 B', 'occupied': False, 'body': '欢迎使用', 'footer': ''},
        {'kind': 'calendar', 'title': '今日安排', 'body': '检查设备\n发送提醒\n完成测试', 'footer': '星期五'},
        {'kind': 'clock', 'title': '2026/11/13 星期五', 'body': '23:59', 'footer': '荷兰 中文'},
        {'kind': 'notice', 'title': '龘字', 'body': 'Aa09/%…，。', 'footer': ''},
    ]
    for i, spec in enumerate(specs):
        percent = (None, 0, 100, 51, 9, 88, 42)[i]
        fixtures['frames'].append({'spec': spec, 'percent': percent, 'frame': render(spec, percent)['frame'].hex()})
    options = {'repeat_mask': 31, 'check_minutes': 5, 'duration_minutes': 10, 'utc_offset': 28800}
    for title in ('中文任务 Aa09/%', '长任务名称需要自动省略显示并保持基线', '龘字'):
        for large in (False, True):
            fixtures['metadata'].append({'title': title, 'options': options, 'large': large, 'hex': reminder_metadata(title, options, large).hex()})
    for value in ('2026-11-13', '2026-10-23', '2026-10-24', '2027-01-01', '2025-08-20', '2024-02-29'):
        fixtures['date_columns'].append({'date': value, 'frame': date_column(datetime.date.fromisoformat(value))['frame'].hex()})
    (WEB / 'tests/text-font-fixtures.json').write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    build()
