"""ELINK Screen Bold bitmap cells, shared by host and device rendering."""
import gzip,hashlib,json,sys
from functools import lru_cache
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops

FONT_ROOT=(Path(sys._MEIPASS)/'source' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'fonts'
# Coverage threshold for the grey outline render. Lower values fill CJK counters at <=20px.
INK=128
# Ideographic em box spans 0.88em above to 0.12em below the baseline in Noto/Source Han.
BASELINE=0.88

def row_mask(width,height,rows):
    assert len(rows)==height
    mask=Image.new('1',(width,height));stride=(width+7)//8
    for y,row in enumerate(rows):
        bits=int(row,16)
        for x in range(width):
            if bits&(1<<(stride*8-1-x)):mask.putpixel((x,y),1)
    return mask

def font_meta(name):
    return json.loads((FONT_ROOT/'preview-fonts.json').read_text('utf-8'))[name]

@lru_cache(maxsize=3)
def font_source(height):
    name={12:'fusion',14:'terminus',16:'unifont'}[height]
    meta=font_meta(name)
    raw=(FONT_ROOT/meta['local_file']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['local_sha256']:raise ValueError('字体哈希不一致：'+name)
    return gzip.decompress(raw).decode('utf-8').splitlines()

@lru_cache(maxsize=128)
def fallback_cells(chars,height):
    wanted=set(chars);result={};lines=font_source(height)
    if height in (12,14):
        ascent=10 if height==12 else 12
        block=[]
        for line in lines:
            if line.startswith('STARTCHAR '):block=[]
            block.append(line)
            if line!='ENDCHAR':continue
            props=dict(x.split(' ',1) for x in block if ' ' in x)
            cp=int(props['ENCODING'])
            if chr(cp) not in wanted:continue
            advance=int(props['DWIDTH'].split()[0]);w,h,bx,by=map(int,props['BBX'].split())
            glyph=row_mask(w,h,block[block.index('BITMAP')+1:-1]);cell=Image.new('1',(advance,height))
            assert 0<=bx and bx+w<=advance and 0<=ascent-by-h and ascent-by<=height
            cell.paste(glyph,(bx,ascent-by-h));result[chr(cp)]=cell
    else:
        for line in lines:
            code,bits=line.split(':');cp=int(code,16)
            if chr(cp) not in wanted:continue
            width=len(bits)//4;digits=width//4
            result[chr(cp)]=row_mask(width,16,[bits[y*digits:(y+1)*digits] for y in range(16)])
    return result

@lru_cache(maxsize=2)
def noto_path(style='noto'):
    meta=font_meta(style);path=FONT_ROOT/meta['local_file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['local_sha256']:raise ValueError('思源黑体字体哈希不一致')
    return str(path)

@lru_cache(maxsize=32)
def noto_font(height):
    return ImageFont.truetype(noto_path('noto_medium' if height in (14,18) else 'noto'),height)

def glyph_cell(ch,height):
    """One baseline-aligned binary cell, `height` rows tall, from the unmodified outline."""
    font=noto_font(height);advance=max(1,round(font.getlength(ch)));pad=height
    canvas=Image.new('L',(advance+2*pad,height),0)
    # The native 12px Black slash needs one row upward to keep its lower tip.
    ImageDraw.Draw(canvas).text((pad,round(height*BASELINE)-(height==12 and ch=='/')),ch,font=font,fill=255,anchor='ls')
    ink=canvas.point(lambda v:255 if v>=INK else 0).convert('1');box=ink.getbbox()
    left=min(pad,box[0]) if box else pad;right=max(pad+advance,box[2]) if box else pad+advance
    return ink.crop((left,0,right,height))

def has_glyph(ch,height):
    font=noto_font(height)
    return bytes(font.getmask(ch,mode='1'))!=bytes(font.getmask('\U0010fffd',mode='1')) or ch==' '

@lru_cache(maxsize=256)
def cells(chars,height):
    if height<12:raise ValueError('点阵字号至少为12像素')
    native=12 if height in (12,14,15,24,28,44) else 16
    result={};scale=height//native;originals=fallback_cells(chars,native)
    latin=fallback_cells(''.join(ch for ch in chars if 32<=ord(ch)<127),14) if height<=20 else {}
    cjk=fallback_cells(''.join(ch for ch in chars if ord(ch)>=0x2e80 and ch not in '\u3031\u3032'),12) if height<=20 else {}
    for ch,source in originals.items():
        cell=source.resize((source.width*scale,native*scale),Image.Resampling.NEAREST)
        width=source.width*height//native
        if height in (44,66) and ch in '0123456789:':
            # Preserve the photo/clock column advances while enlarging whole source pixels.
            zoom=4 if height==44 else 6;source=source.crop(source.getbbox())
            cell=source.resize((source.width*zoom,source.height*zoom),Image.Resampling.NEAREST)
            width=27 if height==44 else 28 if ch==':' else 50
        if height<=20 and source.getbbox():
            if ch in latin:
                source=latin[ch];box=source.getbbox()
                # Native bold stems stay two pixels wide; retain descenders and punctuation.
                cell=source.crop((0,min(2,box[1]),8,max(12,box[3])))
                width=8 if height in (12,16) else max(8,(height+2)//2)
                cell=cell.resize((8,min(height,max(cell.height,height-1))),Image.Resampling.NEAREST)
                x=(width-8)//2
            else:
                target=height-1 if height not in (12,16) else native
                cell=source.resize((source.width*target//native,target),Image.Resampling.NEAREST)
                width=max(width,cell.width+(height>12 and height!=16));x=(width-cell.width)//2
                if ch in cjk and cjk[ch].width==12 and source.width>=12:
                    # Enlarge the coarser native grid before adding weight, retaining open counters.
                    target_width=max(12,height-2 if height>=16 else height-1)
                    cell=cjk[ch].resize((target_width,max(12,height-1)),Image.Resampling.NEAREST)
                    x=(width-cell.width)//2
            assert x+cell.width<=width and cell.height<=height
            out=Image.new('1',(width,height));out.paste(cell,(x,(height-cell.height)//2))
            result[ch]=out if ch in latin else ImageChops.logical_or(out,out.crop((-1,0,width-1,height)))
        else:
            assert cell.width<=width and cell.height<=height
            out=Image.new('1',(width,height));out.paste(cell,((width-cell.width)//2,(height-cell.height)//2));result[ch]=out
    return result

def text_mask(value,size=12,bold_digits=False):
    # Compatibility flag: weight is already baked into the shared cells.
    if not value:return Image.new('1',(1,1))
    glyphs=cells(''.join(sorted(set(value))),size)
    missing=set(value)-glyphs.keys()
    if missing:raise ValueError('字体不含这些字符：'+''.join(sorted(missing)))
    mask=Image.new('1',(sum(glyphs[ch].width for ch in value),size));x=0
    for ch in value:
        mask.paste(glyphs[ch],(x,0));x+=glyphs[ch].width
    return mask

def paint(im,value,xy,size=12,color=(0,0,0),bold_digits=False):
    mask=text_mask(value,size,bold_digits);box=mask.getbbox()
    if box:im.paste(color,xy,mask.crop(box))
    return mask

def status_icon(im,x=194,y=4,percent=None):
    from PIL import ImageDraw
    d=ImageDraw.Draw(im)
    for row,bits in enumerate((48,56,60,567,1843,1023,252,120,252,1023,1843,567,60,56,48)):
        for col in range(11):
            if bits&(1024>>col):d.point((x-18+col,y-2+row),fill='black')
    d.rectangle((x,y,x+16,y+10),outline='black',width=2);d.rectangle((x+17,y+3,x+18,y+7),fill='black')
    if percent is not None:
        if type(percent)!=int or not 0<=percent<=100:raise ValueError('电量须为 0..100')
        fill=(percent*11+50)//100
        if fill:d.rectangle((x+3,y+3,x+2+fill,y+7),fill='black')
    # Same cell origin as the firmware label text(x+24,y-2), side bearings included.
    im.paste('black',(x+24,y-2),text_mask('--%' if percent is None else str(percent)+'%',12))

def native_font(chars,height,bold_digits=False):
    """Original u16 table / five-byte glyph-header format; no new device renderer."""
    import struct
    glyphs=cells(''.join(sorted(set(chars))),height)
    if set(chars)-glyphs.keys():raise ValueError('设备字库缺字：'+''.join(set(chars)-glyphs.keys()))
    table=bytearray(struct.pack('<H',len(glyphs))+bytes(len(glyphs)*4));data=bytearray()
    for i,(ch,cell) in enumerate(sorted(glyphs.items())):
        box=cell.getbbox();bx,by=(box[:2] if box else (0,0));glyph=cell.crop(box) if box else Image.new('1',(0,0))
        struct.pack_into('<HH',table,2+i*4,ord(ch),len(table)+len(data))
        data.extend(struct.pack('<BBBbb',cell.width,glyph.width,glyph.height,bx,by))
        for y in range(glyph.height):
            for start in range(0,glyph.width,8):
                data.append(sum(128>>bit for bit in range(8) if start+bit<glyph.width and glyph.getpixel((start+bit,y))))
    return bytes(table+data)
