"""Freeze the existing host glyphs for browser rendering; never accesses a device."""
import hashlib
import json
from pathlib import Path
import struct
import sys

WEB = Path(__file__).resolve().parents[1]
HOST = WEB / 'windows-manager/source'
sys.path.insert(0, str(HOST / 'backend'))
from bitmap_fonts import cells, noto_path
from protocol import reminder_metadata
from render import render

SIZES = (12, 14, 16, 17, 18, 20, 24, 28, 32, 64)


def characters():
    # Both checked-in Noto files expose a Unicode format-12 cmap.
    raw = Path(noto_path()).read_bytes()
    tables = dict((tag, offset) for tag, _, offset, _ in struct.iter_unpack('>4sIII', raw[12:12 + struct.unpack_from('>H', raw, 4)[0] * 16]))
    base = tables[b'cmap']
    for _, _, offset in struct.iter_unpack('>HHI', raw[base + 4:base + 4 + struct.unpack_from('>H', raw, base + 2)[0] * 8]):
        start = base + offset
        if struct.unpack_from('>H', raw, start)[0] != 12:
            continue
        count = struct.unpack_from('>I', raw, start + 12)[0]
        points = {cp for first, last, glyph in struct.iter_unpack('>III', raw[start + 16:start + 16 + count * 12]) for cp in range(first, last + 1) if glyph + cp - first}
        return ''.join(chr(cp) for cp in sorted(points) if cp >= 32 and not 0x7f <= cp <= 0x9f and not 0xd800 <= cp <= 0xdfff)
    raise ValueError('The bundled Noto font has no format-12 Unicode cmap')


def build():
    chars = characters()
    manifest = {'format': 'ELF1', 'source': json.loads((HOST / 'fonts/preview-fonts.json').read_text('utf-8')), 'sizes': {}}
    for size in SIZES:
        # These two vertical kana marks are 22px tall in the bundled 12px Fusion font.
        selected = chars.replace('\u3031', '').replace('\u3032', '') if size == 12 else chars
        glyphs = cells('0123456789:' if size == 64 else selected, size)
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
    write_fixtures()


def write_fixtures():
    fixtures = {'glyphs': [], 'frames': [], 'metadata': []}
    for size in SIZES:
        sample = '0123456789:' if size == 64 else 'Aa09/%…，。今日天后星期中文\U00020087'
        for ch, cell in sorted(cells(sample, size).items()):
            fixtures['glyphs'].append({'size': size, 'char': ch, 'width': cell.width, 'hex': cell.tobytes().hex()})
    specs = [
        {'kind': 'notice', 'title': '任务提醒', 'body': '检查电量', 'footer': '2026/11/13 星期五'},
        {'kind': 'notice', 'title': '很长的公告标题需要缩小字号', 'body': '第一行任务内容\n第二行检查完成', 'footer': '中文 Aa09/%，。', 'red': False},
        {'kind': 'meeting', 'title': '会议室 A', 'occupied': True, 'body': '产品评审\n忽略第二行', 'footer': '10:00 - 11:30'},
        {'kind': 'meeting', 'title': '会议室 B', 'occupied': False, 'body': '欢迎使用', 'footer': ''},
        {'kind': 'calendar', 'title': '今日安排', 'body': '检查设备\n发送提醒\n完成测试', 'footer': '星期五'},
        {'kind': 'clock', 'title': '2026/11/13 星期五', 'body': '23:59', 'footer': '荷兰 中文'},
        {'kind': 'notice', 'title': '\U00020087字', 'body': 'Aa09/%…，。', 'footer': ''},
    ]
    for i, spec in enumerate(specs):
        percent = (None, 0, 100, 51, 9, 88, 42)[i]
        fixtures['frames'].append({'spec': spec, 'percent': percent, 'frame': render(spec, percent)['frame'].hex()})
    options = {'repeat_mask': 31, 'check_minutes': 5, 'duration_minutes': 10, 'utc_offset': 28800}
    for title in ('中文任务 Aa09/%', '长任务名称需要自动省略显示并保持基线', '\U00020087字'):
        for large in (False, True):
            fixtures['metadata'].append({'title': title, 'options': options, 'large': large, 'hex': reminder_metadata(title, options, large).hex()})
    (WEB / 'tests/text-font-fixtures.json').write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    build()
