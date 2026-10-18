"""Prepare pixel-accurate photo-calendar previews; never connects to a device."""
import argparse
import datetime as dt
import io
import json
import re
from pathlib import Path
import sys

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/backend'))
from lunar import lunar_fields
from render import quantize, frame_png
from photo_calendar import date_column, next_term

# Same local civil-day approximation as the existing device calendar.
TERMS = '小寒 大寒 立春 雨水 惊蛰 春分 清明 谷雨 立夏 小满 芒种 夏至 小暑 大暑 立秋 处暑 白露 秋分 寒露 霜降 立冬 小雪 大雪 冬至'.split()
TERM_SECONDS = (0,1272283,2547462,3828568,5117483,6416376,7726093,9047327,
                10379235,11721860,13072410,14428379,15787551,17145937,18501082,
                19850188,21190911,22520708,23839844,25146961,26443845,27730671,29010666,30284551)
LEFT = 174


def lunar_label(day):
    _, month, number = lunar_fields(day)
    months = '正二三四五六七八九十冬腊'
    if number == 10:
        label = '初十'
    elif number == 20:
        label = '二十'
    elif number == 30:
        label = '三十'
    else:
        label = ('初' if number < 10 else '十' if number < 20 else '廿') + '一二三四五六七八九'[number % 10 - 1]
    return ('闰' if month & 128 else '') + months[month & 127] + '月' + label


def active_term(day):
    candidates = []
    for year in (day.year - 1, day.year):
        if year < 2020:
            continue
        yy = year - 2020
        leap = (yy - 1) // 4 + 1 if yy else 0
        base = 451804 + 20950 * yy - leap * 86400
        for name, seconds in zip(TERMS, TERM_SECONDS):
            date = dt.date(year, 1, 1) + dt.timedelta(days=(base + seconds) // 86400)
            if date <= day:
                candidates.append((date, name))
    return max(candidates)[1]


def compose(source, day):
    if not isinstance(day, dt.date) or not 2020 <= day.year <= 2051:
        raise ValueError('日期须在现有固件支持的2020..2051年范围内')
    fields = {'year_month': day.strftime('%Y/%m'), 'day': f'{day.day:02}',
              'weekday': '星期' + '一二三四五六日'[day.weekday()],
              'lunar': lunar_label(day), 'term': ' · '.join(next_term(day))}
    image = Image.new('RGB', (250, 122), 'white')
    image.paste(ImageOps.fit(source.convert('RGB'), (LEFT, 122), method=Image.Resampling.LANCZOS), (0, 0))
    with Image.open(io.BytesIO(date_column(day)['png'])) as column:
        image.paste(column.crop((LEFT, 0, 250, 122)), (LEFT, 0))
    boxes = [('year_month',174,2,76,12),('day',185,15,54,44),
             ('weekday',185,62,54,18),('lunar',174,84,76,12),('term',174,101,76,18)]
    return quantize(image), fields, boxes


def self_check(source):
    # Frozen calendar boundaries, a leap lunar month, a term change and a year boundary.
    assert lunar_label(dt.date(2026, 2, 17)) == '正月初一'
    days = (dt.date(2026,10,18), dt.date(2026,10,23), dt.date(2027,1,1), dt.date(2025,8,20))
    assert active_term(days[0]) == '寒露' and active_term(days[1]) == '霜降'
    assert lunar_label(days[-1]).startswith('闰')
    left = None
    for day in days:
        result, fields, boxes = compose(source, day)
        assert len(result['frame']) == 8000 and frame_png(result['frame']) == result['png']
        with Image.open(io.BytesIO(result['png'])) as image:
            current = image.crop((0, 0, LEFT, 122)).tobytes()
            assert left is None or left == current, 'Date rendering changed photo pixels'
            left = current
        assert fields['year_month'] == day.strftime('%Y/%m') and fields['day'] == f'{day.day:02}'
        for a, b in zip(boxes, boxes[1:]):
            assert a[2] + a[4] <= b[2], 'Date rows overlap'
    return {'cases': len(days), 'pixel_roundtrip': True, 'left_photo_unchanged_by_date': True,
            'lunar_leap_and_new_year': True, 'solar_term_change': True, 'hardware_access': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'source/opendesign/mockups/photo-calendar')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assets = ROOT / 'reference/epd213/standby-assets'
    sources = [('sunrise', '湖畔日出', assets / 'standby-250x122/01-sunrise-lake.png'),
               ('cat', '午后小猫', assets / 'standby-250x122/03-sleeping-cat.png'),
               ('mountain', '山间小居', assets / 'standby-chinese-250x122-20261007/09-chinese-mountain-retreat.png')]
    dates = ('2026-10-18', '2026-10-23', '2027-01-01', '2025-08-20')
    records = {'status': 'preview_only', 'hardware_access': False, 'left_pixels': [174,122],
               'right_start_x': 174, 'day_font': 'Noto Sans SC Black, native 44px, shared firmware layout',
               'dates': dates, 'images': [], 'frames': []}
    for name, title, path in sources:
        records['images'].append({'id': name, 'title': title})
        with Image.open(path) as image:
            if name == 'sunrise':
                records['checks'] = self_check(image)
            (output / f'{name}-photo.png').write_bytes(quantize(image)['png'])
            for date in dates:
                result, fields, boxes = compose(image, dt.date.fromisoformat(date))
                filename = f'{name}-{date}.png'
                (output / filename).write_bytes(result['png'])
                records['frames'].append({'image': name, 'date': date, 'file': filename,
                                           'sha256': result['sha256'], 'fields': fields})
    (output / 'previews.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    html = output / 'index.html'
    if html.exists():
        source = html.read_text(encoding='utf-8')
        data = '<script type="application/json" id="preview-data">' + json.dumps(records, ensure_ascii=False).replace('<', '\\u003c') + '</script>'
        if 'id="preview-data"' in source:
            source = re.sub(r'<script type="application/json" id="preview-data">.*?</script>',
                            lambda _: data, source, flags=re.S)
        else:
            source = source.replace('  <script src="app.js"></script>', '  ' + data + '\n  <script src="app.js"></script>')
        html.write_text(source, encoding='utf-8')
    print(json.dumps(records['checks'], indent=2))


if __name__ == '__main__':
    main()
