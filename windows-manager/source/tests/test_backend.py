import sys,unittest,tempfile,json,struct,asyncio,threading,base64
from pathlib import Path
from unittest.mock import patch
from datetime import date,datetime
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/backend'),str(ROOT/'source/tests')]
from store import Store,snapshot
from protocol import decode_status,decode_ui_capabilities,decode_battery,sync_packet,VOLTS
from render import render,quantize,notice_battery
from lunar import lunar_fields
from gateway import Gateway,DeliveryUnknown
from PIL import Image
from test_firmware import Machine,STATE,firmware_file,BOOTSTRAP_DIR
from test_ota import OtaMachine

class Data(unittest.TestCase):
    def test_measured_battery_and_frozen_notice_pixels(self):
        import io
        for adc,percent in ((1136,0),(1360,4),(1584,28),(1650,67),(1705,100),(1850,100)):
            mv=adc*225>>7
            self.assertEqual(decode_battery(mv.to_bytes(2,'little'))['battery_percent'],percent)
        for raw in (b'',b'\0\0',b'\xff\xff',b'\x01',bytes(32)):
            with self.assertRaises(ValueError):decode_battery(raw)
        spec={'kind':'notice','title':'今日安排','body':'欢迎使用','footer':'2026-10-06 星期二'}
        unknown=render(spec);measured=notice_battery(unknown['png'],67)
        self.assertEqual(measured['frame'],render(spec,67)['frame'])
        a=Image.open(io.BytesIO(unknown['png']));b=Image.open(io.BytesIO(measured['png']))
        for y in range(122):
            for x in range(250):
                if not (176<=x<=249 and 8<=y<=22):self.assertEqual(a.getpixel((x,y)),b.getpixel((x,y)))
        self.assertEqual(notice_battery(measured['png'],None)['frame'],unknown['frame'],'Missing voltage must restore unknown, not retain a stale percentage')
    def test_licensed_glyphs_render_at_exact_size_without_scaling(self):
        from PIL import ImageFont,ImageDraw
        from bitmap_fonts import cells,text_mask,noto_path,INK,BASELINE,fallback_cells
        for height,style in ((12,'noto'),(14,'noto_medium'),(15,'noto'),(18,'noto_medium'),(24,'noto'),(40,'noto'),(44,'noto')):
            font=ImageFont.truetype(noto_path(style),height)
            for ch in '农历闰荷兰寒露8今日天后ABCDEF':
                canvas=Image.new('L',(3*height,height),0)
                ImageDraw.Draw(canvas).text((height,round(height*BASELINE)),ch,font=font,fill=255,anchor='ls')
                reference=canvas.point(lambda v:255 if v>=INK else 0).convert('1');reference=reference.crop(reference.getbbox())
                if height==12 and ord(ch)>127 and ch not in '今日天后':reference=fallback_cells(ch,12)[ch];reference=reference.crop(reference.getbbox())
                actual=cells(ch,height)[ch]
                self.assertEqual(actual.height,height,'Cells keep the requested pixel size; no 12/16px upscale')
                self.assertEqual(actual.crop(actual.getbbox()).tobytes(),reference.tobytes(),'Use exact licensed '+style+' outlines')
        self.assertEqual(text_mask('0123456789',16).tobytes(),text_mask('0123456789',16,bold_digits=True).tobytes(),'A bold face must not receive another offset stroke')

    def test_small_year_countdown_and_mac_have_native_bold_strokes(self):
        from PIL import ImageFont,ImageDraw
        from bitmap_fonts import text_mask,noto_path,fallback_cells,INK,BASELINE
        old=ImageFont.truetype(noto_path('noto_medium'),12)
        def previous(value):
            count=0
            for ch in value:
                if ord(ch)>127:mask=fallback_cells(ch,12)[ch]
                else:
                    mask=Image.new('L',(36,12),0)
                    ImageDraw.Draw(mask).text((12,round(12*BASELINE)),ch,font=old,fill=255,anchor='ls')
                    mask=mask.point(lambda v:255 if v>=INK else 0).convert('1')
                count+=sum(bool(v) for v in mask.get_flattened_data())
            return count
        for value in ('2026/10','5天后','16天后','今日','18:BC:5A:6B:8A:B1'):
            mask=text_mask(value,12)
            self.assertEqual(mask.height,12)
            self.assertGreater(sum(bool(v) for v in mask.get_flattened_data()),previous(value)*1.35,value)
        self.assertLessEqual(text_mask('2026/10',12).width,76)
        for n in range(17):self.assertLessEqual(36+text_mask(str(n)+'天后',12).width,76)
        for ch in '0123456789ABCDEF':self.assertLess(20+text_mask(':'.join([ch*2]*6),12).width,194)
        full=Image.new('L',(36,36),0)
        ImageDraw.Draw(full).text((12,12+round(12*BASELINE)),'/',font=ImageFont.truetype(noto_path('noto'),12),fill=255,anchor='ls')
        full=full.point(lambda v:255 if v>=INK else 0).convert('1')
        slash=text_mask('/',12)
        self.assertEqual(slash.crop(slash.getbbox()).tobytes(),full.crop(full.getbbox()).tobytes(),'Keep the entire native Black slash, including its lower tip')

    def test_netherlands_wall_time_dst_and_native_font_frames(self):
        from datetime import timezone
        from clock_time import wall_time,timezone_packet,settings
        for iso,hour,summer in (('2026-03-29T00:55:00+00:00',1,False),('2026-03-29T01:05:00+00:00',3,True),('2026-10-25T00:55:00+00:00',2,True),('2026-10-25T01:05:00+00:00',2,False)):
            utc=datetime.fromisoformat(iso);t=wall_time('Europe/Amsterdam',utc)
            self.assertEqual(t.hour,hour);self.assertEqual(bool(t.dst()),summer)
            self.assertEqual(timezone_packet('Europe/Amsterdam',utc),bytes([0x9f,1,int(summer)]))
            self.assertEqual(sync_packet(utc,'Europe/Amsterdam')[5:7],bytes([hour,t.minute]))
        self.assertEqual(settings()['refresh_minutes'],5)
        with self.assertRaises(ValueError):settings({'clock_timezone':'unknown'})
        r=render({'kind':'notice','title':'今日安排','body':'欢迎回家','footer':'2026-10-06 星期二'})
        import io
        from bitmap_fonts import text_mask
        self.assertEqual(len(r['frame']),8000)
        self.assertEqual(quantize(Image.open(io.BytesIO(r['png'])))['frame'],r['frame'])
        self.assertEqual(set(Image.open(io.BytesIO(r['png'])).get_flattened_data()),{(255,255,255),(0,0,0),(190,0,0)})
        self.assertGreater(text_mask('农历八月廿六',12).getbbox()[3],0)
        footer=text_mask('2026-10-06 星期二',18);footer=footer.crop(footer.getbbox())
        notice=Image.open(io.BytesIO(r['png']))
        for y in range(footer.height):
            for x in range(footer.width):
                self.assertEqual(notice.getpixel((8+x,104+y))==(0,0,0),bool(footer.getpixel((x,y))),'Notice footer must use the exact 18px bitmap')

    def test_registration_preserves_metadata_and_unregister_stops_only_pending_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'data.sqlite3');address='18:BC:5A:6B:91:A7'
            self.assertTrue(s.register(address))
            d=s.rows('SELECT * FROM devices')[0]
            self.assertEqual(d['name'],'ELINK-BWR-6B91A7');self.assertIsNone(d['last_seen'])
            s.device(address,'ELINK-BWR-6B91A7')
            s.execute('UPDATE devices SET settings=?,state=? WHERE address=?',('{"refresh_minutes":5}','{"firmware_id":"90559ec8"}',address))
            before=s.rows('SELECT * FROM devices')[0]
            self.assertFalse(s.register(address));self.assertEqual(s.rows('SELECT * FROM devices')[0],before)
            s.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(address,'template',10,0,1))
            done=s.queue(address,'probe',{});s.update_job(done,status='succeeded',receipt={'checked':True})
            waiting=s.queue(address,'probe',{});s.update_job(waiting,status='waiting')
            running=s.queue(address,'probe',{});self.assertTrue(s.claim(running))
            with self.assertRaisesRegex(ValueError,'正在执行'):s.unregister(address)
            self.assertEqual(s.rows('SELECT status FROM jobs WHERE id=?',(waiting,))[0]['status'],'waiting')
            self.assertEqual(len(s.rows('SELECT * FROM plans')),1)
            s.update_job(running,status='succeeded');s.unregister(address)
            self.assertEqual(s.rows('SELECT * FROM devices'),[]);self.assertEqual(s.rows('SELECT * FROM plans'),[])
            self.assertEqual(s.rows('SELECT status FROM jobs WHERE id=?',(waiting,))[0]['status'],'cancelled')
            self.assertFalse(s.claim(waiting));self.assertEqual(json.loads(s.rows('SELECT receipt FROM jobs WHERE id=?',(done,))[0]['receipt']),{'checked':True})
            self.assertTrue(s.register(address));self.assertEqual(len(s.rows('SELECT * FROM jobs')),3)
            s.db.close()
    def test_image_crop_rotation_and_untrusted_parameters(self):
        import io,math
        image=Image.new('RGB',(100,100),'white')
        for x in range(50):
            for y in range(100):image.putpixel((x,y),(190,0,0))
        buf=io.BytesIO();image.save(buf,format='PNG');raw=base64.b64encode(buf.getvalue()).decode()
        def show(crop):return Image.open(io.BytesIO(render({'kind':'image','image':raw,'crop':crop})['png']))
        cover={'mode':'cover','zoom':1,'x':0,'y':0,'rotation':0}
        self.assertEqual(render({'kind':'image','image':raw,'crop':cover})['red_pixels'],125*122)
        self.assertEqual(quantize(Image.new('RGB',(250,122),'black'))['red_pixels'],0)
        im=show(cover);self.assertEqual(im.getpixel((20,60)),(190,0,0));self.assertEqual(im.getpixel((230,60)),(255,255,255))
        im=show({**cover,'rotation':90});self.assertEqual(im.getpixel((120,10)),(190,0,0));self.assertEqual(im.getpixel((120,110)),(255,255,255))
        im=show({**cover,'mode':'contain'});self.assertEqual(im.getpixel((10,60)),(255,255,255));self.assertEqual(im.getpixel((70,60)),(190,0,0))
        for bad in ({**cover,'x':2},{**cover,'zoom':math.nan},{**cover,'zoom':True},{**cover,'rotation':45},{**cover,'rotation':True},{**cover,'mode':'unknown'}):
            with self.assertRaises(ValueError):show(bad)

    def test_new_display_capability_and_old_elink_status(self):
        for ident,commit,native in (('d78aa415',False,False),('6c3279f4',True,False),('14271ec2',True,True)):
            status=decode_status(b'ELK1\x01'+bytes(23)+bytes.fromhex(ident))
            self.assertTrue(status['photo_calendar'])
            self.assertEqual(status['photo_calendar_commit'],commit)
            self.assertEqual(status['photo_calendar_native_digits'],native)
            self.assertEqual(status['max_image_payload'],128)
        self.assertEqual(decode_ui_capabilities(b'ELUI\x01\x07\0\0'),{'embedded_calendar':True,'minute_region_refresh':True,'bold_clock':True,'global_clock_refresh':False,'quiet_sync':False,'default_page':False,'timezone_clock':False,'offline_reminders':False,'reminder_summary':False,'reminder_large_text':False})
        self.assertTrue(decode_ui_capabilities(b'ELUI\x01\x0f\0\0')['global_clock_refresh'])
        self.assertTrue(decode_ui_capabilities(b'ELUI\x01\x1f\0\0')['quiet_sync'])
        self.assertTrue(decode_ui_capabilities(b'ELUI\x01\x3f\0\0')['default_page'])
        self.assertTrue(decode_ui_capabilities(b'ELUI\x01\xff\1\0')['reminder_summary'])
        self.assertTrue(decode_ui_capabilities(b'ELUI\x01\xff\3\0')['reminder_large_text'])
        self.assertEqual(decode_ui_capabilities(b'ELK1\x01'+bytes(27)),{})
        for raw in (b'',b'ELUI\x02\x07\0\0',b'ELUI\x01\x07\2\0'):
            with self.assertRaises(ValueError):decode_ui_capabilities(raw)
    def test_rotation_and_two_planes_against_native_pixel_mapping(self):
        im=Image.new('RGB',(250,122),'white');im.putpixel((0,0),(0,0,0));im.putpixel((249,121),(190,0,0))
        f=quantize(im)['frame'];self.assertEqual(len(f),8000)
        self.assertEqual(f[249*16],0x7f);self.assertEqual(f[15],0xbf);self.assertEqual(f[4000+15],0x40)
        self.assertEqual(sum(f[4000:]),64)
    def test_lunar_new_years_and_sync_byte_encoding(self):
        for d,y in [(date(2020,1,25),0),(date(2025,1,29),5),(date(2026,2,17),6)]:
            self.assertEqual(lunar_fields(d),(y,0,1))
        self.assertEqual(sync_packet(datetime(2026,10,5,12,34,56)),bytes([0x91,0xea,7,9,5,12,34,56,1,6,7,25]))
        with self.assertRaises(ValueError):render({'kind':'clock','body':'99:99'})
    def test_persistence_backup_and_claim_cancel_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.sqlite3';s=Store(path);s.device('18:BC:5A:6B:91:A7','test')
            a=s.queue('18:BC:5A:6B:91:A7','probe',{});self.assertTrue(s.claim(a));self.assertFalse(s.cancel(a));self.assertFalse(s.claim(a))
            b=s.queue('18:BC:5A:6B:91:A7','probe',{});self.assertTrue(s.cancel(b));self.assertFalse(s.claim(b))
            s.backup(Path(tmp)/'backup.sqlite3');s.db.close()
            restarted=Store(path);self.assertEqual(restarted.rows('SELECT status FROM jobs WHERE id=?',(a,))[0]['status'],'delivery_unknown');restarted.db.close()

class Transport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data.sqlite3')
        self.address='18:BC:5A:6B:91:A7';self.store.device(self.address,'test')
        r=render({'kind':'notice','title':'测试','body':'HELLO','footer':'OK','red':True})
        self.store.execute('INSERT INTO templates VALUES(?,?,?,?,?,?,?)',('template','test',json.dumps({'kind':'notice','title':'测试','body':'HELLO','footer':'OK','red':True}),r['png'],r['frame'],r['sha256'],0))
        self.machine=Machine();self.drop=False;self.client=None
    async def asyncTearDown(self):self.store.db.close();self.tmp.cleanup()
    async def test_shared_page_switch_validates_capability_and_executes_new_native_pages(self):
        from test_product_ui import ProductMachine
        from test_firmware import BASE
        owner=self;self.machine=ProductMachine();self.page_packets=[];self.old=False
        class Scanner:
            @staticmethod
            async def find_device_by_address(address,timeout):return type('Device',(),{'name':'stale-windows-name'})()
        class Client:
            def __init__(self,*a,**kw):self.is_connected=False;self.services=type('Services',(),{'get_characteristic':lambda _,uuid:True})()
            async def connect(self):self.is_connected=True
            async def disconnect(self):self.is_connected=False
            async def write_gatt_char(self,char,data,response):
                owner.page_packets.append(data)
                owner.machine.cmd(data)
                if data[0]==0x9c:owner.machine.finish()
            async def read_gatt_char(self,*a,**kw):
                value=owner.machine.published
                return b'ELUI\x01\0\0\0' if owner.old and value[:4]==b'ELUI' else value
        import gateway
        real_sleep=asyncio.sleep
        async def quick_sleep(delay):await real_sleep(0)
        with patch.object(gateway,'BleakScanner',Scanner),patch.object(gateway,'BleakClient',Client),patch.object(gateway.asyncio,'sleep',quick_sleep):
            channel=Gateway(self.store)
            for action,mode in (('default',4),('resume',0),('calendar',3)):
                self.store.execute('INSERT OR REPLACE INTO plans VALUES(?,?,?,?,?)',(self.address,'template',1,0,1))
                ident=self.store.queue(self.address,action,{'clock_timezone':'Europe/Amsterdam','refresh_minutes':15} if action=='resume' else {})
                result=await channel.execute(self.store.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0])
                self.assertEqual(result['display_mode'],mode);self.assertEqual(result['result'],'busy_completed')
                if action=='default':
                    before=len(self.page_packets)
                    pixels=bytes(self.machine.uc.mem_read(BASE+0xdedc,4000))+bytes(self.machine.uc.mem_read(BASE+0xf15c,4000))
                    setting=self.store.queue(self.address,'sync',{'quiet':True})
                    await channel.execute(self.store.rows('SELECT * FROM jobs WHERE id=?',(setting,))[0])
                    self.machine.cmd(b'\x93');actual=decode_status(self.machine.published)
                    self.assertEqual(actual['display_mode'],2,'Quiet sync selects retained custom content to suppress clock painting')
                    self.assertEqual(bytes(self.machine.uc.mem_read(BASE+0xdedc,4000))+bytes(self.machine.uc.mem_read(BASE+0xf15c,4000)),pixels,'Offline reminder resync must preserve all static pixels')
                    self.assertTrue(any(p[0]==0x9e for p in self.page_packets[before:]))
                    self.machine.cmd(b'\xb4\0');self.assertEqual(self.machine.published[23],1)
                if action=='resume':
                    before=sum(p[0]==0x9e for p in self.page_packets)
                    conf={'clock_timezone':'Europe/Amsterdam','refresh_minutes':15}
                    setting=self.store.queue(self.address,'settings',conf)
                    actual=await channel.execute(self.store.rows('SELECT * FROM jobs WHERE id=?',(setting,))[0])
                    self.assertEqual(actual['display_mode'],0,'Changing refresh settings must keep the clock running')
                    self.assertEqual(sum(p[0]==0x9e for p in self.page_packets),before)
                self.assertEqual(self.store.rows('SELECT enabled FROM plans WHERE address=?',(self.address,))[0]['enabled'],0)
            self.assertIn(b'\x9c\x02',self.page_packets);self.assertIn(b'\x9c\x00',self.page_packets)
            self.assertTrue(any(p[0]==0x9e and len(p)==12 for p in self.page_packets))
            self.assertTrue(result['time_initialized']);self.assertEqual(result['clock_timezone'],'Europe/Amsterdam');self.assertEqual(result['clock_refresh_minutes'],15)
            self.assertIn(b'\x99\x0f\x01\x00',self.page_packets)
            self.old=True;before=len([p for p in self.page_packets if p[0]==0x9c])
            ident=self.store.queue(self.address,'resume',{})
            with self.assertRaisesRegex(ValueError,'升级'):await channel.execute(self.store.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0])
            self.assertEqual(len([p for p in self.page_packets if p[0]==0x9c]),before)
            self.assertFalse(any(p[0]==0x98 for p in self.page_packets),'New clock selection must never call legacy resume')
            self.assertEqual(self.store.rows('SELECT name FROM devices WHERE address=?',(self.address,))[0]['name'],'test')
    async def test_scheduled_notice_does_not_queue_over_pending_page_switch(self):
        from gateway import worker
        self.store.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(self.address,'template',1,0,1))
        ident=self.store.queue(self.address,'calendar',{})
        stop=asyncio.Event();seen=[]
        class Channel:
            async def execute(_,job):
                seen.append(job['action']);stop.set();return {'result':'test_boundary'}
        await worker(self.store,Channel(),stop)
        self.assertEqual(seen,['calendar'])
        self.assertEqual([j['id'] for j in self.store.rows('SELECT id FROM jobs')],[ident])
    async def test_optional_ui_query_requires_fresh_elink_and_clears_old_capabilities(self):
        owner=self;self.machine=Machine(BOOTSTRAP_DIR);self.bad_status=False
        class Client:
            is_connected=True
            _elink_caps={'default_page':True}
            async def write_gatt_char(_,char,data,response):
                owner.machine.cmd(data)
                if data[0]==0x9d or owner.bad_status:owner.machine.published=bytes(11)
            async def read_gatt_char(_,char,use_cached):return owner.machine.published
        client=Client();channel=Gateway(self.store)
        self.assertEqual(await channel.capabilities(client),{})
        self.assertEqual((await channel.status(client))['firmware_id'],'24f56403')
        self.bad_status=True
        with self.assertRaises(ValueError):await channel.capabilities(client)
        self.assertEqual(client._elink_caps,{})
    async def test_ota_gateway_reads_every_byte_before_commit_and_checks_new_boot(self):
        owner=self;self.machine=OtaMachine();self.boots=0;self.post_boot_cancel=0
        self.machine.cold_boot(firmware_file('-app.bin',BOOTSTRAP_DIR).read_bytes())
        self.machine.uc.mem_write(STATE+27,b'\x01')
        package=json.loads(firmware_file('.elink-update.json').read_text())
        class Scanner:
            @staticmethod
            async def find_device_by_address(address,timeout):return type('Device',(),{'name':'test'})()
        class Client:
            def __init__(self,*a,**kw):
                self.is_connected=False;self.services=type('Services',(),{'get_characteristic':lambda _,uuid:type('Char',(),{'max_write_without_response_size':244})()})()
            async def connect(self):
                self.is_connected=True
                if owner.boots:
                    h=owner.machine.flash[0x14000:0x14040];size,crc=struct.unpack_from('<II',h,4)
                    import zlib
                    raw=bytes(owner.machine.flash[0x14040:0x14040+size]);assert h[2]==0xaa and zlib.crc32(raw)==crc
                    owner.machine.cold_boot(raw)
            async def disconnect(self):self.is_connected=False
            async def write_gatt_char(self,char,data,response):
                # Existing clock application is independently known to boot;
                # execute its new interceptor, not unmodelled calendar ROM helpers.
                if data[0] in (0x91,0x9e):Machine.cmd(owner.machine,data)
                elif data[0]==0x9d and not owner.boots:
                    owner.machine.published=bytes(11) # Original clock reply to unsupported extension.
                else:owner.machine.cmd(data)
                if data[0]==0xa4:
                    owner.boots+=1;self.is_connected=False
                    # Real WinRT cancels an outstanding ATT operation when the tag resets.
                    raise OSError(None,'Operation cancelled by peripheral reset',None,-2147023673)
                if data==b'\x93' and owner.boots and not owner.post_boot_cancel:
                    owner.post_boot_cancel+=1
                    raise OSError(None,'First post-boot request interrupted',None,-2147023673)
            async def read_gatt_char(self,*a,**kw):return owner.machine.published
        import gateway
        real_sleep=asyncio.sleep
        async def quick_sleep(delay):await real_sleep(0)
        ident=self.store.queue(self.address,'ota',{'package':package});job=self.store.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0]
        channel=Gateway(self.store)
        with patch.object(gateway,'BleakScanner',Scanner),patch.object(gateway,'BleakClient',Client),patch.object(gateway.asyncio,'sleep',quick_sleep):
            result=await channel.execute(job)
        self.assertEqual(result['result'],'ota_boot_verified');self.assertEqual(result['firmware_id'],package['firmware_id']);self.assertEqual(self.boots,1)
        self.assertEqual(self.post_boot_cancel,1,'The verification loop must retry Windows-interrupted status reads')
        self.assertNotIn(self.address,channel.devices,'OTA reboot requires fresh WinRT discovery for subsequent jobs')
    async def test_end_to_end_gateway_to_real_thumb_code(self):
        owner=self;self.scans=0;self.connect_failure=False;self.writes=[];self.stale_packets={0x93,0x9d};self.volts=3009
        class FakeScanner:
            @staticmethod
            async def find_device_by_address(address,timeout):
                owner.scans+=1
                self.assertEqual(address,self.address)
                return type('Device',(),{'name':'DLG-CLOCK-TEST'})()
        class Client:
            def __init__(self,*a,**kw):
                self.is_connected=False;self.services=type('Services',(),{'get_characteristic':lambda _,uuid:True})()
                owner.client=self
                self.stale=False
            async def connect(self):
                if owner.connect_failure:raise OSError('WinRT connection error')
                self.is_connected=True
            async def disconnect(self):self.is_connected=False
            async def write_gatt_char(self,char,data,response):
                self.assert_response=response
                owner.writes.append(data[0])
                self.stale=False
                owner.machine.cmd(data)
                if data[0] in owner.stale_packets:
                    owner.stale_packets.remove(data[0]);self.stale=True
                if data[0]==0x97:
                    owner.machine.run(int(owner.machine.meta['labels']['finish'],16))
                    if owner.drop:raise ConnectionError('dropped after commit')
            async def read_gatt_char(self,char,**kw):
                if char==VOLTS:
                    owner.assertFalse(kw['use_cached'])
                    if owner.volts is None:raise ValueError('FF02 unavailable')
                    return owner.volts.to_bytes(2,'little')
                return bytes(11) if self.stale else owner.machine.published
        import gateway
        real_sleep=asyncio.sleep
        async def quick_sleep(delay):await real_sleep(0)
        def make_job(scheduled=False):
            payload={**snapshot(self.store.template('template')),'scheduled':scheduled};i=self.store.queue(self.address,'publish',payload)
            return self.store.rows('SELECT * FROM jobs WHERE id=?',(i,))[0]
        with patch.object(gateway,'BleakScanner',FakeScanner),patch.object(gateway,'BleakClient',Client),patch.object(gateway.asyncio,'sleep',quick_sleep):
            channel=Gateway(self.store)
            first=make_job();saved=self.store.template('template')
            self.store.delete_template('template')
            result=await channel.execute(first)
            self.store.execute('INSERT INTO templates VALUES(?,?,?,?,?,?,?)',tuple(saved[k] for k in ('id','title','spec','png','frame','sha256','created')))
            self.assertEqual(result['result'],'busy_completed');self.assertEqual(result['bytes'],8000)
            self.assertEqual(result['battery']['battery_mv'],3009);self.assertEqual(result['battery']['battery_percent'],100)
            stored=json.loads(self.store.rows('SELECT payload FROM jobs WHERE id=?',(first['id'],))[0]['payload'])
            actual=base64.b64decode(stored['frame'])
            self.assertEqual(actual,bytes(self.machine.uc.mem_read(0x07fcdedc,4000))+bytes(self.machine.uc.mem_read(0x07fcf15c,4000)))
            self.assertEqual(quantize(Image.open(__import__('io').BytesIO(base64.b64decode(stored['png']))))['sha256'],result['sha256'])
            self.assertIn(0x9e,self.writes);self.assertNotIn(0x91,self.writes,'First announcement must not select clock mode')
            self.assertFalse(self.client.is_connected);self.assertTrue(self.client.assert_response)
            self.store.update_job(first['id'],status='succeeded',receipt=result)
            unchanged=await channel.execute(make_job(True));self.assertEqual(unchanged['result'],'content_unchanged')
            self.volts=2900
            changed=await channel.execute(make_job(True));self.assertEqual(changed['result'],'busy_completed')
            self.assertEqual(changed['battery']['battery_percent'],67)
            self.assertNotEqual(changed['sha256'],result['sha256'],'A new measured battery value updates the queued frame and its receipt')
            self.machine.uc.mem_write(STATE+7,b'\0\0');self.machine.uc.mem_write(STATE+12,b'\0\0');self.machine.uc.mem_write(STATE+18,b'\0\0')
            recovered=await channel.execute(make_job(True));self.assertEqual(recovered['result'],'busy_completed')
            self.drop=True
            with self.assertRaises(DeliveryUnknown):await channel.execute(make_job())
            self.assertFalse(self.client.is_connected)
            self.assertEqual(self.scans,1)
            self.connect_failure=True
            with self.assertRaises(ConnectionError):await channel.execute(make_job())
            self.assertNotIn(self.address,channel.devices)
            self.connect_failure=False;self.drop=False
            ident=self.store.queue(self.address,'probe',{})
            result=await channel.execute(self.store.rows('SELECT * FROM jobs WHERE id=?',(ident,))[0])
            self.assertEqual(result['firmware_id'],self.machine.meta['firmware_id'])
            self.assertEqual(self.scans,2)
            self.volts=None
            missing=await channel.execute(make_job())
            self.assertIsNone(missing['battery']['battery_percent']);self.assertIn('FF02',missing['battery']['battery_error'])
if __name__=='__main__':unittest.main()
