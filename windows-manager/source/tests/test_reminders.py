"""Real Store lifecycle and Gateway packets executed by compiled Thumb firmware."""
import asyncio,base64,json,struct,tempfile,time,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from test_backend import ROOT
from store import Store
from gateway import Gateway
from protocol import decode_ui_capabilities,decode_reminder_slot
from test_product_ui import ProductMachine

class Reminders(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_offline_flash_readback_and_cancel_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.sqlite3';store=Store(path);address='18:BC:5A:6B:91:A7';store.register(address)
            due=int(time.time()//60*60+3600);ident=store.save_reminder([address],'任务提醒','独立执行',due)[0]
            store.dispatch_reminders();store.dispatch_reminders();self.assertEqual(len(store.rows('SELECT * FROM jobs')),1)
            job=store.rows('SELECT * FROM jobs')[0];payload=json.loads(job['payload']);m=ProductMachine()
            current=datetime.fromtimestamp(due-120)
            m.draw(year=current.year,month=current.month,day=current.day,h=current.hour,minute=current.minute,force=128);m.finish()
            channel=Gateway(store)
            class Client:
                is_connected=True
                async def write_gatt_char(_,char,data,response):m.cmd(data)
                async def read_gatt_char(_,char,use_cached):
                    if m.uc.mem_read(0x07fd1988,1)[0]:m.finish() # External panel BUSY hardware completes asynchronously.
                    return m.published
            client=Client();m.cmd(b'\x9d');client._elink_caps=decode_ui_capabilities(m.published)
            import gateway
            real_sleep=asyncio.sleep
            async def immediate(_):await real_sleep(0)
            with patch.object(gateway.asyncio,'sleep',immediate):
                receipt=await channel.install_reminder(client,job,payload,await channel.status(client))
                self.assertEqual(receipt['result'],'reminder_flash_verified');self.assertEqual(receipt['bytes'],8000)
                store.reminder_result(job,receipt);self.assertEqual(store.reminders()[0]['status'],'armed')
                # Backend disappears; only the actual peripheral minute path executes.
                store.db.close();target=datetime.fromtimestamp(due)
                frame=m.draw(year=target.year,month=target.month,day=target.day,h=target.hour,minute=target.minute);m.finish()
                m.cmd(bytes([0xb4,receipt['slot']]));self.assertEqual(decode_reminder_slot(m.published)['state'],252)
                store=Store(path);self.assertEqual(len(store.rows('SELECT * FROM jobs')),1)
                channel=Gateway(store);slots=await channel.reminder_slots(client);store.reconcile_reminders(address,slots)
                state=await channel.status(client);await channel.reminder_preview(client,address,state,slots)
                self.assertEqual(store.reminders()[0]['status'],'displayed')
                frozen=json.loads(store.rows('SELECT payload FROM jobs WHERE id=?',(job['id'],))[0]['payload'])
                self.assertEqual(base64.b64decode(frozen['frame']),frame,'Thumbnail must reflect live battery pixels, not the preinstalled frame')
                store.execute('UPDATE devices SET settings=? WHERE address=?',('{"clock_timezone":"Europe/Amsterdam"}',address))
                m.cold_boot();m.cmd(b'\x9d');client._elink_caps=decode_ui_capabilities(m.published)
                restored=await channel.install_reminder(client,job,payload,await channel.status(client))
                self.assertEqual((await channel.status(client))['clock_timezone'],'Europe/Amsterdam','Cold power loss must restore saved timezone before enabling offline alarms')
                store.change_reminder(ident,delete=True);self.assertEqual(len(store.reminders()),1,'Do not delete an armed schedule before device acknowledgement')
                cancel=store.rows("SELECT * FROM jobs WHERE id=(SELECT job_id FROM reminders WHERE id=?)",(ident,))[0]
                done=await channel.install_reminder(client,cancel,json.loads(cancel['payload']),await channel.status(client));store.reminder_result(cancel,done)
                self.assertEqual(store.reminders(),[]);m.cmd(bytes([0xb4,receipt['slot']]));self.assertEqual(decode_reminder_slot(m.published)['state'],248)
            store.db.close()

    async def test_edit_same_id_atomic_replacement_validation_limit_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'data.sqlite3');a='18:BC:5A:6B:91:A7';store.register(a);due=int(time.time()+3600)
            id=store.save_reminder([a],'A','',due)[0];original=store.reminders()[0]['token']
            store.save_reminder([a],'B','',due+60,id);self.assertEqual(store.reminders()[0]['previous_token'],0)
            store.dispatch_reminders();job=store.rows('SELECT * FROM jobs')[0];store.reminder_result(job,{'slot_state':254})
            armed=store.reminders()[0]['token'];store.state(a,{'offline_reminders':True,'time_initialized':False});self.assertEqual(store.reminders()[0]['status'],'needs_sync');store.reconcile_reminders(a,[{'token':armed,'state':254,'clock_ready':False}]);self.assertEqual(store.reminders()[0]['status'],'needs_sync');store.reconcile_reminders(a,[{'token':armed,'state':254,'clock_ready':True}]);self.assertEqual(store.reminders()[0]['status'],'armed');store.save_reminder([a],'C','',due+120,id);store.save_reminder([a],'D','',due+180,id)
            self.assertEqual(store.reminders()[0]['previous_token'],armed,'Repeated draft edits must retain the real installed token')
            self.assertEqual(len(store.reminders()),1,'Edit updates the original schedule ID')
            store.dispatch_reminders();job=store.rows('SELECT * FROM jobs ORDER BY created DESC LIMIT 1')[0]
            store.update_job(job['id'],status='failed');store.retry_reminder(id);self.assertEqual(store.rows('SELECT status FROM jobs WHERE id=?',(job['id'],))[0]['status'],'queued')
            with self.assertRaises(ValueError):store.save_reminder([a],'E','',due,id)
            with self.assertRaises(ValueError):store.unregister(a)
            for n in range(6):store.save_reminder([a],str(n),'',due+600)
            with self.assertRaisesRegex(ValueError,'7'):store.save_reminder([a],'full','',due)
            for bad in (float('nan'),float('inf'),True,time.time()-1):
                with self.assertRaises(ValueError):store.save_reminder([a],'bad','',bad)
            store.db.close()
if __name__=='__main__':unittest.main()
