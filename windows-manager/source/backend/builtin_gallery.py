"""Shared, allowlisted native artwork from the GitHub web controller."""
import hashlib
import json
from pathlib import Path
import sys

SOURCE = Path(sys._MEIPASS) / 'source' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
WEB = SOURCE / 'web'


def gallery():
    return json.loads((WEB / 'config.json').read_text(encoding='utf-8'))['gallery']


def entry(path):
    if not isinstance(path, str):
        raise ValueError('内置图片路径不合法')
    match = next((item for item in gallery() if item['path'] == path), None)
    if match is None:
        raise ValueError('请选择内置图库中的图片')
    return match


def native(path):
    from render import frame_png
    item = entry(path)
    frame = (WEB / item['frame']).read_bytes()
    if len(frame) != 8000 or hashlib.sha256(frame).hexdigest() != item['sha256']:
        raise ValueError('内置图片像素校验失败，未发送')
    return {'frame': frame, 'png': frame_png(frame), 'sha256': item['sha256'],
            'red_pixels': sum(byte.bit_count() for byte in frame[4000:])}


def resource(path):
    allowed = {item[key] for item in gallery() for key in ('path', 'frame')}
    return WEB / path if path in allowed else None
