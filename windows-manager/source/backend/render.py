"""One renderer for preview and device data, 250x122 logical / 122x250 native."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
import hashlib,io,base64,datetime,math
from bitmap_fonts import text_mask,status_icon

def render(spec,battery_percent=None):
    if not isinstance(spec,dict):raise ValueError('模板必须是对象')
    if spec.get('kind')=='image':
        if 'native_frame' in spec:
            frame=base64.b64decode(spec['native_frame'],validate=True)
            if len(frame)!=8000:raise ValueError('原生图片须为8000字节')
            return {'frame':frame,'png':frame_png(frame),'sha256':hashlib.sha256(frame).hexdigest(),'red_pixels':sum(b.bit_count() for b in frame[4000:])}
        if 'builtin' in spec:
            from builtin_gallery import native
            return native(spec['builtin'])
        try:return image_upload(spec['image'],spec.get('crop'))
        except (OSError,ValueError) as exc:raise ValueError('图片无法解码，请使用完整的 PNG、JPEG、WebP 或 BMP 文件') from exc
    t=datetime.datetime.now()
    fields={'{date}':t.strftime('%Y-%m-%d'),'{time}':t.strftime('%H:%M'),'{weekday}':'星期'+'一二三四五六日'[t.weekday()]}
    spec=dict(spec)
    for key in ('title','body','footer'):
        if key in spec:
            value=str(spec[key])
            for tag,text in fields.items():value=value.replace(tag,text)
            spec[key]=value
    im=Image.new('RGB',(250,122),'white');d=ImageDraw.Draw(im)
    kind=spec.get('kind','notice')
    red=(190,0,0) if spec.get('red',True) else (0,0,0)
    def text(s,xy,size,color='black',limit=24,right=244,bottom=122):
        s=str(s)[:limit]
        available=right-xy[0]
        # Every size is rasterized natively; shrink in whole pixels, never scale bitmaps.
        mask=text_mask(s,size)
        for candidate in (32,28,24,20,18,16,14,12):
            if candidate<size and (mask.width>available or xy[1]+mask.height>bottom):
                size=candidate;mask=text_mask(s,size)
        while s and mask.width>available:
            s=s[:-1];mask=text_mask(s+'…',size)
        if not s:return
        box=mask.getbbox()
        if box:
            # Thin red strokes look patchy on BWR panels.
            if color==red and size<18:color='black'
            im.paste(color,xy,mask.crop(box))
    if kind=='notice':
        text(spec.get('title','电子标签'),(8,7),24,red,18,right=168,bottom=34)
        status_icon(im,194,10,battery_percent)
        d.line((8,35,241,35),fill='black')
        lines=str(spec.get('body','欢迎使用')).splitlines()[:2]
        for row,line in enumerate(lines):text(line,(8,45+row*26),24 if len(lines)>1 else 32,'black',18)
        text(spec.get('footer',''),(8,104),18,'black',26)
    elif kind=='meeting':
        occupied=bool(spec.get('occupied',False))
        text(spec.get('title','会议室'),(6,3),16,'black',18)
        d.rectangle((6,29,244,66),fill=red if occupied else 'black')
        text('使用中' if occupied else '可使用',(14,33),24,'white')
        text(str(spec.get('body','')).splitlines()[0] if spec.get('body') else '',(6,69),16,'black',26)
        text(spec.get('footer',''),(6,104),16,'black',26)
    elif kind=='calendar':
        text(spec.get('title','今日安排'),(6,1),24,red,18)
        for row,line in enumerate(str(spec.get('body','')).splitlines()[:3]):
            text(line,(6,29+row*22),18,'black',22)
        text(spec.get('footer',''),(6,105),16,'black',26)
    elif kind=='clock':
        import re
        if not re.fullmatch(r'\d{1,2}:\d{2}',str(spec.get('body',''))):raise ValueError('时钟正文请输入 {time} 或 HH:MM，例如 12:00')
        hour,minute=map(int,str(spec['body']).split(':'))
        if not 0<=hour<=23 or not 0<=minute<=59:raise ValueError('时钟时间须为 00:00 至 23:59')
        text(spec.get('title','日期'),(6,0),17,'black',28)
        text(spec.get('body','12:00'),(8,19),64,'black',5)
        text(spec.get('footer',''),(6,99),16,'black',30)
    else:raise ValueError('模板类型仅支持 notice / meeting / calendar / clock')
    return quantize(im)

def notice_battery(png,percent):
    # Keep queued date/text/crop pixels frozen; only replace the reserved status area.
    with Image.open(io.BytesIO(png)) as source:im=source.convert('RGB')
    if im.size!=(250,122):raise ValueError('公告图片尺寸不正确')
    ImageDraw.Draw(im).rectangle((176,8,249,22),fill='white')
    status_icon(im,194,10,percent)
    return quantize(im)

def frame_png(frame):
    if len(frame)!=8000:raise ValueError('屏幕像素须为 8000 字节')
    im=Image.new('RGB',(250,122),'white')
    for y in range(122):
        for x in range(250):
            pos=(249-x)*16+y//8;mask=128>>(y%8)
            if frame[4000+pos]&mask:im.putpixel((x,y),(190,0,0))
            elif not frame[pos]&mask:im.putpixel((x,y),(0,0,0))
    buf=io.BytesIO();im.save(buf,format='PNG');return buf.getvalue()

def photo_calendar_frame(frame,photo_x=42):
    if len(frame)!=8000:raise ValueError('屏幕像素须为8000字节')
    result=bytearray(b'\xff'*4000+bytes(4000))
    if type(photo_x)!=int or not 0<=photo_x<=84:raise ValueError('图片日历水平位置必须为0..84的整数')
    photo_x=min(photo_x,76)
    for plane in (0,4000):
        for x in range(174):
            source=plane+(249-photo_x-x)*16;target=plane+(249-x)*16
            result[target:target+16]=frame[source:source+16]
    raw=bytes(result)
    return {'frame':raw,'png':frame_png(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def quantize(im):
    im=im.convert('RGB').resize((250,122),Image.Resampling.LANCZOS)
    out=Image.new('RGB',im.size,'white');black=bytearray(b'\xff'*4000);red=bytearray(4000)
    for y in range(122):
        for x in range(250):
            r,g,b=im.getpixel((x,y))
            is_red=r>100 and r>g*1.4 and r>b*1.4
            is_black=not is_red and (r*299+g*587+b*114)<155000
            # Rotation 3 from exact native draw_pixel: nx=y, ny=249-x.
            pos=(249-x)*16+y//8;mask=128>>(y%8)
            if is_red or is_black:black[pos]&=255^mask
            if is_red:red[pos]|=mask
            out.putpixel((x,y),(190,0,0) if is_red else ((0,0,0) if is_black else (255,255,255)))
    frame=bytes(black+red)
    buf=io.BytesIO();out.save(buf,format='PNG')
    return {'png':buf.getvalue(),'frame':frame,'sha256':hashlib.sha256(frame).hexdigest(),'red_pixels':sum(byte.bit_count() for byte in red)}

def image_upload(encoded,crop=None):
    if not isinstance(encoded,str) or len(encoded)>3_000_000:raise ValueError('图片过大（限 2MB）')
    raw=base64.b64decode(encoded,validate=True)
    if len(raw)>2_000_000:raise ValueError('图片过大')
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>12_000_000:raise ValueError('图片尺寸过大')
        im.load();im=ImageOps.exif_transpose(im)
        if crop is not None:
            if not isinstance(crop,dict) or crop.get('mode') not in ('cover','contain','stretch'):raise ValueError('裁切模式不合法')
            rotation=crop.get('rotation',0)
            if type(rotation)!=int or rotation not in (0,90,180,270):raise ValueError('旋转角度不合法')
            im=im.rotate(-rotation,expand=True)
            zoom,x,y=(crop.get(k,v) for k,v in (('zoom',1),('x',0),('y',0)))
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in (zoom,x,y)) or not 1<=zoom<=4 or not -1<=x<=1 or not -1<=y<=1:raise ValueError('裁切参数不合法')
            rgba=im.convert('RGBA');im=Image.new('RGBA',im.size,'white');im.alpha_composite(rgba);im=im.convert('RGB')
            if crop['mode']!='stretch':
                scale=(max if crop['mode']=='cover' else min)(250/im.width,122/im.height)*zoom
                dx=(250-im.width*scale)/2+x*max(0,(im.width*scale-250)/2)
                dy=(122-im.height*scale)/2+y*max(0,(im.height*scale-122)/2)
                im=im.transform((250,122),Image.Transform.AFFINE,(1/scale,0,-dx/scale,0,1/scale,-dy/scale),Image.Resampling.BICUBIC,fillcolor='white')
        return quantize(im)
