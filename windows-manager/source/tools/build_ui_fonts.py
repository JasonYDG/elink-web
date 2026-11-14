"""Freeze one native Unifont skeleton/weight across the device's 18px CJK labels."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/backend'),str(ROOT/'source/firmware')]
from product_build import REQUIRED
from build_solar_term_fonts import glyph
from bitmap_fonts import font_meta

def build():
    chars=sorted({ch for ch in REQUIRED if ord(ch)>127});assert len(chars)==90
    data={'format':'ELINK-cjk-18-1','size':18,'source':font_meta('unifont'),
          'method':'Native16 skeleton, source pixels and stroke/whitespace topology preserved; same solar-term hints.',
          'glyphs':{ch:{'bits':glyph(ch).tobytes().hex()} for ch in chars}}
    dest=ROOT/'source/fonts/ui-cjk-18.json';dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
    p=ROOT/'source/fonts/preview-fonts.json';meta=json.loads(p.read_text('utf-8'))
    meta['ui_cjk_18']={'version':'1','source':'Native Unifont16 plus reviewed Snow hint; source/tools/build_ui_fonts.py',
                       'local_file':dest.name,'local_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                       'license':meta['unifont']['license'],'characters':''.join(chars)}
    meta['purpose']='Native bitmap UI: Terminus ASCII/photo digits; Fusion small CJK; one Unifont16 skeleton/weight for all90 native18px CJK labels, including the unchanged27 solar-term hints. No outline rasterization.'
    p.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('Frozen90 native CJK labels:',meta['ui_cjk_18']['local_sha256'])

if __name__=='__main__':build()
