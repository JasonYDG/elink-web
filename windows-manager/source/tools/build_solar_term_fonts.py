"""Freeze the 27 solar-term glyphs without joining strokes or closing counters."""
from pathlib import Path
import hashlib,json,sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source/backend'))
from bitmap_fonts import fallback_cells,row_mask,font_meta
from photo_calendar import TERMS

ALL={(x,y) for y in range(18) for x in range(18)}
N4=((1,0),(-1,0),(0,1),(0,-1))
N8=tuple((x,y) for y in (-1,0,1) for x in (-1,0,1) if x or y)

def groups(points,neighbors):
    remaining=set(points);result=[]
    while remaining:
        group={remaining.pop()};todo=list(group)
        while todo:
            x,y=todo.pop()
            for dx,dy in neighbors:
                p=(x+dx,y+dy)
                if p in remaining:remaining.remove(p);group.add(p);todo.append(p)
        result.append(group)
    return result

def glyph(ch):
    if ch=='雪':
        return row_mask(18,18,('000000','1ffe00','1ffe00','00c000','7fff80','60c180','6cd980','60c180','6cd980','000000','1ffe00','1ffe00','000600','0ffe00','0ffe00','000600','1ffe00','1ffe00'))
    source=fallback_cells(ch,16)[ch]
    ink={(x+1,y+1) for y in range(16) for x in range(16) if source.getpixel((x,y))}
    black=len(groups(ink,N8));white=groups(ALL-ink,N4)
    holes=[g for g in white if not any(x in (0,17) or y in (0,17) for x,y in g)]
    for dx,dy in ((1,0),(0,1)):
        candidates=sorted({(x+dx,y+dy) for x,y in ink if 1<=x+dx<=16 and 1<=y+dy<=17}-ink,key=lambda p:(p[1],p[0]))
        for p in candidates:
            proposed=ink|{p}
            if any(len(g-proposed)<min(2,len(g)) for g in holes):continue
            if len(groups(proposed,N8))!=black or len(groups(ALL-proposed,N4))!=len(white):continue
            ink=proposed
    # Resolve diagonal-only contacts without joining separate strokes or closing whitespace.
    for p in sorted({(x+dx,y+dy) for x,y in ink for dx,dy in N4 if 1<=x+dx<=16 and 1<=y+dy<=17}-ink):
        proposed=ink|{p}
        if len(groups(proposed,N4))>=len(groups(ink,N4)):continue
        if any(len(g-proposed)<min(2,len(g)) for g in holes):continue
        if len(groups(proposed,N8))!=black or len(groups(ALL-proposed,N4))!=len(white):continue
        ink=proposed
    assert len(groups(ink,N4))==black,('Unresolved diagonal-only stroke',ch)
    mask=Image.new('1',(18,18))
    for p in ink:mask.putpixel(p,1)
    return mask

def build():
    chars=sorted(set(''.join(TERMS)));assert len(TERMS)==24 and len(chars)==27
    glyphs={ch:{'bits':glyph(ch).tobytes().hex(),'source':'native Snow hint' if ch=='雪' else 'Unifont16; topology-preserving weight'} for ch in chars}
    data={'format':'ELINK-solar-18-1','size':18,'terms':TERMS,'base_source':font_meta('unifont'),'method':'Preserve source pixels, 8-connected ink components, 4-connected whitespace regions, and at least two pixels per original counter when possible. Dense internal details retain one-pixel strokes. Snow retains the reviewed native hint.','glyphs':glyphs}
    dest=ROOT/'source/fonts/solar-terms-18.json';dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    p=ROOT/'source/fonts/preview-fonts.json';meta=json.loads(p.read_text('utf-8'))
    meta['solar_terms_18']={'version':'1','source':'Derived from pinned Unifont16 plus reviewed native Snow hint; source/tools/build_solar_term_fonts.py','local_file':dest.name,'local_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'license':meta['unifont']['license'],'characters':''.join(chars)}
    p.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Frozen24 terms /27 glyphs:',meta['solar_terms_18']['local_sha256'])

if __name__=='__main__':build()
