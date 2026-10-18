"""Native gallery parity and manager-to-compiled-photo-calendar integration."""
import asyncio,base64,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/backend'),str(ROOT/'source/tests')]
from builtin_gallery import gallery,native,resource
from render import render,photo_calendar_frame,frame_png
from store import Store,snapshot
from protocol import image_packets,decode_status
from gateway import Gateway,DeliveryUnknown

class NativeGallery(unittest.TestCase):
    def test_shared_sixteen_frames_and_crop_preserve_native_pixels(self):
        self.assertEqual(len(gallery()),16)
        for item in gallery():
            frame=native(item['path'])
            self.assertEqual(frame['frame'],(ROOT/'source/web'/item['frame']).read_bytes())
            self.assertEqual(frame['sha256'],hashlib.sha256(frame['frame']).hexdigest())
            self.assertEqual(render({'kind':'image','builtin':item['path']}),frame)
            cropped=photo_calendar_frame(frame['frame'])['frame']
            for off in (0,4000):
                for x in range(174):
                    self.assertEqual(cropped[off+(249-x)*16:off+(250-x)*16],frame['frame'][off+(207-x)*16:off+(208-x)*16])
            self.assertEqual(cropped[:1216],b'\xff'*1216)
            self.assertEqual(cropped[4000:5216],bytes(1216))
        for path in ('../config.json','image/../../backend/server.py','config.json','image/missing.png'):
            self.assertIsNone(resource(path))
            with self.assertRaises(ValueError):native(path)
        for amount,count in ((17,471),(128,63)):
            packets=list(image_packets(bytes(8000),1,amount))
            self.assertEqual(len(packets)-2,count)
            self.assertEqual(b''.join(p[3:] for p in packets[1:-1]),bytes(8000))

class PhotoTransport(unittest.IsolatedAsyncioTestCase):
    async def test_new_theme_real_thumb_large_mtu_and_old_firmware_rejection(self):
        from test_photo_calendar import PhotoMachine
        from test_firmware import BASE
        import gateway
        machine=PhotoMachine();packets=[]
        self.assertEqual(machine.meta['firmware_id'],'ff001ff1','Run against build/firmware-1.5.11')
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'elink.sqlite3');address='18:BC:5A:6B:8A:B1';store.register(address)
            item=gallery()[0];ident=store.save_template(item['title'],{'kind':'image','builtin':item['path']},native(item['path']))
            content=snapshot(store.template(ident),photo=True)
            class Scanner:
                @staticmethod
                async def find_device_by_address(*a,**kw):return object()
            class Client:
                mtu_size=247
                is_connected=True
                old=False
                legacy_photo=False
                drop_theme=False
                def __init__(self,*a,**kw):self.services=type('Services',(),{'get_characteristic':lambda _,uuid:True})()
                async def connect(self):pass
                async def disconnect(self):pass
                async def write_gatt_char(self,char,data,response):
                    packets.append(bytes(data));machine.cmd(data)
                    if machine.uc.mem_read(BASE+0x11980+8,1)[0]:machine.finish()
                    if self.drop_theme and data==b'\x9c\x03':raise ConnectionError('lost theme acknowledgement')
                async def read_gatt_char(self,char,**kw):
                    if char.endswith('ff02-0000-1000-8000-00805f9b34fb'):return b'\xb8\x0b'
                    raw=machine.published
                    if raw[:4]==b'ELUI' and (self.old or self.legacy_photo):return raw[:6]+bytes([raw[6]&3])+raw[7:]
                    if raw[:4]==b'ELK1' and (self.old or self.legacy_photo):return raw[:28]+bytes.fromhex('3bbf1f31' if self.old else 'd78aa415')
                    return raw
            real_sleep=asyncio.sleep
            async def quick_sleep(delay):await real_sleep(0)
            try:
                with patch.object(gateway,'BleakScanner',Scanner),patch.object(gateway,'BleakClient',Client),patch.object(gateway.asyncio,'sleep',quick_sleep):
                    job=store.queue(address,'photo_calendar',content)
                    receipt=await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(job,))[0])
                self.assertEqual(receipt['pixel_payload_bytes'],128)
                self.assertTrue(receipt['direct_photo_commit'])
                self.assertEqual(receipt['generation_after']-receipt['generation_before'],1)
                self.assertFalse(any(p[0]==0x97 for p in packets))
                for key in ('transfer_seconds','refresh_seconds','readback_seconds','total_seconds'):self.assertGreaterEqual(receipt[key],0)
                self.assertEqual(sum(p[0]==0x96 for p in packets),63)
                self.assertIn(b'\x9c\x03',packets)
                self.assertEqual(machine.status()['display_mode'],6)
                actual=bytes(machine.uc.mem_read(BASE+0xdedc,4000))+bytes(machine.uc.mem_read(BASE+0xf15c,4000))
                updated=json.loads(store.rows('SELECT payload FROM jobs WHERE id=?',(job,))[0]['payload'])
                self.assertEqual(base64.b64decode(updated['display_png']),frame_png(actual))
                self.assertEqual(receipt['display_sha256'],hashlib.sha256(actual).hexdigest())
                self.assertEqual(machine.flash_events,[],'Image theme must never write persistent storage')
                old=bytearray(32);old[:5]=b'ELK1\x01';old[28:]=bytes.fromhex('3bbf1f31')
                self.assertFalse(decode_status(old)['photo_calendar'])
                self.assertEqual(decode_status(old)['max_image_payload'],17)
                with patch.object(gateway,'BleakScanner',Scanner),patch.object(gateway,'BleakClient',Client),patch.object(gateway.asyncio,'sleep',quick_sleep):
                    before=sum(p[0]==0x95 for p in packets);Client.old=True
                    refused=store.queue(address,'photo_calendar',content)
                    with self.assertRaisesRegex(ValueError,'1.5.4'):await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(refused,))[0])
                    self.assertEqual(sum(p[0]==0x95 for p in packets),before,'Old firmware must reject before pixel transfer')
                    Client.old=False;Client.legacy_photo=True;start=len(packets)
                    compatible=store.queue(address,'photo_calendar',content)
                    fallback=await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(compatible,))[0])
                    self.assertFalse(fallback['direct_photo_commit'])
                    self.assertEqual(fallback['generation_after']-fallback['generation_before'],2)
                    commits=[p[0] for p in packets[start:] if p[0] in (0x97,0x9c)]
                    self.assertEqual(commits,[0x97,0x9c],'Advertised 1.5.4 capabilities retain the two-commit path')
                    Client.legacy_photo=False;Client.drop_theme=True
                    commits_before=sum(p==b'\x9c\x03' for p in packets)
                    uncertain=store.queue(address,'photo_calendar',content)
                    with self.assertRaises(DeliveryUnknown):await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(uncertain,))[0])
                    self.assertEqual(sum(p==b'\x9c\x03' for p in packets),commits_before+1,'Lost commit acknowledgement must not replay the theme')
            finally:store.db.close()

if __name__=='__main__':unittest.main()
