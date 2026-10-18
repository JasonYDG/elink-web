"""Export exact compiled-binary frames and the shared host notice renderer."""
import os,sys,struct,json,hashlib,io,calendar,zlib
from pathlib import Path
from datetime import datetime
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('ELINK_TEST_FIRMWARE_DIR',str(ROOT/'build/firmware-1.5.2'))
sys.path[:0]=[str(ROOT/'source/tests'),str(ROOT/'source/backend'),str(ROOT/'source/tools')]
from test_product_ui import ProductMachine,BASE,STATE,END,FIRMWARE_DIR
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_LR,UC_ARM_REG_PC
from preview_firmware import frame_image
from lunar import lunar_fields
from render import quantize,render
from bitmap_fonts import paint
OUT=Path(os.environ.get('ELINK_PREVIEW_OUT',ROOT/'source/opendesign/mockups/elink-screen-design'))
MAC='18:BC:5A:6B:91:A7'

def native_page(view,day=datetime(2026,10,6,6,55),nl=False):
    m=ProductMachine();m.uc.mem_write(BASE+0x10520,bytes.fromhex(MAC.replace(':',''))[::-1])
    m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1650))
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

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    frames={name:native_page(name) for name in ('default','clock','calendar')}
    frames['clock-netherlands']=native_page('clock',datetime(2026,10,5,23,55),True)
    frames['calendar-six-rows']=native_page('calendar',datetime(2026,8,26,6,55))
    frames['calendar-leap-month']=native_page('calendar',datetime(2025,8,10,6,55))
    frames['reminders']=reminder_page()
    frames['notice']=render({'kind':'notice','title':'任务提醒','body':'你的日程','footer':'2026-10-06 星期二'},battery_percent=67)['frame']
    records={}
    for name,frame in frames.items():
        im=frame_image(frame);r=quantize(im)
        assert r['frame']==frame
        (OUT/f'{name}.png').write_bytes(r['png']);(OUT/f'{name}.bwr.bin').write_bytes(frame)
        im.resize((1000,488),Image.Resampling.NEAREST).save(OUT/f'{name}-4x.png')
        records[name]={'sha256':r['sha256'],'frame_bytes':len(frame),'png_matches_frame':True,'red_pixels':r['red_pixels']}
        if name in ('default','clock','calendar','reminders'):
            (ROOT/'source/opendesign/mockups/elink-manager'/f'page-{name}.png').write_bytes(r['png'])
            (FIRMWARE_DIR/({'default':'boot'}.get(name,name)+'-preview.png')).write_bytes(r['png'])
    sheet=Image.new('RGB',(1076,654),(245,240,231))
    for i,(name,label) in enumerate((('default','默认界面'),('clock','时钟界面'),('calendar','日历界面'),('notice','任务提醒'))):
        x,y=24+i%2*528,24+i//2*321
        paint(sheet,label,(x,y),24);sheet.paste(frame_image(frames[name]).resize((500,244),Image.Resampling.NEAREST),(x,y+41))
    sheet.save(OUT/'all-pages.png')
    meta=json.loads((FIRMWARE_DIR/'manifest.json').read_text('utf-8'))
    proof={'status':'compiled binary + shared host renderer; optical result unverified','version':meta['version'],'firmware_id':meta['firmware_id'],'font':meta['font_sources'],'sample_date':'2026-10-06','sample_mac':MAC,'sample_battery_percent':67,'clock_default_refresh_minutes':5,'pages':records}
    (OUT/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(proof,ensure_ascii=False))
if __name__=='__main__':main()
