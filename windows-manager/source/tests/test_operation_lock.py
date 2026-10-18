"""Exercise real admission/SQLite locking without running the BLE worker."""
import concurrent.futures
import sys
import tempfile
import threading
import unittest
import asyncio
import json
import struct
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from server import App
from store import Store
from gateway import Gateway,DeliveryUnknown


class OperationLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App.__new__(App)
        self.app.store = Store(Path(self.tmp.name) / 'test.sqlite3')
        self.app.thread = SimpleNamespace(is_alive=lambda: True)
        self.app.scanning = False
        self.app.addresses = ['18:BC:5A:6B:91:A7', '18:BC:5A:6B:86:66']
        for address in self.app.addresses:
            self.app.store.device(address, 'test')

    def tearDown(self):
        self.app.store.db.close()
        self.tmp.cleanup()

    def test_all_unfinished_states_block_other_device_and_scan(self):
        ident = self.app.store.queue(self.app.addresses[0], 'probe', {})
        for status in ('queued', 'waiting', 'running', 'awaiting_display'):
            self.app.store.update_job(ident, status=status, progress=100)
            self.assertTrue(self.app.operation_state()['busy'])
            with self.assertRaisesRegex(ValueError, '尚未完成'):
                self.app.enqueue(self.app.addresses[1], 'probe', {})
            with self.assertRaisesRegex(ValueError, '尚未完成'):
                self.app.scan()
        for status in ('succeeded', 'failed', 'delivery_unknown', 'cancelled'):
            self.app.store.update_job(ident, status=status)
            self.assertFalse(self.app.operation_state()['busy'])
        self.app.enqueue(self.app.addresses[1], 'probe', {})

    def test_concurrent_admission_only_accepts_one_request(self):
        barrier = threading.Barrier(2)
        def submit(address):
            barrier.wait()
            try:
                return self.app.enqueue(address, 'probe', {})
            except ValueError:
                return None
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(submit, self.app.addresses))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.app.operation_state()['jobs'], 1)

    def test_batch_is_one_admission_and_waiting_jobs_can_be_cancelled(self):
        results = self.app.enqueue_batch(self.app.addresses, 'probe', {})
        self.assertEqual(len(results), 2)
        self.assertTrue(all('id' in row for row in results))
        with self.assertRaisesRegex(ValueError, '尚未完成'):
            self.app.enqueue_batch(self.app.addresses, 'probe', {})
        for row in results:
            self.assertTrue(self.app.store.cancel(row['id']))
        self.assertFalse(self.app.operation_state()['busy'])
        self.app.scanning = True
        with self.assertRaisesRegex(ValueError, '尚未完成'):
            self.app.enqueue(self.app.addresses[0], 'probe', {})

    def test_pending_reminder_reserves_channel_before_dispatch(self):
        import time
        ids = self.app.device_change(self.app.store.save_reminder, [self.app.addresses[0]],
                                     'test', '', int(time.time()) + 3600)
        self.assertEqual(self.app.operation_state()['pending_reminders'], 1)
        with self.assertRaisesRegex(ValueError, '尚未完成'):
            self.app.enqueue(self.app.addresses[1], 'probe', {})
        self.app.cancel_pending_reminder(ids[0])
        self.assertFalse(self.app.operation_state()['busy'])
        ids = self.app.device_change(self.app.store.save_reminder, [self.app.addresses[0]],
                                     'existing', '', int(time.time()) + 3600)
        self.app.store.execute('UPDATE reminders SET previous_token=1 WHERE id=?',(ids[0],))
        with self.assertRaisesRegex(ValueError,'尚未派发'):
            self.app.cancel_pending_reminder(ids[0])

    def test_state_includes_running_job_even_behind_100_queued_jobs(self):
        import urllib.request
        from http.server import ThreadingHTTPServer
        from server import handler
        self.app.worker_error=None
        first=self.app.store.queue(self.app.addresses[0],'probe',{})
        self.app.store.update_job(first,status='running')
        for i in range(100):self.app.store.queue(f'18:BC:5A:00:00:{i:02X}','probe',{})
        http=ThreadingHTTPServer(('127.0.0.1',0),None);self.app.port=http.server_port
        http.RequestHandlerClass=handler(self.app)
        thread=threading.Thread(target=http.serve_forever);thread.start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/state',timeout=3) as response:
                state=json.load(response)
            self.assertEqual(len(state['jobs']),101)
            self.assertIn(first,{j['id'] for j in state['jobs']})
        finally:http.shutdown();thread.join();http.server_close()


class RefreshCompletion(unittest.IsolatedAsyncioTestCase):
    async def test_busy_readback_keeps_job_unfinished_and_device_error_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.sqlite3');channel=Gateway(store)
            ident=store.queue('18:BC:5A:6B:91:A7','sync',{})
            store.update_job(ident,status='running')
            job={'id':ident}
            class Client:
                is_connected=True
                reads=0
                error=0
                async def write_gatt_char(self,*args,**kwargs):pass
                async def read_gatt_char(self,*args,**kwargs):
                    self.reads+=1
                    data=bytearray(32);data[:5]=b'ELK1\x01';data[8]=int(self.reads<3);data[9]=self.error
                    return data
            client=Client();sleep=asyncio.sleep
            async def quick_sleep(_):await sleep(0)
            try:
                with patch('gateway.asyncio.sleep',quick_sleep):
                    result=await channel.wait_idle(client,job,{'busy':True})
                    self.assertFalse(result['busy']);self.assertEqual(client.reads,3)
                    row=store.rows('SELECT status,progress FROM jobs WHERE id=?',(ident,))[0]
                    self.assertEqual(row['status'],'running');self.assertEqual(row['progress'],95)
                    client.error=4
                    with self.assertRaises(DeliveryUnknown):await channel.wait_idle(client,job,{'busy':True})
                    with self.assertRaises(DeliveryUnknown):await channel.wait_idle(client,job,{'busy':False,'error':4})
            finally:store.db.close()


if __name__ == '__main__':
    unittest.main()
