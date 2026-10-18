"""Bounded C patch and native-format bold font; only pinned baseline regions change."""
from pathlib import Path
import struct,subprocess,hashlib,sys,string,re

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from bitmap_fonts import native_font
from module_build import load_modules

# The boot title is an asset; no 18px caller uses the former uppercase I glyph.
REQUIRED='0123456789BWRx. :/'+'农历闰月年今日天后星期一二三四五六七八九十初廿正冬腊小寒大立春雨水惊蛰分清明谷夏满芒种至暑秋处白露霜降雪荷兰甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥鼠牛虎兔龙蛇马羊猴鸡狗猪任务'
# Only small-font callers: MAC, version, battery, lunar date and reminder labels.
SMALL_REQUIRED='0123456789ABCDEFV. :/%-'+'闰月第周一二三四五六七八九十初廿正冬腊今日天后任务提醒无项待已过时另有'

# Calendar day digits sit in the tail of the main-font region, before the native 66px clock digits.
DAYS=0xc2a0
DATE=0x90a4
PHOTO_DAYS=0xb780

def compressed_font(raw,bits):
    """Preserve native metrics/index and losslessly bit-pack alternating runs."""
    from itertools import groupby
    count=struct.unpack_from('<H',raw)[0];limit=(1<<bits)-1
    table=bytearray(raw[:2+4*count]);data=bytearray()
    for i in range(count):
        code,off=struct.unpack_from('<HH',raw,2+4*i)
        struct.pack_into('<HH',table,2+4*i,code,len(table)+len(data))
        data.extend(raw[off:off+5]);w,h=raw[off+1:off+3];stride=(w+7)//8
        pixels=[bool(raw[off+5+y*stride+x//8]&(128>>(x%8))) for y in range(h) for x in range(w)]
        zeros=0;values=[]
        for bit,group in groupby(pixels):
            length=len(list(group))
            if not bit:
                while length>limit:values.extend((limit,0));length-=limit
                zeros=length
            else:
                while length>limit:values.extend((zeros,limit));zeros=0;length-=limit
                values.extend((zeros,length));zeros=0
        if zeros:values.extend((zeros,0))
        packed=[(v>>j)&1 for v in values for j in range(bits)]
        encoded=bytes(sum(packed[j+k]<<k for k in range(min(8,len(packed)-j))) for j in range(0,len(packed),8))
        decoded=[];bit=0
        for i in range(len(values)):
            n=sum(((encoded[(bit+j)//8]>>((bit+j)%8))&1)<<j for j in range(bits));bit+=bits
            decoded.extend([bool(i&1)]*n)
        assert decoded==pixels
        data.extend(encoded)
    return bytes(table+data)

def photo_digits():
    return compressed_font(native_font('0123456789',44),4)

def clock_digits(app):
    raw=compressed_font(app[0xc3c4:0xd2b0],5)
    assert len(raw)==0xc8a4-0xc3c4, 'Clock font must end before album code'
    return raw

def bold_font(app):
    raw=native_font(REQUIRED,18)
    assert len(raw)<=0xb580-0xa48c, '18px glyphs overlap verified application helper section'
    assert len(raw)<=PHOTO_DAYS-0xa48c, f'18px font overlaps photo digits: {len(raw)}'
    photo=photo_digits()
    assert len(photo)<=0xba00-PHOTO_DAYS, f'44px photo digits overlap reminder code: {len(photo)}'
    days=native_font('0123456789',15)
    assert len(days)<=0xc3c4-DAYS, f'15px calendar digits overlap clock digits: {len(days)}'
    return raw+bytes(PHOTO_DAYS-0xa48c-len(raw))+photo+bytes(DAYS-PHOTO_DAYS-len(photo))+days

def small_font():
    raw=native_font(SMALL_REQUIRED,12)
    assert len(raw)<=0x8500-0x7eb4, f'12px font overlaps reminder state: {len(raw)}'
    date=native_font('0123456789/星期日一二三四五六APM',14)
    assert len(date)<=0x9300-DATE, f'14px clock header table overlaps product code: {len(date)}'
    return raw+bytes(DATE-0x7eb4-len(raw))+date

def compile_product(root,out,leds_off,version='0.0.0'):
    assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version)
    firmware=root/'source/firmware'
    modules=load_modules(firmware)
    unity=(firmware/'product_ui.c').read_text(encoding='utf-8')
    for module in modules['modules']:
        for fragment in module['sources'].get('c_fragment',[]):
            if unity.count('#include "'+fragment+'"')!=1:
                raise ValueError('C fragment must be composed exactly once: '+fragment)
    sources=[firmware/p for m in modules['modules'] for p in m['sources'].get('c_source',[])]
    zig=root/'runtime/tools/zig-windows-x86_64-0.13.0/zig.exe'
    assert subprocess.check_output([str(zig),'version'],text=True).strip()=='0.13.0'
    out.mkdir(parents=True,exist_ok=True);elf=out/'product-ui.elf'
    command=[str(zig),'cc','-target','thumb-freestanding-eabi','-mcpu=cortex_m0','-Oz','-g',
             '-ffreestanding','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
             '-ffunction-sections','-fdata-sections','-nostdlib',f'-DLEDS_OFF={leds_off}',f'-DBOOT_VERSION="V{version}"',
             '-Wl,-T,'+str(root/'source/firmware/product_ui.ld'),'-Wl,--gc-sections','-Wl,-e,product_clock','-Wl,-u,product_clock',
             '-Wl,-u,product_minute_tick','-Wl,-u,product_boot_battery','-Wl,-u,product_refresh','-Wl,-u,product_finish',
             '-Wl,-u,product_caps','-Wl,-u,product_view','-Wl,-u,product_sync_valid',
             '-Wl,-u,product_timezone','-Wl,-u,product_control','-Wl,-u,product_reminder_cmd',
             str(firmware/'product_ui.c'),*map(str,sources),'-o',str(elf)]
    subprocess.run(command,check=True)
    raw=elf.read_bytes();assert raw[:7]==b'\x7fELF\x01\x01\x01'
    table=struct.unpack_from('<I',raw,32)[0]
    entsize,count,names=struct.unpack_from('<HHH',raw,46)
    sections=[struct.unpack_from('<10I',raw,table+i*entsize) for i in range(count)]
    names_section=sections[names];strings=raw[names_section[4]:names_section[4]+names_section[5]]
    regions={};symbols={};functions={}
    for sec in sections:
        name=strings[sec[0]:].split(b'\0',1)[0].decode()
        if name in ('.clock','.product','.reminder','.reminder_extra','.album','.album_extra'):regions[name]=(sec[3],raw[sec[4]:sec[4]+sec[5]])
        if sec[1]==2:
            st=sections[sec[6]];symstrings=raw[st[4]:st[4]+st[5]]
            for off in range(sec[4],sec[4]+sec[5],sec[9]):
                n,value,size,info,other,index=struct.unpack_from('<IIIBBH',raw,off)
                symname=symstrings[n:].split(b'\0',1)[0].decode()
                if symname.startswith('product_'):symbols[symname]=value
                if info&15==2 and size and 0<index<len(sections) and sections[index][2]&2:
                    functions[symname]={'address':value&~1,'bytes':size}
    assert set(regions)=={'.clock','.product','.reminder','.reminder_extra','.album','.album_extra'}
    assert symbols['product_clock']==0x07fc2cc5
    import json
    (out/'product-functions.json').write_text(json.dumps(functions,indent=2),encoding='utf-8')
    return regions,symbols,hashlib.sha256(raw).hexdigest()
