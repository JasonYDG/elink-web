"""Serialized BLE transactions with explicit device identity and capability checks."""
import asyncio,json,time,secrets,base64,struct,zlib,hashlib,datetime
from bleak import BleakClient,BleakScanner
from bleak.exc import BleakError
from protocol import decode_album,SERVICE,CONTROL,VOLTS,decode_battery,decode_status,decode_ui_capabilities,decode_reminder_slot,decode_reminder_runtime,reminder_metadata,image_packets,policy_packet,timing_packet,sync_packet
from render import notice_battery,frame_png
from store import snapshot
from ota import validate_package,image,page_packets
from clock_time import settings,timezone_packet

class DeliveryUnknown(RuntimeError):pass

def check_windows_cancel(exc,command):
    if getattr(exc,'winerror',None) in (-2147023673,2147943623,1223):
        raise ConnectionError(f'蓝牙操作被 Windows 中止（0x800704C7，命令 {command[:2].hex().upper()}）；可能连接中断或设备重启，不代表你点击了取消') from exc
def block(data,size):
    if len(data)!=size:raise ValueError('像素读回长度不一致')
    return data
class Gateway:
    def __init__(self,store):self.store=store;self.lock=asyncio.Lock();self.devices={}
    async def scan(self):
        async with self.lock:
            found=await BleakScanner.discover(timeout=6,return_adv=True)
            result=[]
            for dev,ad in found.values():
                name=ad.local_name or dev.name or ''
                if name.startswith(('DLG-','ELINK-')):
                    self.devices[dev.address.upper()]=dev
                    self.store.device(dev.address.upper(),name)
                    result.append({'address':dev.address.upper(),'name':name,'rssi':ad.rssi})
            return result
    async def write(self,client,data):
        if not client.is_connected:raise ConnectionError('蓝牙已断开')
        try:await asyncio.wait_for(client.write_gatt_char(CONTROL,data,response=True),8)
        except OSError as exc:
            check_windows_cancel(exc,data)
            raise
    async def query(self,client,packet,decode):
        # VAL_SET_REQ is queued by the peripheral task after write confirmation.
        for attempt in range(3):
            await self.write(client,packet)
            await asyncio.sleep(.12)
            try:value=await asyncio.wait_for(client.read_gatt_char(CONTROL,use_cached=False),8)
            except OSError as exc:
                check_windows_cancel(exc,packet)
                raise
            try:return decode(value)
            except ValueError:
                if attempt==2:raise
    async def status(self,client):
        return {**await self.query(client,b'\x93',decode_status),**getattr(client,'_elink_caps',{}),**getattr(client,'_elink_battery',{})}
    async def wait_idle(self,client,job,state):
        deadline=time.monotonic()+190
        while True:
            if state.get('error'):raise DeliveryUnknown('刷新后设备报错：'+str(state['error']))
            if not state['busy']:return state
            self.store.update_job(job['id'],phase='等待屏幕刷新完成回执',progress=95)
            if time.monotonic()>deadline:raise DeliveryUnknown('设置或校时后未取得屏幕完成回执')
            await asyncio.sleep(1);state=await self.status(client)
    async def battery(self,client):
        try:
            raw=await asyncio.wait_for(client.read_gatt_char(VOLTS,use_cached=False),8)
            value=decode_battery(raw)
        except (ValueError,BleakError,TimeoutError,OSError) as exc:
            value={'battery_mv':None,'battery_percent':None,'battery_error':str(exc)}
        # Retrieval time; the peripheral doesn't expose the ADC sample timestamp.
        client._elink_battery={**value,'battery_read_at':time.time()}
        return client._elink_battery
    async def capabilities(self,client):
        client._elink_caps={}
        try:client._elink_caps=await self.query(client,b'\x9d',decode_ui_capabilities)
        except ValueError:
            # Pre-ELUI firmware can answer an unknown 9D with native clock data.
            # A fresh ELK1 response is still required; grant no display capabilities.
            await self.query(client,b'\x93',decode_status)
        return client._elink_caps
    async def reminder_slots(self,client):
        slots=[await self.query(client,bytes([0xb4,i]),decode_reminder_slot) for i in range(8)]
        if getattr(client,'_elink_caps',{}).get('reminder_summary'):
            for slot in slots:slot.update(await self.query(client,bytes([0xbb,slot['slot']]),decode_reminder_runtime))
        return slots
    async def reminder_cancel(self,client,tokens,slots):
        for token in set(tokens)-{0}:
            for slot in slots:
                if slot['token']!=token or slot['state']==248:continue
                await self.write(client,bytes([0xb5,slot['slot']])+struct.pack('<I',token))
                check=await self.query(client,bytes([0xb4,slot['slot']]),decode_reminder_slot)
                if check['token']!=token or check['state']!=248:raise ValueError('设备未确认取消离线提醒')
    async def read_frame(self,client,state):
        frame=bytearray()
        for plane in (0,4000):
            for off in range(0,4000,128):frame.extend((await self.query(client,b'\x9a'+struct.pack('<H',plane+off),lambda b:block(b,128)))[:min(128,4000-off)])
        check=await self.status(client)
        if check['busy'] or check['error'] or any(check.get(k)!=state.get(k) for k in ('display_mode','display_generation','transfer_id','firmware_id')):raise DeliveryUnknown('读回期间页面已变化，请重新读取状态')
        return bytes(frame)
    async def query_album(self,client):
        try:return await self.query(client,b'\xbd\x00',decode_album)
        except ValueError:
            state=await self.status(client)
            if state['error']!=6:raise
            # Firmware capability and the installed Flash model are separate checks.
            client._elink_caps['offline_album']=False
            return None

    async def stop_album(self,client,job,state):
        if not state.get('offline_album'):return state
        if state['busy']:state=await self.wait_idle(client,job,state)
        album=await self.query_album(client)
        if album is None:return {**state,'offline_album':False,'album_unavailable':'Flash 型号或分区读取不支持图库'}
        if album['enabled'] or album['writing']:
            await self.write(client,b'\xbd\x04');state=await self.status(client)
            if state['error']:raise ValueError('设备未接受停止轮播：'+str(state['error']))
            album=await self.query(client,b'\xbd\x00',decode_album)
            if album['enabled'] or album['running'] or album['writing']:raise DeliveryUnknown('停止轮播的回执不一致')
        state['album']=album;self.store.state(job['address'],state);return state

    async def install_album(self,client,job,payload,state):
        if not state.get('offline_album'):raise ValueError('离线图库需要配套 1.5.8 固件，请先升级并读取状态')
        from render import photo_calendar_frame
        frames=[base64.b64decode(x['frame'],validate=True) for x in payload['items']]
        if not 1<=len(frames)<=4 or any(len(f)!=8000 for f in frames):raise ValueError('图库必须包含 1–4 张完整的 8000 字节图片')
        if state['busy']:state=await self.wait_idle(client,job,state)
        album=await self.query_album(client)
        if album is None or album['protocol_version']<2:raise ValueError('保存图库需要 1.5.8 固件的分步写入修复；请先升级固件，旧版单图功能仍可使用')
        if not state.get('album_minute_tick'):raise ValueError('离线轮播需要1.5.9固件，修复非整秒校时后的换图计时')
        crcs=[zlib.crc32(frame) for frame in frames]
        reuse=not album['writing'] and album['has_config'] and album['count']==len(frames) and album['crc32']==crcs and album['photo_x']==[i['photo_x'] for i in payload['items']]
        sequence=((album['sequence'] if album['has_config'] else 1)+1)&0xffffffff
        if not reuse:
            self.store.update_job(job['id'],phase='检查图库分区并准备新图像区',progress=3)
            await self.write(client,b'\xbd\x01');check=await self.status(client)
            if check['error']:raise ValueError('图库未开始写入（型号、未知分区或设备忙）：'+str(check['error']))
        else:self.store.update_job(job['id'],phase='复用屏幕已保存图库，更新显示方式和间隔',progress=80)
        if payload['mode']=='calendar':
            config=self.config(job['address']);state=await self.configure(client,config,state)
            if not reuse or not state['time_initialized']:await self.sync(client,config,state,quiet=True)
            state=await self.wait_idle(client,job,await self.status(client))
            if reuse:sequence=((await self.query_album(client))['sequence']+1)&0xffffffff
        generation=state['display_generation'];started=time.monotonic()
        amount=min(128,max(17,getattr(client,'mtu_size',23)-6))
        for i,frame in enumerate(() if reuse else frames):
            transfer=secrets.randbelow(65535)+1;packets=list(image_packets(frame,transfer,amount))
            await self.write(client,packets[0]);check=await self.status(client)
            if check['error'] or check['transfer_id']!=transfer or check['display_mode']!=1:raise ValueError('设备拒绝接收图库图片')
            for j,packet in enumerate(packets[1:-1],1):
                await self.write(client,packet)
                if j%32==0 or j==len(packets)-2:
                    check=await self.status(client);expected=min(j*amount,8000)
                    if check['error'] or check['received']!=expected:raise ValueError('图库图片接收位置不一致')
                    self.store.update_job(job['id'],phase=f'上传第 {i+1}/{len(frames)} 张 · {expected}/8000 字节',progress=5+int(75*(i+expected/16000)/len(frames)))
            crc=crcs[i]
            for step in range(32):
                self.store.update_job(job['id'],phase=f'保存第 {i+1}/{len(frames)} 张到屏幕 · {step}/32 块已校验',progress=5+int(75*(i+(1+step/32)/2)/len(frames)))
                try:
                    await self.write(client,b'\xbd\x02'+bytes((i,payload['items'][i]['photo_x']))+struct.pack('<I',crc)+bytes([step]))
                    check=await self.status(client)
                    if check['error']:raise ValueError('Flash 写入或读回校验失败：'+str(check['error']))
                    album=await self.query(client,b'\xbd\x00',decode_album)
                    if not album['writing'] or album['staged_count']!=i+(step==31) or album['save_step']!=(step+1)%32:raise ValueError('设备写入进度与回执不一致')
                except Exception as exc:
                    raise ValueError(f'第 {i+1} 张第 {step+1}/32 块保存未完成，未提交新播放列表。请读取设备状态后重新保存：{exc}') from exc
        mode=int(payload['mode']=='calendar')
        self.store.update_job(job['id'],phase='提交播放列表并等待屏幕刷新',progress=88)
        interrupted=None
        try:
            try:await self.write(client,b'\xbd\x03'+bytes([mode])+struct.pack('<H',payload['interval_minutes']))
            except (ConnectionError,BleakError,TimeoutError,OSError) as exc:interrupted=exc
            for attempt in range(3):
                try:
                    if interrupted:
                        self.store.update_job(job['id'],phase='提交回执中断，重新连接核对图库（不重复写入）',progress=90)
                        try:await client.disconnect()
                        except Exception:pass
                        self.devices.pop(job['address'],None)
                        await asyncio.sleep(2);await asyncio.wait_for(client.connect(),15)
                    check=await self.wait_idle(client,job,await self.status(client))
                    album=await self.query(client,b'\xbd\x00',decode_album)
                    if not album['enabled'] or not album['running'] or album['sequence']!=sequence or album['count']!=len(frames) or album['mode']!=mode or album['interval_minutes']!=payload['interval_minutes'] or album['crc32']!=crcs or album['photo_x']!=[i['photo_x'] for i in payload['items']] or album['writing'] or album['index']!=0:
                        raise DeliveryUnknown('播放列表提交后的配置读回不一致')
                    if check['display_mode']!=7+mode or check['display_generation']==generation:raise DeliveryUnknown('图库未返回首张画面完成回执')
                    actual=await self.read_frame(client,check)
                    expected=photo_calendar_frame(frames[0],payload['items'][0]['photo_x'])['frame'] if mode else frames[0]
                    boundary=1216 if check.get('photo_calendar_wide') else 1344
                    if (not mode and actual!=expected) or any(actual[o+boundary:o+4000]!=expected[o+boundary:o+4000] for o in (0,4000)):
                        raise DeliveryUnknown('图库首张画面的像素读回不一致')
                    break
                except (ConnectionError,BleakError,TimeoutError,OSError) as exc:
                    interrupted=exc
                    if attempt==2:raise
        except Exception as exc:
            if isinstance(exc,DeliveryUnknown):raise
            raise DeliveryUnknown('图库已尝试提交，结果待核对：'+str(exc)) from exc
        self.store.update_job(job['id'],payload={**payload,'display_png':base64.b64encode(frame_png(actual)).decode()})
        self.store.state(job['address'],{**check,'album':album})
        return {**check,'result':'album_config_verified' if reuse else 'album_flash_verified','album':album,'offline':True,'bytes':8000*len(frames),'transmitted_image_bytes':0 if reuse else 8000*len(frames),'reused_gallery':reuse,'pixel_payload_bytes':amount,'generation_before':generation,'generation_after':check['display_generation'],'recovered_after_disconnect':interrupted is not None,'total_seconds':round(time.monotonic()-started,3),'optical_result_verified':False}

    async def overview(self,client,job,state):
        state=await self.stop_album(client,job,state)
        if not state.get('reminder_summary'):raise ValueError('任务汇总、重复及持续时间需要 V1.5.0 固件')
        deadline=time.monotonic()+190
        while state['busy']:
            if time.monotonic()>deadline:raise TimeoutError('屏幕仍忙，未切换任务汇总')
            await asyncio.sleep(1);state=await self.status(client)
        if not state['time_initialized']:
            config=self.config(job['address']);state=await self.configure(client,config,state)
            await self.sync(client,config,state,quiet=True);state=await self.status(client)
        await self.write(client,b'\xb3'+struct.pack('<i',int(datetime.datetime.now().astimezone().utcoffset().total_seconds())))
        generation=state['display_generation'];self.store.update_job(job['id'],phase='切换今日任务汇总，等待屏幕完成')
        await self.write(client,b'\xb9');actual=await self.status(client)
        if actual['error'] or actual['display_mode']!=5:raise ValueError('设备拒绝任务汇总页面')
        while actual['busy']:
            if time.monotonic()>deadline:raise DeliveryUnknown('任务汇总刷新结果待核对')
            await asyncio.sleep(1);actual=await self.status(client)
        if actual['error'] or actual['display_generation']==generation:raise DeliveryUnknown('任务汇总未返回刷新完成回执')
        frame=await self.read_frame(client,actual)
        old=json.loads(self.store.rows('SELECT payload FROM jobs WHERE id=?',(job['id'],))[0]['payload']);old['display_png']=base64.b64encode(frame_png(frame)).decode()
        self.store.update_job(job['id'],payload=old);self.store.state(job['address'],actual)
        self.store.execute('UPDATE plans SET enabled=0 WHERE address=?',(job['address'],))
        return {**actual,'result':'reminder_summary_ram_verified','generation_after':actual['display_generation'],'summary_sha256':hashlib.sha256(frame).hexdigest(),'optical_result_verified':False}
    async def install_reminder(self,client,job,payload,state):
        if not state.get('reminder_summary'):raise ValueError('任务汇总、重复及持续时间需要 V1.5.0 固件，请先升级所选屏幕')
        deadline=time.monotonic()+190
        while state['busy']:
            if time.monotonic()>deadline:raise TimeoutError('屏幕仍忙，尚未写入日程')
            await asyncio.sleep(1);state=await self.status(client)
        slots=await self.reminder_slots(client)
        if payload['operation']=='cancel':
            self.store.update_job(job['id'],phase='取消标签中的离线日程并读回验证')
            await self.reminder_cancel(client,[payload['token'],payload.get('previous_token',0)],slots)
            summary=await self.overview(client,job,await self.status(client))
            return {**summary,'result':'reminder_cancel_verified','token':payload['token']}
        if not state['time_initialized']:
            config=self.config(job['address']);state=await self.configure(client,config,state)
            await self.sync(client,config,state,quiet=True)
        # UTC due time stays independent of the Netherlands repeated autumn hour.
        offset=int(datetime.datetime.now().astimezone().utcoffset().total_seconds())
        await self.write(client,b'\xb3'+struct.pack('<i',offset))
        metadata=reminder_metadata(payload.get('title','任务提醒'),payload.get('options'),large=state.get('reminder_large_text',False));token=payload['token'];frame=base64.b64decode(payload['frame'],validate=True);checksum=zlib.crc32(frame)
        if len(frame)!=8000:raise ValueError('离线提醒须为完整 8000 字节 BWR 图像')
        existing=next((s for s in slots if s['token']==token and s['state'] in (254,252)),None)
        if existing:
            if existing['due']!=payload['due'] or existing['crc32']!=checksum:raise ValueError('提醒标识与标签内容冲突')
            slot=existing['slot']
        else:
            free=next((s for s in slots if s['state']!=254),None)
            if free is None:raise ValueError('标签日程存储已满，请先删除并确认旧提醒')
            slot=free['slot'];self.store.update_job(job['id'],phase='提前写入提醒画面到独立 Flash 日程区')
            await self.write(client,b'\xb6')
            await self.write(client,bytes([0xb0,slot])+struct.pack('<III',token,payload['due'],checksum))
            for off in range(0,8000,17):
                await self.write(client,b'\xb1'+struct.pack('<H',off)+frame[off:off+17])
                if off//17%32==0 or off+17>=8000:
                    check=await self.query(client,bytes([0xb4,slot]),decode_reminder_slot)
                    if check['received']!=min(off+17,8000) or not check['writing']:raise ValueError('离线提醒写入位置不一致')
                    self.store.update_job(job['id'],progress=5+int(65*min(off+17,8000)/8000))
            self.store.update_job(job['id'],phase='读回全部提醒像素，核对 CRC 与 SHA256')
            read=bytearray()
            for off in range(0,8000,128):
                count=min(128,8000-off)
                data=await self.query(client,bytes([0xb7,slot])+struct.pack('<H',off),lambda b:block(b,count))
                read.extend(data)
            if bytes(read)!=frame:raise ValueError('离线提醒全量读回校验失败，未启用提醒')
            for off in range(0,156,18):await self.write(client,bytes([0xb8,off])+metadata[off:off+18])
            await self.write(client,b'\xb2'+struct.pack('<I',token))
        read=bytearray()
        for off in (0,128):
            count=min(128,156-off);read.extend(await self.query(client,bytes([0xba,slot])+struct.pack('<H',off),lambda b:block(b,count)))
        if bytes(read)!=metadata:raise ValueError('提醒策略或汇总文字读回不一致')
        check=await self.query(client,bytes([0xb4,slot]),decode_reminder_slot)
        if check['token']!=token or check['state'] not in (254,252) or check['due']!=payload['due'] or check['crc32']!=checksum or not check['clock_ready']:raise ValueError('标签未确认离线提醒已启用')
        await self.reminder_cancel(client,[payload.get('previous_token',0)],await self.reminder_slots(client))
        summary=await self.overview(client,job,await self.status(client))
        runtime=await self.query(client,bytes([0xbb,slot]),decode_reminder_runtime)
        return {**summary,**runtime,'result':'reminder_flash_verified','slot':slot,'token':token,'due':payload['due'],'crc32':checksum,'sha256':hashlib.sha256(frame).hexdigest(),'bytes':8000,'offline':True,'slot_state':check['state'],'optical_result_verified':False}
    async def reminder_preview(self,client,address,state,slots):
        if state.get('display_mode')!=2 or not slots or slots[0]['last_slot']<0:return
        current=slots[slots[0]['last_slot']]
        if current['state'] not in (254,252) or state['transfer_id']!=(current['token']&65535):return
        rows=self.store.rows("SELECT j.id FROM reminders r JOIN jobs j ON j.id=r.job_id WHERE r.address=? AND r.token=? AND j.status='succeeded'",(address,current['token']))
        if not rows:return
        frame=bytearray()
        for plane in (0,4000):
            for off in range(0,4000,128):
                frame.extend((await self.query(client,b'\x9a'+struct.pack('<H',plane+off),lambda b:block(b,128)))[:min(128,4000-off)])
        check=await self.status(client)
        if check['busy'] or check['error'] or check['display_generation']!=state['display_generation'] or check['transfer_id']!=state['transfer_id']:return
        ident=rows[0]['id'];job=self.store.rows('SELECT payload,receipt FROM jobs WHERE id=?',(ident,))[0];payload=json.loads(job['payload']);receipt=json.loads(job['receipt'])
        payload.update(display_png=base64.b64encode(frame_png(frame)).decode(),frame=base64.b64encode(frame).decode(),png=base64.b64encode(frame_png(frame)).decode(),sha256=hashlib.sha256(frame).hexdigest())
        receipt.update(result='offline_reminder_ram_verified',generation_after=state['display_generation'],transfer_id=state['transfer_id'],firmware_id=state['firmware_id'],sha256=payload['sha256'],optical_result_verified=False)
        self.store.update_job(ident,payload=payload,receipt=receipt)
    def config(self,address,changes=None):
        saved=json.loads(self.store.rows('SELECT settings FROM devices WHERE address=?',(address,))[0]['settings'])
        return settings({**saved,**(changes or {})})
    async def configure(self,client,config,state):
        if config['mode']==1 and not state.get('global_clock_refresh'):raise ValueError('整页时钟快刷需要 1.1.1 或更新固件')
        if config['mode']==2 and not state.get('minute_region_refresh'):raise ValueError('分钟局刷需要 1.1.0 或更新固件')
        if config['clock_timezone']!='local' and not state.get('timezone_clock'):raise ValueError('荷兰时钟需要 1.3.0 或更新固件')
        deadline=time.monotonic()+95
        while state['busy']:
            if time.monotonic()>deadline:raise TimeoutError('屏幕仍忙，尚未应用设置')
            await asyncio.sleep(1);state=await self.status(client)
        if state.get('timezone_clock'):await self.write(client,timezone_packet(config['clock_timezone']))
        await self.write(client,policy_packet(config['mode'],config['full_every']))
        await self.write(client,timing_packet(config['refresh_minutes'],config['advertise_minutes'],config['window_seconds']))
        actual=await self.status(client)
        wanted={'mode':config['mode'],'full_every':config['full_every'],'clock_refresh_minutes':config['refresh_minutes'],'advertise_every_minutes':config['advertise_minutes'],'advertise_window_seconds':config['window_seconds']}
        if state.get('timezone_clock'):wanted['clock_timezone']=config['clock_timezone']
        if actual['error'] or any(actual[k]!=v for k,v in wanted.items()):raise ValueError('设备设置读回不一致')
        return actual
    async def sync(self,client,config,state,quiet=False):
        album=await self.query(client,b'\xbd\x00',decode_album) if state.get('offline_album') and state.get('display_mode') in (7,8) else None
        resume=album and album['enabled'] and not album['writing']
        if resume:quiet=True
        packet=sync_packet(timezone=config['clock_timezone'])
        if quiet and state.get('quiet_sync'):packet=b'\x9e'+packet[1:]
        if state.get('offline_reminders'):
            offset=int(datetime.datetime.now().astimezone().utcoffset().total_seconds())
            await self.write(client,b'\xb3'+struct.pack('<i',offset))
        await self.write(client,packet);await asyncio.sleep(.3)
        if resume:
            await self.write(client,b'\xbd\x03'+bytes([album['mode']])+struct.pack('<H',album['interval_minutes']))
            check=await self.status(client)
            if check['error']:raise DeliveryUnknown('校时后图库恢复未确认：'+str(check['error']))
        return packet
    async def upgrade(self,client,job,payload,state):
        raw,version=validate_package(payload['package']);wire=image(raw,version)
        if state['firmware_id']==payload['package']['firmware_id']:raise ValueError('设备已经运行此版本，未擦写固件。')
        char=client.services.get_characteristic(CONTROL)
        deadline=time.monotonic()+10
        while char.max_write_without_response_size<136 and time.monotonic()<deadline:await asyncio.sleep(.25)
        if char.max_write_without_response_size<136:raise ValueError('OTA 需要至少 139 字节 ATT MTU；当前连接容量不足，尚未擦写固件。可更换蓝牙适配器后重试。')
        if not state['time_initialized']:
            await self.sync(client,self.config(job['address']),state);state=await self.status(client)
        deadline=time.monotonic()+45
        while state['busy']:
            if time.monotonic()>deadline:raise TimeoutError('屏幕仍忙，OTA 尚未开始')
            await asyncio.sleep(1);state=await self.status(client)
        started=False;finalized=False
        receipt={'result':'ota_preparing','firmware_id':payload['package']['firmware_id'],'sha256':payload['package']['sha256'],'bytes':len(raw)}
        try:
            self.store.update_job(job['id'],phase='上传到非活动固件区')
            started=True
            await self.write(client,b'\xa0\x00'+len(raw).to_bytes(2,'little'))
            for off in range(0,len(wire),256):
                for packet in page_packets(wire[off:off+256]):await self.write(client,packet)
                self.store.update_job(job['id'],progress=5+int(55*(off+256)/len(wire)))
            # Native first page carries its new bank flag and invalid 0xff tag.
            self.store.update_job(job['id'],phase='逐块读回并校验固件')
            expected=bytearray(wire);expected[2]=255
            for off in range(0,len(wire),128):
                for attempt in range(3):
                    await self.write(client,b'\xa1'+off.to_bytes(2,'little'))
                    await asyncio.sleep(.12)
                    read=bytes(await asyncio.wait_for(client.read_gatt_char(CONTROL,use_cached=False),8))
                    if off==0 and len(read)==128:
                        if not 0<=read[3]<=127:raise ValueError('OTA 启动区序号不安全，请使用有线升级恢复')
                        expected[3]=read[3]
                    if read==expected[off:off+128]:break
                else:raise ValueError('OTA 读回校验失败，偏移 '+hex(off)+'；新固件区保持无效')
                self.store.update_job(job['id'],progress=60+int(30*(off+128)/len(wire)))
            receipt['result']='ota_readback_verified'
            self.store.update_job(job['id'],receipt=receipt,progress=92,phase='提交启动标记，等待重启核对版本')
            finalized=True # Reset can prevent the last ATT response from reaching the host.
            try:await self.write(client,b'\xa4')
            except (ConnectionError,BleakError,TimeoutError,OSError):pass
            try:await client.disconnect()
            except Exception:pass
            # A firmware reboot invalidates the pre-upgrade WinRT discovery object.
            # The next transaction must discover the device again.
            self.devices.pop(job['address'],None)
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                await asyncio.sleep(2)
                try:
                    await asyncio.wait_for(client.connect(),15)
                    check=await self.status(client)
                    if check.get('firmware_id')==receipt['firmware_id']:
                        check.update(await self.capabilities(client))
                        check.update(await self.battery(client))
                        config=self.config(job['address'])
                        check=await self.configure(client,config,check)
                        await self.sync(client,config,check,quiet=True)
                        check=await self.status(client)
                        self.store.state(job['address'],check)
                        return {**receipt,'result':'ota_boot_verified','physical_display_confirmed':False}
                    raise DeliveryUnknown('重启后版本标识不匹配，请读取设备状态核对')
                except DeliveryUnknown:raise
                except (ConnectionError,BleakError,TimeoutError,ValueError,OSError):
                    try:await client.disconnect()
                    except Exception:pass
            raise DeliveryUnknown('OTA 镜像已读回验证，提交后未确认新版本启动')
        except Exception as exc:
            if started and not finalized:
                try:await self.write(client,b'\xa5') # Reset without marking the candidate bank valid.
                except Exception:pass
            if finalized:raise DeliveryUnknown('OTA 提交后结果待核对：'+str(exc)) from exc
            if started:raise ValueError('OTA 未提交启动标记：'+str(exc)) from exc
            raise
    async def execute(self,job):
        async with self.lock:
            address=job['address'];payload=json.loads(job['payload'])
            started_at=time.monotonic()
            self.store.update_job(job['id'],phase='查找标签广播')
            # WinRT may retain the physical connection briefly after dispose.
            # Reuse discovery, not GATT state: every operation reads uncached services/status.
            dev=self.devices.get(address)
            if dev is None:
                dev=await BleakScanner.find_device_by_address(address,timeout=8)
            if dev is None:raise ConnectionError('设备未广播；任务等待下一接收窗口。')
            self.devices[address]=dev
            client=BleakClient(dev,timeout=15,services=[SERVICE],winrt={'use_cached_services':False})
            committed=False
            try:
                self.store.update_job(job['id'],phase='建立蓝牙连接并获取 GATT 服务')
                try:await asyncio.wait_for(client.connect(),20)
                except (BleakError,TimeoutError,OSError) as exc:
                    self.devices.pop(address,None)
                    raise ConnectionError('蓝牙连接失败，将重新扫描重试：'+str(exc)) from exc
                if not client.services.get_characteristic(CONTROL):raise ValueError('设备没有 HMCLOCK FF01 控制特征')
                # Preserve the scan response name; Windows dev.name can remain cached after OTA.
                self.store.execute('UPDATE devices SET last_seen=?,updated=? WHERE address=?',(time.time(),time.time(),address))
                self.store.update_job(job['id'],status='running',progress=2,error=None,phase='读取设备状态与电池电压')
                try:state=await self.status(client)
                except ValueError:state={'protocol':0,'display_mode':'legacy','note':'原版 HMCLOCK，仅支持校时'}
                if state.get('protocol')==1:state.update(await self.capabilities(client))
                state.update(await self.battery(client))
                self.store.state(address,state)
                action=job['action']
                if action=='probe':
                    if state.get('offline_album') and not state['busy']:
                        state['album']=await self.query_album(client);state['offline_album']=state['album'] is not None;self.store.state(address,state)
                    if state.get('offline_reminders') and not state['busy']:
                        slots=await self.reminder_slots(client);state['reminder_slots']=slots
                        self.store.reconcile_reminders(address,slots)
                        self.store.state(address,state)
                    if state.get('protocol')==1 and not state['busy'] and not state['error']:
                        self.store.update_job(job['id'],phase='状态已读取，正在读回屏幕像素',progress=50)
                        try:
                            frame=await self.read_frame(client,state)
                            self.store.update_job(job['id'],payload={**payload,'display_png':base64.b64encode(frame_png(frame)).decode()})
                            return {**state,'generation_after':state['display_generation'],'pixel_readback_verified':True,'frame_sha256':hashlib.sha256(frame).hexdigest()}
                        except (ConnectionError,BleakError,TimeoutError,OSError,ValueError,DeliveryUnknown) as exc:
                            state['preview_error']='状态已读取，画面读回未完成：'+str(exc)
                            self.store.state(address,state)
                    return state
                if action=='sync':
                    self.store.update_job(job['id'],phase='校准设备时间并核对状态')
                    config=self.config(address)
                    if state.get('protocol')==1:state=await self.configure(client,config,state)
                    elif config['clock_timezone']!='local':raise ValueError('荷兰时钟需要 1.3.0 或更新固件')
                    committed=True
                    packet=await self.sync(client,config,state,quiet=payload.get('quiet',False) and state.get('display_mode') not in (0,3))
                    if state.get('display_mode')==5:await self.overview(client,job,await self.status(client))
                    # Original clock_push updates FF01; allow the peripheral task to run.
                    await asyncio.sleep(.3)
                    if state.get('protocol')==1:
                        actual=await self.wait_idle(client,job,await self.status(client));self.store.state(address,actual)
                        if actual.get('offline_reminders') and not actual['busy']:self.store.reconcile_reminders(address,await self.reminder_slots(client))
                    return {'result':'gatt_write_confirmed','packet_hex':packet.hex(),'physical_display_confirmed':False}
                if state.get('protocol')!=1:raise ValueError('需要刷入 ELK1 优化固件才支持此操作；原版仅可校时。')
                if action=='ota':return await self.upgrade(client,job,payload,state)
                if action=='album':return await self.install_album(client,job,payload,state)
                if action=='album_stop':return await self.stop_album(client,job,state)
                if action in ('default','resume','calendar','publish','photo_calendar'):
                    state=await self.stop_album(client,job,state)
                if action=='overview':return await self.overview(client,job,state)
                if action=='reminder':return await self.install_reminder(client,job,payload,state)
                if action=='settings':
                    self.store.update_job(job['id'],phase='应用设置并读回验证')
                    config=self.config(address,payload);actual=await self.configure(client,config,state)
                    if not state['time_initialized'] or state.get('clock_timezone','local')!=config['clock_timezone']:
                        committed=True
                        await self.sync(client,config,actual,quiet=state['display_mode'] not in (0,3));actual=await self.status(client)
                        if state.get('display_mode')==5:actual=await self.overview(client,job,actual)
                    actual=await self.wait_idle(client,job,actual)
                    self.store.execute('UPDATE devices SET settings=? WHERE address=?',(json.dumps(config),address))
                    self.store.state(address,actual);return actual
                if action in ('default','resume','calendar'):
                    self.store.update_job(job['id'],phase='等待屏幕空闲并设置目标页面')
                    capability={'default':'default_page','resume':'bold_clock','calendar':'embedded_calendar'}[action]
                    if not state.get(capability):raise ValueError('此标签不支持所选新版页面，请先 OTA 升级；未发送旧时钟命令')
                    deadline=time.monotonic()+95
                    while state['busy']:
                        if time.monotonic()>deadline:raise TimeoutError('屏幕仍忙，尚未切换页面')
                        await asyncio.sleep(1);state=await self.status(client)
                    if action!='default':
                        config=self.config(address,payload)
                        state=await self.configure(client,config,state)
                        await self.sync(client,config,state,quiet=True)
                        state=await self.status(client)
                        while state['busy']:
                            if time.monotonic()>deadline:raise TimeoutError('校时刷新未结束，尚未切换页面')
                            await asyncio.sleep(1);state=await self.status(client)
                        self.store.execute('UPDATE devices SET settings=? WHERE address=?',(json.dumps(config),address))
                    view,mode={'default':(2,4),'resume':(0,0),'calendar':(1,3)}[action]
                    generation=state['display_generation']
                    await self.write(client,bytes([0x9c,view]));actual=await self.status(client)
                    if actual['error'] or actual['display_mode']!=mode:raise ValueError('设备未接受所选页面')
                    # Once accepted, a lost connection leaves the display result uncertain.
                    committed=True;deadline=time.monotonic()+190
                    self.store.update_job(job['id'],phase='等待清屏及目标页面刷新完成')
                    while actual['busy']:
                        if time.monotonic()>deadline:raise DeliveryUnknown('页面刷新未取得完成回执')
                        await asyncio.sleep(1);actual=await self.status(client)
                        if actual['error']:raise DeliveryUnknown('页面刷新失败：'+str(actual['error']))
                    if actual['display_generation']==generation:raise DeliveryUnknown('页面未返回新的显示序号')
                    self.store.state(address,actual)
                    self.store.execute('UPDATE plans SET enabled=0 WHERE address=?',(address,))
                    return {**actual,'result':'busy_completed','optical_result_verified':False}
                if action not in ('publish','photo_calendar'):raise ValueError('未知设备动作')
                if action=='photo_calendar' and not state.get('photo_calendar'):raise ValueError('图片日历需要1.5.4固件；未发送图片')
                # A delivery uses its immutable queued snapshot, even if the template was edited/deleted.
                if payload.get('kind','notice')=='notice':
                    drawn=notice_battery(base64.b64decode(payload['png'],validate=True),state['battery_percent'])
                    payload={**payload,'frame':base64.b64encode(drawn['frame']).decode(),'png':base64.b64encode(drawn['png']).decode(),'sha256':drawn['sha256'],'battery':client._elink_battery}
                    self.store.update_job(job['id'],payload=payload)
                frame=base64.b64decode(payload['frame'],validate=True)
                if payload.get('scheduled'):
                    latest=self.store.rows("SELECT payload,receipt FROM jobs WHERE address=? AND action=? AND status='succeeded' ORDER BY created DESC LIMIT 1",(address,action))
                    if latest:
                        old=json.loads(latest[0]['payload']);done=json.loads(latest[0]['receipt'])
                        if old.get('sha256')==payload['sha256'] and state['display_mode']==(6 if action=='photo_calendar' else 2) and not state['busy'] and done.get('transfer_id')==state['transfer_id'] and done.get('generation_after')==state['display_generation'] and done.get('firmware_id')==state['firmware_id']:
                            if old.get('display_png'):self.store.update_job(job['id'],payload={**payload,'display_png':old['display_png']})
                            return {**done,'result':'content_unchanged','checked_at':time.time()}
                state=await self.configure(client,self.config(address),state)
                # Unset native time causes the QR screen to redraw each minute.
                # Initialize it once per power cycle before taking ownership of the planes.
                if not state['time_initialized'] or action=='photo_calendar':
                    packet=sync_packet(timezone=self.config(address)['clock_timezone'])
                    if state.get('quiet_sync'):
                        deadline=time.monotonic()+95
                        while state['busy']:
                            if time.monotonic()>deadline:raise TimeoutError('屏幕仍忙，尚未静默校时或传图')
                            await asyncio.sleep(1);state=await self.status(client)
                        packet=b'\x9e'+packet[1:]
                    await self.sync(client,self.config(address),state,quiet=True)
                    state=await self.status(client)
                    if not state['time_initialized']:raise ValueError('设备首次校时未确认，未开始传图')
                deadline=time.monotonic()+45
                while state['busy']:
                    if time.monotonic()>deadline:raise TimeoutError('屏幕仍忙，未开始传图')
                    await asyncio.sleep(1);state=await self.status(client)
                transfer=secrets.randbelow(65535)+1;generation=state['display_generation']
                payload_bytes=min(state.get('max_image_payload',17),max(17,getattr(client,'mtu_size',23)-6))
                direct_photo=action=='photo_calendar' and state.get('photo_calendar_commit',False)
                packets=list(image_packets(frame,transfer,payload_bytes))
                prepared_at=time.monotonic()
                self.store.update_job(job['id'],phase=f'发送图片：每包{payload_bytes}字节，共{len(packets)-2}包')
                await self.write(client,packets[0])
                check=await self.status(client)
                if check['error'] or check['transfer_id']!=transfer or check['display_mode']!=1:raise ValueError('设备拒绝开始传图')
                for i,p in enumerate(packets[1:-1],1):
                    await self.write(client,p)
                    if i%32==0 or i==len(packets)-2:
                        check=await self.status(client)
                        expected=min(i*payload_bytes,8000)
                        if check['error'] or check['received']!=expected:raise ValueError('设备接收位置不一致，已停止发送')
                        self.store.update_job(job['id'],progress=5+int(85*expected/8000),phase=f'传输已核对 {expected}/8000 字节 · {i}/{len(packets)-2} 包')
                if check['sum16']!=sum(frame)&65535:raise ValueError('图片校验和不一致')
                transferred_at=time.monotonic()
                receipt={'transfer_id':transfer,'sha256':payload['sha256'],'generation_before':generation,'bytes':8000,'firmware_id':state['firmware_id'],'battery':client._elink_battery,'pixel_payload_bytes':payload_bytes,'pixel_packets':len(packets)-2,'att_mtu':getattr(client,'mtu_size',23),'direct_photo_commit':direct_photo,'prepare_seconds':round(prepared_at-started_at,3),'transfer_seconds':round(transferred_at-prepared_at,3)}
                self.store.update_job(job['id'],status='awaiting_display',receipt=receipt,progress=92,phase='图片已接收，等待清屏与刷新回执')
                # Mark uncertain before awaiting: a disconnect can occur after physical acceptance.
                committed=True;await self.write(client,b'\x9c\x03' if direct_photo else packets[-1])
                deadline=time.monotonic()+190
                while time.monotonic()<deadline:
                    await asyncio.sleep(1);check=await self.status(client)
                    if check['error']:raise DeliveryUnknown('提交后设备报错：'+str(check['error']))
                    if not check['busy'] and check['transfer_id']==transfer and check['display_generation']!=generation:
                        if check['display_mode']!=(6 if direct_photo else 2):raise DeliveryUnknown('传图完成时页面已被其他功能切换')
                        if action=='photo_calendar':
                            if not direct_photo:
                                before=check['display_generation']
                                self.store.update_job(job['id'],phase='旧固件兼容：合成日历并等待刷新',progress=95)
                                await self.write(client,b'\x9c\x03');check=await self.status(client)
                                if check['error'] or check['display_mode']!=6:raise DeliveryUnknown('图片已发送，但设备未接受图片日历主题')
                                check=await self.wait_idle(client,job,check)
                                if check['display_generation']==before:raise DeliveryUnknown('图片日历未返回新的显示序号')
                            if check['display_mode']!=6 or check['transfer_id']!=transfer or check['firmware_id']!=receipt['firmware_id']:raise DeliveryUnknown('图片日历刷新期间页面或设备状态已变化')
                            refreshed_at=time.monotonic()
                            self.store.update_job(job['id'],phase='屏幕刷新已完成，读回最终画面校验',progress=97)
                            actual_frame=await self.read_frame(client,check)
                            payload={**payload,'display_png':base64.b64encode(frame_png(actual_frame)).decode()}
                            self.store.update_job(job['id'],payload=payload)
                            receipt['display_sha256']=hashlib.sha256(actual_frame).hexdigest()
                        else:refreshed_at=time.monotonic()
                        receipt.update(refresh_seconds=round(refreshed_at-transferred_at,3),readback_seconds=round(time.monotonic()-refreshed_at,3),total_seconds=round(time.monotonic()-started_at,3))
                        self.store.state(address,check)
                        return {**receipt,'result':'busy_completed','generation_after':check['display_generation'],'optical_result_verified':False}
                raise DeliveryUnknown('190 秒内未取得清屏与目标画面的完成回执；请检查 BUSY 与实际显示。')
            except Exception as exc:
                if committed and not isinstance(exc,DeliveryUnknown):raise DeliveryUnknown('提交后连接中断，显示结果待核对：'+str(exc)) from exc
                raise
            finally:
                try:await asyncio.wait_for(client.disconnect(),5)
                except Exception:pass # Disconnect cleanup must not mask transaction failure.

async def worker(store,gateway,stop):
    while not stop.is_set():
        store.dispatch_reminders()
        # Plans enqueue a real saved template; unchanged content is not resent.
        for plan in store.rows('SELECT * FROM plans WHERE enabled=1 AND next_due<=?',(time.time(),)):
            with store.lock:
                if not store.rows('SELECT address FROM plans WHERE address=? AND enabled=1',(plan['address'],)):continue
                outstanding=store.rows("SELECT id FROM jobs WHERE address=? AND status IN ('queued','waiting','running','awaiting_display')",(plan['address'],))
                if not outstanding:
                    latest=store.rows("SELECT payload,status FROM jobs WHERE address=? AND action='publish' ORDER BY created DESC LIMIT 1",(plan['address'],))
                    if latest and latest[0]['status']=='delivery_unknown':
                        store.execute('UPDATE plans SET enabled=0 WHERE address=?',(plan['address'],));continue
                    try:content=snapshot(store.template(plan['template_id']))
                    except Exception as exc:
                        store.execute('UPDATE plans SET enabled=0 WHERE address=?',(plan['address'],))
                        ident=store.queue(plan['address'],'publish',{'template_id':plan['template_id'],'scheduled':True})
                        store.update_job(ident,status='failed',error='计划内容生成失败，计划已停用：'+str(exc))
                        continue
                    # Even unchanged content needs a real device-state check: power loss
                    # resets RAM/clock ownership while host history remains persistent.
                    store.queue(plan['address'],'publish',{**content,'scheduled':True})
                store.execute('UPDATE plans SET next_due=? WHERE address=?',(time.time()+plan['interval_minutes']*60,plan['address']))
        rows=store.rows("SELECT * FROM jobs WHERE status IN ('queued','waiting') AND due<=? ORDER BY due,created LIMIT 1",(time.time(),))
        if not rows:
            await asyncio.sleep(.5);continue
        job=rows[0]
        if not store.claim(job['id']):continue
        try:
            result=await gateway.execute(job)
            if job['action']=='reminder':store.reminder_result(job,result)
            else:store.update_job(job['id'],status='succeeded',progress=100,receipt=result,error=None)
        except DeliveryUnknown as exc:store.update_job(job['id'],status='delivery_unknown',error=str(exc))
        except (ConnectionError,TimeoutError) as exc:
            if time.time()-job['created']<86400:
                store.update_job(job['id'],status='waiting',error=str(exc),attempts=job['attempts']+1,due=time.time()+10+secrets.randbelow(8000)/1000)
            else:store.update_job(job['id'],status='failed',error='24 小时内未找到可用设备：'+str(exc))
        except Exception as exc:store.update_job(job['id'],status='failed',error=str(exc))
