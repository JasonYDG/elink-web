"""Record the actual compiled clock's SPI mask, plus native UI glyph diagnostics."""
from pathlib import Path
from datetime import date
import json,os,shutil,struct,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tests'),str(ROOT/'source/backend'),str(ROOT/'source/tools')]
from PIL import Image
from test_product_ui import ProductMachine,BASE
from test_clock_balanced import polarity_frames
from test_font_readability import native_cells
from bitmap_fonts import ui_cjk_cells,font_meta
from audit_solar_terms import fixture
from preview_firmware import export_frame,verify_firmware

def main():
    for key in ('ELINK_TEST_FIRMWARE_DIR','ELINK_PREVIEW_UPDATE_PACKAGE','ELINK_STROKE_AUDIT_OUT'):
        if not os.environ.get(key):raise SystemExit('Explicit firmware, OTA and new audit paths required')
    provenance=verify_firmware(Path(os.environ['ELINK_TEST_FIRMWARE_DIR']),os.environ['ELINK_PREVIEW_UPDATE_PACKAGE'])
    out=Path(os.environ['ELINK_STROKE_AUDIT_OUT']);assert not out.exists();out.mkdir(parents=True)
    records={};modes={}
    for mode in (1,2):
        m=ProductMachine();m.cmd(bytes([0x94,mode,60]));before=fixture(m,date(2026,11,14),0)
        assert m.status()['clock_refresh_minutes']==1
        m.stream.clear();m.uc.mem_write(BASE+0x104dc+40,struct.pack('<I',56));m.run(BASE+0x2cc4)
        after=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
        mask=bytes(m.stream[:4000]);assert len(m.stream)==8070
        assert mask==bytes(255^(a^b) for a,b in zip(before[:4000],after[:4000]))
        assert before[4000:]==after[4000:]==bytes(4000)
        assert bytes(m.stream[4000:8000])==bytes((255^a)&b for a,b in zip(mask,after[:4000]))
        assert m.stream[8007:8014]==[0]*7
        stages=[]
        def save_stage(name):
            for suffix,raw in (('bw',m.stream[:4000]),('rr',m.stream[4000:8000]),('lut',m.stream[8000:])):
                (out/(name+'.'+suffix+'.bin')).write_bytes(bytes(raw))
            stages.append({'name':name,'bw_bytes':4000,'rr_bytes':4000,'lut_bytes':70,'unchanged_pixel_lut1_all_zero_vss':m.stream[8007:8014]==[0]*7})
        save_stage(f'mode{mode}-balanced')
        m.stream.clear();m.run(BASE+0x4208);assert m.status()['busy'] and m.status()['display_generation']==1
        changed=bytes(a^b for a,b in zip(before[:4000],after[:4000]))
        black=bytes(v&(255^b) for v,b in zip(changed,after[:4000]))
        assert len(m.stream)==8070 and bytes(m.stream[:4000])==mask
        assert bytes(m.stream[4000:8000])==bytes(v&b for v,b in zip(changed,after[:4000]))
        assert not any(m.stream[8007:8014]) and not any(m.stream[8021:8028])
        save_stage(f'mode{mode}-compensation');m.run(BASE+0x4208)
        if mode==2:records['black-boost-mask']=export_frame(out,'black-boost-mask',bytes(255^v for v in black)+black)
        assert m.status()['display_generation']==2 and not m.status()['busy']
        modes[mode]={'driven_pixels':sum(8-v.bit_count() for v in mask),'former_rectangle_pixels':103*72,
                     'native_update_command':m.update_sequence(),'unchanged_background_neutral':True,'stages':stages,
                     'native_voltage_and_phase_timing_unchanged':True,'generation_commits':1}
        if mode==1:
            records['clock-before']=export_frame(out,'clock-before',before)
            records['clock-after']=export_frame(out,'clock-after',after)
            records['stroke-mask']=export_frame(out,'stroke-mask',mask+bytes(255^v for v in mask))
        else:assert records['clock-before']['frame_sha256']==export_frame(out,'fast-before',before)['frame_sha256']
    sequences={}
    for mode in (1,2):
        m=ProductMachine();m.cmd(bytes([0x94,mode,60]));before=fixture(m,date(2026,11,14),0)
        records[f'mode{mode}-step0']=export_frame(out,f'mode{mode}-step0',before);steps=[]
        for step,minute in enumerate((56,55,56),1):
            m.stream.clear();m.uc.mem_write(BASE+0x104dc+40,struct.pack('<I',minute));m.run(BASE+0x2cc4)
            target=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000));first=bytes(m.stream)
            m.stream.clear();m.run(BASE+0x4208);second=bytes(m.stream);assert m.status()['busy']
            assert len(first)==len(second)==8070 and first[:8000]==second[:8000]
            changed=bytes(a^b for a,b in zip(before[:4000],target[:4000]))
            assert first[:4000]==bytes(255^v for v in changed)
            white=bytes(v&b for v,b in zip(changed,target[:4000]))
            assert first[4000:8000]==white
            if mode==2 and step==2:records['white-erase-mask']=export_frame(out,'white-erase-mask',bytes(255^v for v in white)+white)
            lut=second[8000:];assert lut[7:14]+lut[21:28]==bytes(14)
            m.run(BASE+0x4208);assert not m.status()['busy'] and m.status()['display_generation']==step+1
            records[f'mode{mode}-step{step}']=export_frame(out,f'mode{mode}-step{step}',target)
            steps.append({'minute':minute,'generation':step+1,'phase_count':2,
                          'new_black_pixels':sum((v&(255^b)).bit_count() for v,b in zip(changed,target[:4000])),
                          'removed_pixels':sum(v.bit_count() for v in white),'extra_black_polarity_frames':polarity_frames(lut,0),
                          'extra_white_polarity_frames':polarity_frames(lut,2),'unchanged_pixel_lut1_all_zero_vss':True})
            before=target
        sequences[mode]=steps
    glyphs=native_cells(m.b,0xa48c,18);hints=ui_cjk_cells();chars=sorted(hints)
    for i in range(0,len(chars),78):
        sheet=Image.new('RGB',(250,122),'white')
        for j,ch in enumerate(chars[i:i+78]):
            assert glyphs[ch].tobytes()==hints[ch].tobytes()
            sheet.paste('black',(4+j%13*18,4+j//13*19),glyphs[ch])
        sheet.save(out/f'ui-glyphs-{i//78+1:02}.png')
    shutil.copy2(ROOT/'source/fonts/ui-cjk-18.json',out/'ui-cjk-18.json')
    proof={**provenance,'fixture':'2026-11-14 06:55 -> 06:56; real lunar fields; simulated ADC100%',
           'clock_refresh_minutes':1,'modes':modes,'sequences':sequences,'frames':records,'geometry':[250,122],'native_cjk_glyphs':90,
           'cjk_source':font_meta('ui_cjk_18'),'photo_digit_source':font_meta('terminus_large'),
           'photo_plain_zero_source':'O bitmap from the same Terminus32 font',
           'diagnostics':['stroke-mask is the actual SPI drive-mask diagnostic, not a device page',
                          'ui-glyphs sheets contain compiled font masks, not a device page'],
           'clock_partial_border_register':'0xc0','full_border_register':'0x05',
           'register_execution_proof':'border-after.json (separate native-init trace)',
           'zero_lut_is_not_border_hiz':True,'computer_use':False,'physical_device_access':False,'optical_tested':False}
    (out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n','utf-8')
    (out/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>笔画差分与字形核对</title>
<style>body{font:16px sans-serif}img{display:block;width:250px!important;height:122px!important;max-width:none;image-rendering:pixelated}figure{margin:24px 0}</style>
<h1>边框高阻与连续局刷 · 250×122原始点阵</h1><p>此用例选择每分钟更新，日常默认间隔仍为5分钟。1.5.26字形采用分离斜角七段点阵，补偿流程保持1.5.25。经用户单独授权，时钟局刷两个阶段将边框0x3C设为0xC0高阻，完整刷新及其他页面恢复原生0x05。LUT1全零代表源电平VSS，不能视为边框高阻。红色遮罩标记变化像素，是诊断图；白色表示未选中，不是设备页面。PNG来自编译RAM，不模拟电压、色深、残影或墨水显影。原生初始化代码、扫描、供电和脉冲参数不改。<a href="border-after.json">实际寄存器执行记录</a></p>
<figure>刷新前 06:55<img src="clock-before.png" width="250" height="122"></figure>
<figure>刷新后 06:56<img src="clock-after.png" width="250" height="122"></figure>
<figure>驱动遮罩诊断<img src="stroke-mask.png" width="250" height="122"></figure>
<figure>加深模式：仅新黑笔画<img src="black-boost-mask.png" width="250" height="122"></figure>
<figure>连续变化56→55：补擦消失笔画<img src="white-erase-mask.png" width="250" height="122"></figure>
<h2>平衡模式连续55→56→55→56</h2>
<img src="mode1-step0.png" width="250" height="122"><img src="mode1-step1.png" width="250" height="122"><img src="mode1-step2.png" width="250" height="122"><img src="mode1-step3.png" width="250" height="122">
<h2>加深模式连续55→56→55→56</h2>
<img src="mode2-step0.png" width="250" height="122"><img src="mode2-step1.png" width="250" height="122"><img src="mode2-step2.png" width="250" height="122"><img src="mode2-step3.png" width="250" height="122">
<p>下方是90个原生界面汉字的编译字形拼排，属于诊断表，不是设备页面。</p>
<img src="ui-glyphs-01.png" width="250" height="122"><img src="ui-glyphs-02.png" width="250" height="122">
<p><a href="proof.json">固件、遮罩与字形来源</a></p>''','utf-8')
    print(json.dumps({'firmware_id':provenance['firmware_id'],'modes':modes},ensure_ascii=False))

if __name__=='__main__':main()
