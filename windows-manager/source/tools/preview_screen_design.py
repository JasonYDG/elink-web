"""Export exact compiled-binary frames and the shared host notice renderer."""
import os,sys,struct,json,zlib
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tests'),str(ROOT/'source/backend'),str(ROOT/'source/tools')]
from test_product_ui import ProductMachine,BASE,STATE,END,FIRMWARE_DIR
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_LR,UC_ARM_REG_PC
from preview_firmware import export_frame,verify_firmware
from lunar import lunar_fields
from render import render
OUT=Path(os.environ.get('ELINK_PREVIEW_OUT',ROOT/'build/native-pixel-preview'))
MAC='18:BC:5A:6B:91:A7'

def native_page(view,day=datetime(2026,11,14,6,55),nl=False,adc=1705):
    m=ProductMachine();m.uc.mem_write(BASE+0x10520,bytes.fromhex(MAC.replace(':',''))[::-1])
    m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',adc))
    if view=='default':m.run(BASE+0x2224)
    else:
        m.cmd(b'\x9f'+bytes([int(nl),int(nl)]))
        ly,lm,ld=lunar_fields(day.date())
        for off,value in ((8,day.year),(12,(day.weekday()+1)%7),(16,ly),(20,lm),(24,ld-1)):
            m.uc.mem_write(BASE+0xdd98+off,struct.pack('<I',value))
        for off,value in ((28,day.month-1),(32,day.day-1),(36,day.hour),(40,day.minute)):
            m.uc.mem_write(BASE+0x104dc+off,struct.pack('<I',value))
        m.uc.mem_write(STATE+27,bytes([1|int(nl)*6]));m.uc.mem_write(STATE+7,bytes([3 if view.startswith('calendar') else 0]))
        m.uc.reg_write(UC_ARM_REG_R0,128);m.uc.reg_write(UC_ARM_REG_LR,END|1)
        m.uc.emu_start(BASE+0x2cc5,END,count=2500000)
        assert m.uc.reg_read(UC_ARM_REG_PC)==END
    return bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))

def reminder_page():
    from protocol import reminder_metadata
    m=ProductMachine();m.draw(day=6,h=8,minute=0,force=128);m.finish();m.cmd(b'\xb3'+struct.pack('<i',28800))
    m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1650))
    for slot,(title,hour) in enumerate((('早餐后服药',9),('晚间散步',18),('夜间服药',22))):
        due=int(datetime(2026,10,6,hour,0).timestamp());frame=render({'kind':'notice','title':title,'body':'日程提醒','footer':'每天 %02u:00'%hour})['frame']
        meta=reminder_metadata(title,{'repeat_mask':127,'utc_offset':28800},large=True)
        m.cmd(bytes([0xb0,slot])+struct.pack('<III',100+slot,due,zlib.crc32(frame)))
        for off in range(0,8000,17):m.cmd(b'\xb1'+struct.pack('<H',off)+frame[off:off+17])
        for off in range(0,156,18):m.cmd(bytes([0xb8,off])+meta[off:off+18])
        m.cmd(b'\xb2'+struct.pack('<I',100+slot))
    m.cmd(b'\xb9');m.finish()
    return bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))

def photo_calendar_page():
    from test_photo_calendar_155 import Photo155
    from builtin_gallery import native
    from protocol import image_packets
    m=Photo155().ready(datetime(2026,11,14).date())
    frame=native('image/calendar/19-wind-and-waves.png')['frame']
    for packet in list(image_packets(frame,55,128))[:-1]:m.cmd(packet)
    m.cmd(b'\x9c\x03');m.finish()
    return bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))

def notice_page():
    from protocol import image_packets
    m=ProductMachine();m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1705))
    frame=render({'kind':'notice','title':'任务提醒','body':'你的日程','footer':'2026-11-14 星期六'},battery_percent=100)['frame']
    for packet in image_packets(frame,56,128):m.cmd(packet)
    m.finish()
    return bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))

def main():
    if not os.environ.get('ELINK_TEST_FIRMWARE_DIR') or not os.environ.get('ELINK_PREVIEW_UPDATE_PACKAGE'):
        raise SystemExit('Set ELINK_TEST_FIRMWARE_DIR and ELINK_PREVIEW_UPDATE_PACKAGE explicitly; no legacy build fallback')
    provenance=verify_firmware(FIRMWARE_DIR,os.environ['ELINK_PREVIEW_UPDATE_PACKAGE'])
    if OUT.exists() and any(OUT.iterdir()):raise SystemExit('Use a new empty output directory to exclude stale previews')
    OUT.mkdir(parents=True,exist_ok=True)
    frames={name:native_page(name) for name in ('default','clock','calendar')}
    frames['clock-netherlands']=native_page('clock',datetime(2026,10,5,23,55),True)
    frames['calendar-six-rows']=native_page('calendar',datetime(2026,8,26,6,55))
    frames['calendar-leap-month']=native_page('calendar',datetime(2025,8,10,6,55))
    frames['reminders']=reminder_page()
    frames['photo-calendar']=photo_calendar_page()
    frames['notice']=notice_page()
    records={}
    for name,frame in frames.items():
        records[name]=export_frame(OUT,name,frame)
    html='<!doctype html><meta charset="utf-8"><title>250×122 原始点阵</title><style>body{font:16px sans-serif}figure{margin:24px 0}img{display:block;width:250px!important;height:122px!important;max-width:none;image-rendering:pixelated}</style><h1>250×122 原始点阵</h1><p>每张 PNG 都是固件模拟器帧缓冲逐位解码。无缩放、无补画、无字体重绘。显示器物理尺寸和墨水显影不由此模拟。</p>'
    for name in frames:
        html+=f'<figure><figcaption>{name} · 250×122 · 1×</figcaption><img src="{name}.png" width="250" height="122" alt="{name}"><a href="{name}.png">原始 PNG</a> · <a href="{name}.bwr.bin">8000 字节点阵</a></figure>'
    (OUT/'index.html').write_text(html,encoding='utf-8')
    proof={'status':'compiled application RAM; optical result unverified',**provenance,'stored_geometry':[128,250],
           'visible_geometry':[250,122],'unused_source_bits_per_gate':6,'simulation_only':True,'physical_device_access':False,
           'default_clock_calendar_fixture':'2026-11-14 06:55, battery 100%; reminders use 2026-10-06 fixture',
           'pages':records}
    (OUT/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(proof,ensure_ascii=False))
if __name__=='__main__':main()
