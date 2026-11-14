"""Export all 24 terms through the compiled clock/calendar/photo-calendar paths."""
from pathlib import Path
from datetime import date,datetime,timedelta
import hashlib,json,os,shutil,struct,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tests'),str(ROOT/'source/backend'),str(ROOT/'source/tools')]
from PIL import Image
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_SP
from test_firmware import BASE,STATE,END,FIRMWARE_DIR
from test_product_ui import ProductMachine,frame_matches
from test_photo_calendar_155 import Photo155
from test_font_readability import native_cells
from test_solar_term_fonts import regions
from bitmap_fonts import text_mask,solar_term_cells,font_meta
from photo_calendar import TERMS,TERM_SECONDS,next_term,date_column
from lunar import lunar_fields
from preview_firmware import export_frame,verify_firmware
from builtin_gallery import native
from protocol import image_packets


def fixture(m,day,mode):
    ly,lm,ld=lunar_fields(day)
    for off,value in ((8,day.year),(12,(day.weekday()+1)%7),(16,ly),(20,lm),(24,ld-1)):
        m.uc.mem_write(BASE+0xdd98+off,struct.pack('<I',value))
    for off,value in ((28,day.month-1),(32,day.day-1),(36,6),(40,55)):
        m.uc.mem_write(BASE+0x104dc+off,struct.pack('<I',value))
    m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1706));m.uc.mem_write(STATE+27,b'\x01');m.uc.mem_write(STATE+7,bytes([mode]))
    m.uc.reg_write(UC_ARM_REG_R0,128);m.uc.reg_write(UC_ARM_REG_LR,END|1)
    m.uc.emu_start(BASE+0x2cc5,END,count=2500000)
    assert m.uc.reg_read(UC_ARM_REG_PC)==END and m.uc.reg_read(UC_ARM_REG_SP)==BASE+0x1d000
    result=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000));m.finish();return result


def main():
    if not os.environ.get('ELINK_TEST_FIRMWARE_DIR') or not os.environ.get('ELINK_PREVIEW_UPDATE_PACKAGE') or not os.environ.get('ELINK_TERM_AUDIT_OUT'):
        raise SystemExit('Explicit firmware, OTA and new audit output paths required')
    provenance=verify_firmware(FIRMWARE_DIR,os.environ['ELINK_PREVIEW_UPDATE_PACKAGE'])
    out=Path(os.environ['ELINK_TERM_AUDIT_OUT']);assert not out.exists() or not any(out.iterdir());out.mkdir(exist_ok=True,parents=True)
    names=TERMS;year=2026;yy=year-2020;leap=(yy-1)//4+1
    days=[date(year,1,1)+timedelta(days=(451804+20950*yy-leap*86400+seconds)//86400) for seconds in TERM_SECONDS]
    machines={'clock':ProductMachine(),'calendar':ProductMachine()}
    photo=Photo155().ready(days[0]);source=native('image/calendar/19-wind-and-waves.png')['frame']
    for packet in list(image_packets(source,620,128))[:-1]:photo.cmd(packet)
    photo.cmd(b'\x9c\x03');photo.finish();machines['photo-calendar']=photo
    cases={}
    for i,(term,day) in enumerate(zip(names,days)):
        assert next_term(day)==(term,'今日')
        for mode,m in machines.items():
            frame=fixture(m,day,{'clock':0,'calendar':3,'photo-calendar':6}[mode])
            x,y=(244-text_mask(term+'今日',18).width,103) if mode=='clock' else (171,85) if mode=='calendar' else (212-(36+text_mask('今日',12).width)//2,101)
            assert frame_matches(frame,term,18,x,y),(term,mode,'Term glyphs must be complete and exact')
            if mode=='photo-calendar':
                expected=date_column(day)['frame']
                for plane in (0,4000):
                    assert frame[plane:plane+1216]==expected[plane:plane+1216],(term,'date column')
                    assert frame[plane+1216:plane+4000]==source[plane+1216:plane+4000],(term,'left artwork preserved')
            name=f'{i+1:02}-{mode}';record=export_frame(out,name,frame);record.update(term=term,date=day.isoformat(),mode=mode,label_position=[x,y],label_pixels_checked=36*18)
            cases[name]=record
        print(f'{i+1:02}/24 {term}: 3 compiled250x122 modes verified',flush=True)
    assert len(cases)==72
    current=native_cells(machines['clock'].b,0xa48c,18)
    before=native_cells((ROOT/'build/firmware-1.5.19-final/elink-bwr-1.5.19-app.bin').read_bytes(),0xa48c,18)
    all_pixels={(x,y) for y in range(18) for x in range(18)};records={};sheet=Image.new('RGB',(250,122),'white')
    for i,term in enumerate(names):
        for j,ch in enumerate(term):sheet.paste('black',(7+(i%5)*50+j*18,2+(i//5)*24),current[ch])
    sheet.save(out/'glyph-table-250x122.png')
    for ch in sorted(set(''.join(names))):
        mask=current[ch];assert mask.tobytes()==solar_term_cells()[ch].tobytes()
        ink={(x,y) for x,y in all_pixels if mask.getpixel((x,y))};old={(x,y) for x,y in all_pixels if before[ch].getpixel((x,y))}
        holes=lambda points:[g for g in regions(all_pixels-points) if not any(x in (0,17) or y in (0,17) for x,y in g)]
        records[ch]={'checked':True,'old_ink':len(old),'new_ink':len(ink),'old_stroke_components':len(regions(old,True)),'new_stroke_components':len(regions(ink,True)),'new_continuous_components':len(regions(ink)),'old_counters':len(holes(old)),'new_counters':len(holes(ink)),'ink_bounds':list(mask.getbbox()),'source':font_meta('solar_terms_18')['local_sha256'],'dense_details_may_be_one_pixel':True}
        assert records[ch]['new_continuous_components']==records[ch]['new_stroke_components']
    (out/'glyph-audit.json').write_text(json.dumps({'format':'ELINK-solar-audit-1','terms':names,'glyphs':records,'count':27,'sheet':'compiled native glyph diagnostic; not a device page','optical_tested':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copy2(ROOT/'source/fonts/solar-terms-18.json',out/'solar-terms-18.json')
    html='<!doctype html><meta charset="utf-8"><title>24节气原始点阵核对</title><style>body{font:16px sans-serif}img{display:block;width:250px!important;height:122px!important;max-width:none;image-rendering:pixelated}figure{margin:24px 0}</style><h1>24节气 · 250×122原始点阵</h1><p>字形表取自交付应用编译字表，供逐字检查；下方72张图来自同一应用的时钟、月历和图片日历完整绘制路径。全部原始尺寸，无缩放、平滑或浏览器绘字。模拟器不代表实体墨水显影。</p><img src="glyph-table-250x122.png" width="250" height="122"><p><a href="glyph-audit.json">27字检查数据</a> · <a href="proof.json">固件与逐图来源</a></p>'
    for name,meta in cases.items():
        html+=f'<figure><figcaption>{meta["term"]} · {meta["date"]} · {meta["mode"]}</figcaption><img src="{name}.png" width="250" height="122"><a href="{name}.bwr.bin">8000字节点阵</a></figure>'
    (out/'index.html').write_text(html,encoding='utf-8')
    proof={**provenance,'status':'compiled application RAM; hardware unverified','terms':24,'glyphs':27,'frames':72,'visible_geometry':[250,122],'computer_use':False,'physical_device_access':False,'cases':cases}
    (out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('All24 terms /27 glyphs /72 real compiled frames verified.',flush=True)


if __name__=='__main__':main()
