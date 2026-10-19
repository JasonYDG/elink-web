"""Probe real compiled firmware; do not substitute a page illustration for pixels."""
import asyncio,base64,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_offline_album import AlbumMachine
from test_firmware import BASE
from gateway import Gateway
from protocol import VOLTS
from store import Store
from render import frame_png

class StatusConsistency(unittest.TestCase):
    def test_boot_reports_default_and_album_resumes_without_a_query(self):
        m=AlbumMachine();frame=bytes([37])*8000;m.stage([frame]);m.play()
        m.cold_boot();m.run(BASE+0x2224);m.finish()
        self.assertEqual(m.status()['display_mode'],4)
        events=list(m.flash_events)
        m.minute();m.finish()
        self.assertEqual(m.status()['display_mode'],7)
        self.assertEqual(m.frame(),frame)
        self.assertEqual(m.flash_events,events)

    def test_unverified_preview_never_uses_an_illustration_or_stale_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Store(Path(folder)/'test.sqlite3');address='18:BC:5A:6B:8A:B1'
            try:
                for mode in (0,3,4,5,6,7,8):
                    self.assertIsNone(s.display_preview(address,{'display_mode':mode}))
                state={'display_mode':7,'display_generation':2,'transfer_id':0,'firmware_id':'test'}
                ident=s.queue(address,'probe',{'display_png':base64.b64encode(frame_png(bytes(8000))).decode()})
                s.update_job(ident,status='succeeded',receipt={**state,'generation_after':2,'pixel_readback_verified':True})
                self.assertIsNotNone(s.display_preview(address,state))
                self.assertIsNone(s.display_preview(address,{**state,'preview_error':'read failed'}))
                self.assertIsNone(s.display_preview(address,{**state,'busy':True}))
            finally:s.db.close()

class ProbeTransport(unittest.IsolatedAsyncioTestCase):
    async def check_probe(self,interrupt=False):
        m=AlbumMachine();frame=bytes([37])*8000;m.stage([frame]);m.play()
        m.cold_boot();m.run(BASE+0x2224);m.finish();events=list(m.flash_events)
        commands=[];changed=False
        class Client:
            def __init__(self,*args,**kwargs):self.is_connected=False;self.services=SimpleNamespace(get_characteristic=lambda _:True)
            async def connect(self):self.is_connected=True
            async def disconnect(self):self.is_connected=False
            async def write_gatt_char(self,uuid,data,response):
                nonlocal changed
                commands.append(bytes(data))
                if data[0]==0x9a and not changed:
                    changed=True
                    if interrupt:raise ConnectionError('Windows read interrupted')
                    m.minute();m.finish()
                m.cmd(bytes(data))
            async def read_gatt_char(self,uuid,**kwargs):return (3000).to_bytes(2,'little') if uuid==VOLTS else m.published
        native_sleep=asyncio.sleep
        async def quick(_):await native_sleep(0)
        with tempfile.TemporaryDirectory() as folder:
            s=Store(Path(folder)/'test.sqlite3');address='18:BC:5A:6B:8A:B1'
            try:
                s.device(address,'test');g=Gateway(s);g.devices[address]=SimpleNamespace(address=address)
                ident=s.queue(address,'probe',{});job=s.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0]
                with patch('gateway.BleakClient',Client),patch('gateway.asyncio.sleep',quick):
                    if interrupt:
                        with self.assertRaises(ConnectionError):await g.execute(job)
                        state=json.loads(s.rows('SELECT state FROM devices WHERE address=?',(address,))[0]['state'])
                        self.assertIsNone(s.display_preview(address,state))
                        # A fresh connection may repeat reads, never a submitted command.
                        m.minute();m.finish()
                    receipt=await g.execute(job)
                self.assertTrue(receipt['pixel_readback_verified'])
                self.assertEqual(receipt['display_mode'],7)
                payload=json.loads(s.rows('SELECT payload FROM jobs WHERE id=?',(ident,))[0]['payload'])
                self.assertEqual(base64.b64decode(payload['display_png']),frame_png(frame))
                self.assertTrue(all(p[0] in (0x93,0x9d,0x9a,0xb4,0xbb) or p[:2] in (b'\xbd\0',b'\xbd\5') for p in commands))
                self.assertEqual(m.flash_events,events)
            finally:s.db.close()

    async def test_page_change_during_probe_retries_with_current_state(self):await self.check_probe()
    async def test_read_disconnect_is_retryable_not_a_successful_clock(self):await self.check_probe(True)

if __name__=='__main__':unittest.main()
