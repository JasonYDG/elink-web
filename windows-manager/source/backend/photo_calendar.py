"""Host preview of the firmware photo-date column; never used as device clock data."""
import datetime
from PIL import Image
from bitmap_fonts import text_mask
from lunar import lunar_fields
from render import quantize

TERMS='小寒 大寒 立春 雨水 惊蛰 春分 清明 谷雨 立夏 小满 芒种 夏至 小暑 大暑 立秋 处暑 白露 秋分 寒露 霜降 立冬 小雪 大雪 冬至'.split()
TERM_SECONDS=(0,1272283,2547462,3828568,5117483,6416376,7726093,9047327,
              10379235,11721860,13072410,14428379,15787551,17145937,18501082,
              19850188,21190911,22520708,23839844,25146961,26443845,27730671,29010666,30284551)

def next_term(day):
    for year in (day.year,day.year+1):
        yy=year-2020;leap=(yy-1)//4+1 if yy else 0
        for name,seconds in zip(TERMS,TERM_SECONDS):
            target=datetime.date(year,1,1)+datetime.timedelta(days=(451804+20950*yy-leap*86400+seconds)//86400)
            days=(target-day).days
            if days>=0:return name,'今日' if not days else f'{days}天后'
    raise ValueError('节气日期超出范围')

def date_column(day):
    if not 2020<=day.year<=2051:raise ValueError('日期须在2020..2051年范围内')
    im=Image.new('RGB',(250,122),'white')
    def draw(label,size,y,x=None,red=False):
        mask=text_mask(label,size)
        x=212-mask.width//2 if x is None else x
        im.paste((190,0,0) if red else (0,0,0),(x,y),mask)
    draw(day.strftime('%Y/%m'),12,2)
    draw(f'{day.day:02}',44,15,185,red=True)
    draw('星期'+'一二三四五六日'[day.weekday()],18,62,185)
    _,month,number=lunar_fields(day)
    label={10:'初十',20:'二十',30:'三十'}.get(number)
    if label is None:label=('初' if number<10 else '十' if number<20 else '廿')+'一二三四五六七八九'[number%10-1]
    draw(('闰' if month&128 else '')+'正二三四五六七八九十冬腊'[month&127]+'月'+label,12,84)
    name,countdown=next_term(day);x=212-(36+text_mask(countdown,12).width)//2
    draw(name,18,101,x);draw(countdown,12,106,x+36)
    return quantize(im)
