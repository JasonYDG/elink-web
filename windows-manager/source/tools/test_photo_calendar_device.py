"""Explicit manual 1.5.4 test: read-only Flash probe and optional RAM-only photo page."""
import argparse
import asyncio
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/backend'))
from protocol import CONTROL, decode_status, sync_packet


def decode_diagnostic(raw):
    if len(raw) != 16 or raw[:6] != b'EFD1\x01\x80':
        raise ValueError('尚未收到1.5.4只读诊断回应')
    return {'legacy_90h_id': hex(int.from_bytes(raw[6:8], 'little')),
            'max_image_payload': raw[5], 'sample_0x40000': raw[8:12].hex(),
            'sample_0x7fffc': raw[12:16].hex(),
            'capacity_independently_verified': False}


def photo_frame(path):
    from PIL import Image, ImageOps
    from render import quantize
    with Image.open(path) as source:
        source = ImageOps.exif_transpose(source).convert('RGB')
        photo = ImageOps.fit(source, (174, 122), method=Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (250, 122), 'white')
    canvas.paste(photo, (0, 0))
    return quantize(canvas)['frame']


async def main(args):
    from bleak import BleakClient
    async with BleakClient(args.address, timeout=20) as client:
        async def write(packet):
            await asyncio.wait_for(client.write_gatt_char(CONTROL, packet, response=True), 8)

        async def query(packet, decode):
            await write(packet)
            for _ in range(5):
                await asyncio.sleep(0.1)
                raw = bytes(await asyncio.wait_for(client.read_gatt_char(CONTROL), 8))
                try:
                    return decode(raw)
                except ValueError:
                    continue
            raise RuntimeError('设备回应无效；停止操作，未自动重传')

        async def status():
            return await query(b'\x93', decode_status)

        async def idle():
            deadline = time.monotonic() + 200
            while True:
                state = await status()
                if state['error']:
                    raise RuntimeError('设备错误：' + str(state['error']))
                if not state['busy']:
                    return state
                if time.monotonic() > deadline:
                    raise TimeoutError('等待刷屏超时；停止操作，未重发提交')
                await asyncio.sleep(0.5)

        state = await idle()
        if state['firmware_id'] != args.firmware_id:
            raise RuntimeError('设备固件ID与此测试包不符，停止：' + state['firmware_id'])
        diagnostic = await query(b'\xbc', decode_diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        if args.clock:
            await write(b'\x98')
            print(json.dumps(await idle(), ensure_ascii=False, indent=2))
        if not args.photo:
            return
        frame = photo_frame(args.photo)
        await write(b'\x9e' + sync_packet()[1:])
        state = await idle()
        payload = min(128, max(17, client.mtu_size - 6))
        transfer = 154
        print('图片像素包大小：', payload, '；包数：', (8000 + payload - 1) // payload, flush=True)
        await write(b'\x95' + struct.pack('<HH', transfer, sum(frame) & 65535))
        for off in range(0, 8000, payload):
            await write(b'\x96' + struct.pack('<H', off) + frame[off:off + payload])
            state = await status()
            if state['error'] or state['received'] != min(off + payload, 8000):
                raise RuntimeError('接收位置不符；停止操作，未重发图片或提交')
        await write(b'\x97' + struct.pack('<H', transfer))
        await idle()
        await write(b'\x9c\x03')
        result = await idle()
        if result['display_mode'] != 6:
            raise RuntimeError('图片日历未进入，停止：' + str(result))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('已收到图片日历刷新完成状态；请检查实体屏幕。图片只在RAM中，未写图库。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', required=True, help='Explicit test screen Bluetooth MAC/address')
    parser.add_argument('--firmware-id', required=True, help='Pinned ID from the delivered test manifest')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--photo', type=Path, help='Local JPEG/PNG; sends image and selects photo calendar')
    action.add_argument('--clock', action='store_true', help='Return to the existing clock')
    asyncio.run(main(parser.parse_args()))
