"""Manager snapshots and full GATT exchange use the compiled album firmware."""
import asyncio,base64,json,tempfile,unittest,contextlib
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from test_offline_album import AlbumMachine
from test_firmware import BASE
from builtin_gallery import gallery,native
from store import Store,album_snapshot
from server import App
from protocol import decode_album
from gateway import Gateway,DeliveryUnknown

class AlbumTransport(unittest.IsolatedAsyncioTestCase):
    async def test_windows_cancel_is_transport_failure_and_old_album_is_not_written(self):
        class Client:
            is_connected=True
            async def write_gatt_char(self,*args,**kwargs):raise OSError(None,'操作已被用户取消',None,-2147023673)
        with self.assertRaisesRegex(ConnectionError,'Windows.*0x800704C7.*BD02'):
            await Gateway(None).write(Client(),b'\xbd\x02')
        class ReadClient(Client):
            async def write_gatt_char(self,*args,**kwargs):pass
            async def read_gatt_char(self,*args,**kwargs):raise OSError(None,'操作已被用户取消',None,-2147023673)
        with self.assertRaisesRegex(ConnectionError,'Windows.*0x800704C7.*93'):
            await Gateway(None).query(ReadClient(),b'\x93',lambda value:value)
        class OldGateway(Gateway):
            async def wait_idle(self,*args):return {'busy':False}
            async def query_album(self,*args):return {'protocol_version':1}
        payload={'items':[{'frame':base64.b64encode(bytes(8000)).decode()}]}
        with self.assertRaisesRegex(ValueError,'1.5.8'):
            await OldGateway(None).install_album(Client(),{},payload,{'offline_album':True,'busy':False,'error':5})

    async def test_queue_snapshot_upload_readback_offline_rotation_and_stop(self):
        import gateway
        machine=AlbumMachine();packets=[]
        class Scanner:
            @staticmethod
            async def find_device_by_address(*a,**kw):return object()
        class Client:
            mtu_size=247;is_connected=True;drop_commit=False;drop_step=False;drop_before_commit=False
            def __init__(self,*a,**kw):self.services=SimpleNamespace(get_characteristic=lambda uuid:True)
            async def connect(self):pass
            async def disconnect(self):pass
            async def write_gatt_char(self,char,data,response):
                if self.drop_before_commit and data[:2]==b'\xbd\x03':
                    packets.append(bytes(data));raise ConnectionError('commit never reached device')
                packets.append(bytes(data));machine.cmd(data)
                if machine.uc.mem_read(BASE+0x11980+8,1)[0]:machine.finish()
                if self.drop_commit and data[:2]==b'\xbd\x03':raise ConnectionError('lost commit reply')
                if self.drop_step and data[:2]==b'\xbd\x02':raise OSError(None,'操作已被用户取消',None,-2147023673)
            async def read_gatt_char(self,char,**kw):return b'\xb8\x0b' if 'ff02-' in char else machine.published
        real_sleep=asyncio.sleep
        async def fast(delay):await real_sleep(0)
        with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as cleanup:
            store=Store(Path(tmp)/'db');address='18:BC:5A:6B:8A:B1';store.register(address)
            cleanup.callback(store.db.close)
            ids=[store.save_template(i['title'],{'kind':'image','builtin':i['path']},native(i['path'])) for i in gallery()[:2]]
            value={'items':[{'template_id':i,'photo_x':x} for i,x in zip(ids,(0,84))],'mode':'calendar','interval_minutes':120}
            app=App.__new__(App);app.store=store;app.thread=SimpleNamespace(is_alive=lambda:True);app.scanning=False
            ident=app.enqueue(address,'album',value);job=store.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0];saved=json.loads(job['payload'])
            self.assertEqual(len(base64.b64decode(saved['items'][0]['frame'])),8000)
            with patch.object(gateway,'BleakScanner',Scanner),patch.object(gateway,'BleakClient',Client),patch.object(gateway.asyncio,'sleep',fast):
                receipt=await Gateway(store).execute(job)
                self.assertEqual(receipt['album']['count'],2);self.assertEqual(receipt['album']['photo_x'],[0,84]);self.assertTrue(receipt['offline'])
                self.assertEqual(sum(p[0]==0x96 for p in packets),126)
                self.assertEqual(sum(p[:2]==b'\xbd\x02' for p in packets),64)
                self.assertFalse(any(p[0]==0x97 for p in packets));self.assertEqual(machine.status()['display_mode'],8)
                store.update_job(ident,status='succeeded',receipt=receipt)
                self.assertIsNotNone(store.display_preview(address,machine.status()))
                for mode in ('image','calendar'):
                    before=len(packets);switched=store.queue(address,'album',{**saved,'mode':mode})
                    shared=await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(switched,))[0])
                    self.assertTrue(shared['reused_gallery']);self.assertEqual(shared['transmitted_image_bytes'],0)
                    self.assertEqual(sum(p[:2]==b'\xbd\x03' for p in packets[before:]),1)
                    self.assertFalse(any(p[0] in (0x95,0x96) or p[:2] in (b'\xbd\x01',b'\xbd\x02') for p in packets[before:]))
                    store.update_job(switched,status='succeeded',receipt=shared)
                probe=store.queue(address,'probe',{});state=await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(probe,))[0])
                self.assertTrue(state['pixel_readback_verified'])
                store.update_job(probe,status='succeeded',receipt=state)
                self.assertEqual(store.display_preview(address,machine.status())['label'],'设备像素读回')
                self.assertEqual(store.display_preview(address,machine.status())['url'],'/api/jobs/'+probe+'/preview.png')
                # Explicit calibration keeps the stored calendar album playing.
                calibrate=store.queue(address,'sync',{'quiet':True})
                await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(calibrate,))[0])
                self.assertEqual(machine.status()['display_mode'],8)
                self.assertTrue(decode_album(machine.album())['running'])
                # Upload snapshots are independent of later template edits or deletion.
                store.execute('DELETE FROM templates WHERE id=?',(ids[0],))
                self.assertEqual(json.loads(store.rows('SELECT payload FROM jobs WHERE id=?',(ident,))[0]['payload'])['items'],saved['items'])
                stop=store.queue(address,'album_stop',{});result=await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(stop,))[0])
                self.assertFalse(result['album']['enabled']);self.assertFalse(result['album']['running'])
                changed=store.queue(address,'album',{**saved,'items':list(reversed(saved['items']))})
                changed_job=store.rows('SELECT * FROM jobs WHERE id=?',(changed,))[0]
                Client.drop_step=True;before=len(packets)
                with self.assertRaisesRegex(ValueError,'1/32.*未提交.*Windows'):await Gateway(store).execute(changed_job)
                self.assertFalse(any(p[:2]==b'\xbd\x03' for p in packets[before:]))
                Client.drop_step=False
                Client.drop_commit=True
                before=sum(p[:2]==b'\xbd\x03' for p in packets)
                recovered=await Gateway(store).execute(changed_job)
                self.assertTrue(recovered['recovered_after_disconnect']);self.assertEqual(recovered['result'],'album_flash_verified')
                self.assertEqual(sum(p[:2]==b'\xbd\x03' for p in packets)-before,1,'Recovery must only read; never resend a commit')
                Client.drop_commit=False;Client.drop_before_commit=True
                before=sum(p[:2]==b'\xbd\x03' for p in packets)
                with self.assertRaisesRegex(DeliveryUnknown,'配置读回不一致'):await Gateway(store).execute(changed_job)
                self.assertEqual(sum(p[:2]==b'\xbd\x03' for p in packets)-before,1)
            self.assertTrue(all(0x40000<=a and a+n<=0x52000 for _,a,n in machine.flash_events))
            store.db.close()

    async def test_input_boundaries_and_crc_decoder(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db')
            for value in ({},{'items':[],'mode':'image','interval_minutes':60},{'items':[{}]*5,'mode':'image','interval_minutes':60},{'items':[{'template_id':'missing','photo_x':42}],'mode':'image','interval_minutes':True},{'items':[{'template_id':'missing','photo_x':85}],'mode':'image','interval_minutes':60}):
                with self.assertRaises(ValueError):album_snapshot(store,value)
            store.db.close()
        m=AlbumMachine();self.assertFalse(decode_album(m.album())['has_config'])
        with self.assertRaises(ValueError):decode_album(bytes(52))

if __name__=='__main__':unittest.main()
