"""ELK1 overlay protocol on HMCLOCK FF00/FF01. Never sends OTA/OTP writes."""
import datetime,struct
SERVICE='0000ff00-0000-1000-8000-00805f9b34fb'
CONTROL='0000ff01-0000-1000-8000-00805f9b34fb'
VOLTS='0000ff02-0000-1000-8000-00805f9b34fb'
PLANE_BYTES=4000

def decode_battery(data):
    # FF02 is the native ADC voltage, little-endian mV, not a percentage.
    if len(data)!=2:raise ValueError('电压特征应为2字节')
    mv=int.from_bytes(data,'little')
    if not 1500<=mv<=3600:raise ValueError('设备电压值无效：'+str(mv))
    a=(mv*128+224)//225 # Invert native (adc*225)>>7; no host battery default.
    if a>1705:percent=100
    elif a>1584:percent=28+(a-1584)*72//121
    elif a>1360:percent=4+(a-1360)*24//224
    elif a>1136:percent=(a-1136)*4//224
    else:percent=0
    return {'battery_mv':mv,'battery_percent':percent,'battery_source':'FF02_voltage_estimate'}

def sync_packet(now=None,timezone='local'):
    from clock_time import wall_time
    t=wall_time(timezone,now)
    if not 2020<=t.year<=2051: raise ValueError('Clock calendar supports 2020..2051')
    # The firmware stores lunar-calendar counters; use its existing table.
    # Reference table shared with upstream web controller, extracted by build tooling.
    from lunar import lunar_fields
    ly,lm,ld=lunar_fields(t.date())
    return bytes([0x91,t.year&255,t.year>>8,t.month-1,t.day,t.hour,t.minute,t.second,
                  (t.weekday()+1)%7,ly,lm,ld])

def decode_status(data):
    if len(data)!=32 or data[:5]!=b'ELK1\x01':
        raise ValueError('当前固件未返回 ELK1 能力；仅可使用原版校时。')
    firmware=data[28:32].hex()
    return {'protocol':1,'photo_calendar':firmware in ('d78aa415','6c3279f4','14271ec2'),'photo_calendar_commit':firmware in ('6c3279f4','14271ec2'),'photo_calendar_native_digits':firmware=='14271ec2','max_image_payload':128 if firmware in ('d78aa415','6c3279f4','14271ec2') else 17,'mode':data[5],'full_every':data[6],
            'display_mode':data[7],'busy':bool(data[8]),'error':data[9],
            'received':struct.unpack_from('<H',data,10)[0],
            'transfer_id':struct.unpack_from('<H',data,12)[0],
            'sum16':struct.unpack_from('<H',data,14)[0],
            'expected_sum16':struct.unpack_from('<H',data,16)[0],
            'display_generation':struct.unpack_from('<H',data,18)[0],
            'advertise_window_seconds':data[21],'advertise_every_minutes':data[22],
            'clock_refresh_minutes':data[24],'time_initialized':bool(data[27]&1),'firmware_id':data[28:32].hex(),
            'clock_timezone':'Europe/Amsterdam' if data[27]&2 else 'local','clock_summer_time':bool(data[27]&4)}

def decode_ui_capabilities(data):
    # Older ELK1 ignores 9D and leaves its 32-byte status value in FF01.
    if len(data)==32 and data[:5]==b'ELK1\x01':return {}
    if len(data)!=8 or data[:5]!=b'ELUI\x01' or data[6]&224 or (data[6]&2 and not data[6]&1) or (data[6]&8 and not data[6]&4) or (data[6]&16 and not data[6]&8) or data[7]:
        raise ValueError('设备返回了无法识别的显示能力')
    return {'embedded_calendar':bool(data[5]&1),'minute_region_refresh':bool(data[5]&2),'bold_clock':bool(data[5]&4),'global_clock_refresh':bool(data[5]&8),'quiet_sync':bool(data[5]&16),'default_page':bool(data[5]&32),'timezone_clock':bool(data[5]&64),'offline_reminders':bool(data[5]&128),'reminder_summary':bool(data[6]&1),'reminder_large_text':bool(data[6]&2),**({'offline_album':True,'photo_calendar':True,'photo_calendar_commit':True,'photo_calendar_native_digits':True,'max_image_payload':128} if data[6]&4 else {}),**({'photo_calendar_wide':True,'album_minute_tick':True} if data[6]&8 else {}),**({'album_capacity':7,'album_readback':True} if data[6]&16 else {})}

def reminder_options(value=None):
    value={} if value is None else value
    if not isinstance(value,dict) or set(value)-{'repeat_mask','check_minutes','duration_minutes','utc_offset'}:raise ValueError('提醒策略不合法')
    result={'repeat_mask':0,'check_minutes':1,'duration_minutes':5,'utc_offset':int(datetime.datetime.now().astimezone().utcoffset().total_seconds()),**value}
    if any(type(v)!=int for v in result.values()) or not 0<=result['repeat_mask']<=127 or result['check_minutes'] not in (1,5,15,60) or not 0<=result['duration_minutes']<=120 or not -50400<=result['utc_offset']<=50400:raise ValueError('重复星期、检查间隔、持续时间或时区不合法')
    return result

def reminder_metadata(title,options,large=False):
    import zlib
    from bitmap_fonts import text_mask
    config=reminder_options(options);height,width,stride=(16,72,9) if large else (12,96,12)
    mask=text_mask(title,height)
    if large and mask.width>width:
        while title and text_mask(title+'…',height).width>width:title=title[:-1]
        mask=text_mask(title+'…',height)
    bitmap=bytearray(144)
    for y in range(min(mask.height,height)):
        for x in range(min(mask.width,width)):
            if mask.getpixel((x,y)):bitmap[y*stride+x//8]|=128>>(x%8)
    data=bytes([166 if large else 165,config['repeat_mask'],config['check_minutes'],config['duration_minutes']])+struct.pack('<i',config['utc_offset'])+bitmap
    return data+struct.pack('<I',zlib.crc32(data))

def decode_reminder_runtime(data):
    if len(data)!=20 or data[:4]!=b'ERM2' or data[4]>127 or data[5] not in (1,5,15,60) or data[6]>120 or data[7] not in (165,166,255):raise ValueError('提醒运行策略无效')
    return {'repeat_mask':data[4],'check_minutes':data[5],'duration_minutes':data[6],'metadata_ready':data[7] in (165,166),'next_due':struct.unpack_from('<I',data,8)[0],'last_due':struct.unpack_from('<I',data,12)[0],'utc_offset':struct.unpack_from('<i',data,16)[0]}

def decode_reminder_slot(data):
    if len(data)!=24 or data[:5]!=b'ERM1\x01' or data[5]>=8 or data[6] not in (255,254,252,248) or data[7]&14 or data[7]>>4>8 or data[22]>=8 or data[23]>1 or struct.unpack_from('<H',data,20)[0]>8000:raise ValueError('提醒存储返回无效')
    return {'slot':data[5],'state':data[6],'writing':bool(data[7]&1),'last_slot':(data[7]>>4)-1,
            'token':struct.unpack_from('<I',data,8)[0],'due':struct.unpack_from('<I',data,12)[0],
            'crc32':struct.unpack_from('<I',data,16)[0],'received':struct.unpack_from('<H',data,20)[0],'active_slot':data[22],'clock_ready':bool(data[23])}

def timing_packet(refresh,advertise,window):
    if any(type(x)!=int for x in [refresh,advertise,window]) or not(1<=refresh<=60 and 1<=advertise<=240 and (window==0 or 10<=window<=120)):
        raise ValueError('刷新 1..60 分钟，广播间隔 1..240 分钟；持续可发现或窗口 10..120 秒')
    return bytes([0x99,refresh,advertise,window])

def policy_packet(mode,every):
    if type(mode)!=int or type(every)!=int or mode not in (0,1,2) or not 1<=every<=60:
        raise ValueError('刷新模式 0..2，全刷间隔 1..60 次')
    return bytes([0x94,mode,every])

def image_packets(frame,transfer_id,payload_bytes=17):
    if len(frame)!=8000: raise ValueError('BWR frame requires exactly 8000 bytes')
    if type(payload_bytes)!=int or not 1<=payload_bytes<=128:raise ValueError('像素包大小须为1..128字节')
    yield b'\x95'+struct.pack('<HH',transfer_id,sum(frame)&65535)
    for off in range(0,len(frame),payload_bytes):
        yield b'\x96'+struct.pack('<H',off)+frame[off:off+payload_bytes]
    yield b'\x97'+struct.pack('<H',transfer_id)


def decode_album(data):
    import zlib
    if len(data)==64 and data[:5]==b'ELA1\x03':
        if data[5]>1 or data[6]>1 or data[8]>1 or data[9]>7 or data[7] not in (*range(7),255):raise ValueError('设备未返回有效图库状态')
        progress=struct.unpack_from('<H',data,10)[0];c=data[12:];count=c[14];flags=c[15];minutes=struct.unpack_from('<H',c,12)[0]
        if data[8] and progress>32:raise ValueError('图库写入进度无效')
        if not data[5] and any(c):raise ValueError('空图库状态不一致')
        if data[5] and (c[:4]!=b'ELG2' or c[51]!=254 or count>7 or flags>7 or not 60<=minutes<=10080 or any(x>84 for x in c[44:51]) or (flags&4 and not count) or zlib.crc32(c[:8]+c[12:51])!=struct.unpack_from('<I',c,8)[0]):raise ValueError('图库配置校验失败')
        return {'protocol_version':3,'capacity':7,'save_step':progress if data[8] else 0,'has_config':bool(data[5]),'running':bool(data[6]),'index':data[7],'writing':bool(data[8]),'staged_count':data[9],'elapsed_minutes':0 if data[8] else progress,'sequence':struct.unpack_from('<I',c,4)[0],'count':count,'mode':flags&1,'interval_minutes':minutes,'crc32':list(struct.unpack_from('<7I',c,16))[:count],'photo_x':list(c[44:44+count]),'enabled':bool(flags&4)}
    if len(data)!=52 or data[:4]!=b'ELA1' or data[4] not in (1,2) or data[5]>1 or data[6]>1 or data[8]>1 or data[9]>4 or data[7] not in (0,1,2,3,255):
        raise ValueError('设备未返回有效图库状态')
    progress=struct.unpack_from('<H',data,10)[0]
    if data[4]==2 and data[8] and progress>32:raise ValueError('图库写入进度无效')
    c=data[12:]
    if not data[5] and any(c):raise ValueError('空图库状态不一致')
    count,mode=c[14:16];minutes=struct.unpack_from('<H',c,12)[0]
    if data[5] and (c[:4]!=b'ELG1' or c[38]!=254 or count>4 or mode>1 or c[36]>1 or c[37]>1 or not 60<=minutes<=10080 or any(x>84 for x in c[32:36]) or (c[37] and not count) or zlib.crc32(c[:8]+c[12:38])!=struct.unpack_from('<I',c,8)[0]):
        raise ValueError('图库配置校验失败')
    return {'protocol_version':data[4],'capacity':4,'save_step':progress if data[4]==2 and data[8] else 0,
            'has_config':bool(data[5]),'running':bool(data[6]),'index':data[7],'writing':bool(data[8]),'staged_count':data[9],
            'elapsed_minutes':0 if data[4]==2 and data[8] else progress,'sequence':struct.unpack_from('<I',c,4)[0],
            'count':count,'mode':mode,'interval_minutes':minutes,'crc32':list(struct.unpack_from('<4I',c,16))[:count],
            'photo_x':list(c[32:32+count]),'enabled':bool(c[37])}
