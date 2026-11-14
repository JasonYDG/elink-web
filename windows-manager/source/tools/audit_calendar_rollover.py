"""Trace native noon/midnight callbacks and export actual application RAM frames."""
from pathlib import Path
from datetime import datetime
import json,os,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tests'),str(ROOT/'source/backend'),str(ROOT/'source/tools')]
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0
from test_midnight_calendar import NativeMinuteMachine,BASE,FIRMWARE_DIR
from protocol import image_packets
from builtin_gallery import native
from preview_firmware import verify_firmware,export_frame

def state(m):
    return {'date':[m.word(BASE+0xdd98+8),m.word(BASE+0x104dc+28)+1,m.word(BASE+0x104dc+32)+1],
            'hour':m.word(BASE+0x104dc+36),'minute':m.word(BASE+0x104dc+40),'second':m.word(BASE+0x104dc+44),
            'generation':m.status()['display_generation'],'busy':m.status()['busy']}

def frame(m):return bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))

def main():
    for key in ('ELINK_TEST_FIRMWARE_DIR','ELINK_PREVIEW_UPDATE_PACKAGE','ELINK_ROLLOVER_AUDIT_OUT'):
        if not os.environ.get(key):raise SystemExit('Explicit firmware/OTA/new output directory required')
    provenance=verify_firmware(FIRMWARE_DIR,os.environ['ELINK_PREVIEW_UPDATE_PACKAGE'])
    out=Path(os.environ['ELINK_ROLLOVER_AUDIT_OUT']);assert not out.exists();out.mkdir(parents=True)
    records={};images={}
    for mode in ('calendar','photo-calendar'):
        for boundary,hour in (('noon',11),('midnight',23)):
            m=NativeMinuteMachine().at(datetime(2026,11,14,hour,59,37))
            if mode=='photo-calendar':
                source=native('image/calendar/19-wind-and-waves.png')['frame']
                for p in list(image_packets(source,401,128))[:-1]:m.cmd(p)
                m.cmd(b'\x9c\x03');m.finish()
            before=frame(m);old=state(m);flags=[];m.commands.clear()
            def trace(uc,a,size,_):
                if a==BASE+0x2cc4:flags.append(uc.reg_read(UC_ARM_REG_R0))
            hook=m.uc.hook_add(UC_HOOK_CODE,trace);m.tick();m.uc.hook_del(hook)
            if m.status()['busy']:m.finish()
            after=frame(m);new=state(m);assert flags==[128]
            refreshes=sum(c[0]==BASE+0x3c10 and c[1]==0x22 for c in m.commands)
            if boundary=='noon':assert before==after and old['date']==new['date'] and new['generation']==old['generation'] and refreshes==0
            else:
                assert new['date']==[2026,11,15] and new['hour']==0 and new['generation']==old['generation']+1 and refreshes==1
                if mode=='photo-calendar':
                    for plane in (0,4000):assert before[plane+1216:plane+4000]==after[plane+1216:plane+4000]
            name=mode+'-'+boundary
            for suffix,pixels in (('before',before),('after',after)):images[name+'-'+suffix]=export_frame(out,name+'-'+suffix,pixels)
            records[name]={'before':old,'after':new,'native_flags':flags,'display_refreshes':refreshes,'date_change':old['date']!=new['date']}
    proof={**provenance,'cases':records,'frames':images,'native_entry':'0x07fc25c0','geometry':[250,122],
           'native_second_phase_preserved':True,'clock_step_minutes':1,'hardware_boundaries':'SPI, BUSY, ROM services/diagnostic logging are emulated',
           'computer_use':False,'physical_device_access':False,'physical_midnight_tested':False}
    (out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n','utf-8')
    html='''<!doctype html><meta charset="utf-8"><title>午夜跨日核对</title><style>body{font:16px sans-serif}img{display:block;width:250px!important;height:122px!important;max-width:none;image-rendering:pixelated}figure{margin:24px 0}</style><h1>原生分钟回调 · 午夜与中午</h1><p>编译固件实际执行0x07fc25c0分钟入口。中午与午夜都传入旧0x80标记；新版只在日期变化时自动更新日历，保留手动切页重绘。下图来自同一交付应用的模拟RAM，250×122无缩放、补画或浏览器绘字。秒相位37不改写，所以例子跨至00:00:37；不承诺硬件精确零秒唤醒或实屏光学结果。</p><p><a href="proof.json">原生字段、刷新次数及固件来源</a></p>'''
    for name,data in records.items():
        html+=f'<h2>{name}</h2><p>原生标记{data["native_flags"]}；刷屏{data["display_refreshes"]}次。</p>'
        for suffix in ('before','after'):html+=f'<figure>{suffix}<img src="{name}-{suffix}.png" width="250" height="122"><a href="{name}-{suffix}.bwr.bin">8000字节点阵</a></figure>'
    (out/'index.html').write_text(html,'utf-8')
    print(json.dumps({'firmware_id':provenance['firmware_id'],'cases':records},ensure_ascii=False))

if __name__=='__main__':main()
