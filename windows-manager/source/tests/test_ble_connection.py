"""Connection preparation never writes until FF01 is discovered."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/backend'), str(ROOT / 'source/tests')]
from gateway import Gateway, worker, DeliveryUnknown
from protocol import CONTROL, SERVICE, VOLTS
from store import Store


class Connections(unittest.IsolatedAsyncioTestCase):
    async def test_windows_connected_identity_can_be_read_without_a_new_advertisement(self):
        closed=[];connected=[]
        address='18:BC:5A:6B:8D:58'
        known=SimpleNamespace(bluetooth_address=int(address.replace(':',''),16),
            connection_status=1,name='ELINK-BWR-6B8D58',close=lambda:closed.append(True))
        async def cached(_):return known
        async def scan(*args,**kwargs):return None
        class Client:
            def __init__(self,device,**kwargs):
                connected.append(device.address);self.is_connected=False
                self.services=SimpleNamespace(get_characteristic=lambda _:True)
            async def connect(self):self.is_connected=True
            async def disconnect(self):self.is_connected=False
            async def write_gatt_char(self,*args,**kwargs):pass
            async def read_gatt_char(self,uuid,**kwargs):
                return (3000).to_bytes(2,'little') if uuid==VOLTS else bytes(11)
        native_sleep=asyncio.sleep
        async def quick_sleep(_):await native_sleep(0)
        module=SimpleNamespace(BluetoothLEDevice=SimpleNamespace(from_bluetooth_address_async=cached),
                               BluetoothConnectionStatus=SimpleNamespace(CONNECTED=1))
        for native_address,status,expected in ((known.bluetooth_address,1,True),(0x18bc5a6b8d59,1,False),(known.bluetooth_address,0,False)):
            with self.subTest(native_address=native_address,status=status), tempfile.TemporaryDirectory() as folder:
                known.bluetooth_address=native_address;known.connection_status=status
                closed.clear();connected.clear();store=Store(Path(folder)/'test.sqlite3')
                try:
                    ident=store.queue(address,'probe',{})
                    with patch.dict(sys.modules,{'winrt.windows.devices.bluetooth':module}), patch('gateway.sys.platform','win32'), patch('gateway.BleakScanner.find_device_by_address',scan), patch('gateway.BleakClient',Client), patch('gateway.asyncio.sleep',quick_sleep):
                        if expected:
                            state=await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0])
                            self.assertEqual(state['protocol'],0)
                        else:
                            with self.assertRaises(ConnectionError):await Gateway(store).execute(store.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0])
                    self.assertEqual(connected,[address] if expected else []);self.assertEqual(closed,[True])
                finally:store.db.close()

    async def test_incomplete_first_discovery_recovers_before_querying_actual_152(self):
        from test_firmware import Machine
        machine = Machine(ROOT / 'build/firmware-1.5.2')
        writes = []
        clients = []

        class Services:
            def __init__(self, client): self.client = client
            def get_characteristic(self, uuid):
                return SimpleNamespace(uuid=uuid) if self.client.connects > 1 else None
            def __iter__(self): return iter([SimpleNamespace(uuid=SERVICE)])

        class Client:
            def __init__(self, *args, **kwargs):
                self.connects = 0; self.disconnects = 0; self.is_connected = False
                self.services = Services(self); clients.append(self)
            async def connect(self): self.connects += 1; self.is_connected = True
            async def disconnect(self): self.disconnects += 1; self.is_connected = False
            async def write_gatt_char(self, uuid, data, response):
                assert self.connects > 1 and self.is_connected and response
                writes.append(bytes(data)); machine.cmd(bytes(data))
            async def read_gatt_char(self, uuid, **kwargs):
                return (3000).to_bytes(2, 'little') if uuid == VOLTS else machine.published

        native_sleep = asyncio.sleep
        async def quick_sleep(_): await native_sleep(0)
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'test.sqlite3')
            try:
                channel = Gateway(store); address = '18:BC:5A:6B:8D:58'
                store.device(address, 'test'); channel.devices[address] = SimpleNamespace(address=address)
                ident = store.queue(address, 'probe', {})
                with patch('gateway.BleakClient', Client), patch('gateway.asyncio.sleep', quick_sleep):
                    state = await channel.execute(store.rows('SELECT * FROM jobs WHERE id=?', (ident,))[0])
                self.assertEqual(state['firmware_id'], '3bbf1f31')
                self.assertEqual(clients[0].connects, 2)
                self.assertEqual(clients[0].disconnects, 2)
                self.assertIn(b'\x93', writes)
                self.assertTrue(all(p[0] in (0x93, 0x9d, 0xb4, 0xbb, 0x9a) for p in writes))
                self.assertFalse(machine.flash_events)
            finally: store.db.close()

    async def test_missing_control_stops_after_three_discoveries_with_uuid_evidence(self):
        client = SimpleNamespace(connects=0, disconnects=0, is_connected=False)
        class Services:
            def get_characteristic(self, uuid): return None
            def __iter__(self): return iter([SimpleNamespace(uuid='00001800-0000-1000-8000-00805f9b34fb')])
        client.services = Services()
        async def connect(): client.connects += 1; client.is_connected = True
        async def disconnect(): client.disconnects += 1; client.is_connected = False
        client.connect = connect; client.disconnect = disconnect
        native_sleep = asyncio.sleep
        async def quick_sleep(_): await native_sleep(0)
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'test.sqlite3')
            try:
                channel = Gateway(store); address = '18:BC:5A:6B:8D:58'
                channel.devices[address] = SimpleNamespace(address=address)
                ident = store.queue(address, 'probe', {})
                with patch('gateway.BleakClient', return_value=client), patch('gateway.asyncio.sleep', quick_sleep):
                    with self.assertRaisesRegex(ValueError, '3 次.*FF01.*00001800'):
                        await channel.execute(store.rows('SELECT * FROM jobs WHERE id=?', (ident,))[0])
                self.assertEqual(client.connects, 3)
                self.assertEqual(client.disconnects, 3)
            finally: store.db.close()

    async def test_manual_connection_failures_stop_but_scheduled_jobs_keep_their_window(self):
        for payload, expected in (({}, 'failed'), ({'scheduled': True}, 'waiting')):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                store = Store(Path(folder) / 'test.sqlite3'); stop = threading.Event()
                class Unavailable:
                    async def execute(self, job):
                        stop.set(); raise ConnectionError('设备未广播')
                try:
                    ident = store.queue('18:BC:5A:6B:8D:58', 'probe', payload)
                    for _ in range(3):
                        stop.clear(); store.execute('UPDATE jobs SET due=0 WHERE id=?', (ident,))
                        await worker(store, Unavailable(), stop)
                    job = store.rows('SELECT * FROM jobs WHERE id=?', (ident,))[0]
                    self.assertEqual(job['status'], expected)
                    self.assertEqual(job['attempts'], 3)
                finally: store.db.close()

    async def test_committed_unknown_is_never_requeued(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'test.sqlite3'); stop = threading.Event()
            class Submitted:
                async def execute(self, job):
                    stop.set(); raise DeliveryUnknown('提交后失联')
            try:
                ident = store.queue('18:BC:5A:6B:8D:58', 'probe', {})
                await worker(store, Submitted(), stop)
                job = store.rows('SELECT * FROM jobs WHERE id=?', (ident,))[0]
                self.assertEqual(job['status'], 'delivery_unknown')
                self.assertEqual(job['attempts'], 0)
            finally: store.db.close()


if __name__ == '__main__': unittest.main()
