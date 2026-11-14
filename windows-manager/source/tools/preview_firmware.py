"""Decode the exact native BWR buffer; no font drawing, resizing or smoothing."""
import os,sys,struct,json,hashlib
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tests'),str(ROOT/'source/backend')]
from test_product_ui import ProductMachine,BASE,STATE,FIRMWARE_DIR

def frame_image(frame):
    if len(frame)!=8000:raise ValueError('BWR frame must be 8000 bytes')
    # RAM has 128 source bits x 250 gates; only 122 source bits are visible.
    planes=[Image.frombytes('1',(128,250),frame[i:i+4000]).crop((0,0,122,250)).transpose(Image.Transpose.ROTATE_270) for i in (0,4000)]
    im=planes[0].convert('RGB');im.paste((190,0,0),(0,0),planes[1])
    return im

def verify_firmware(directory,package):
    from ota import validate_package
    directory=Path(directory);package=Path(package)
    meta=json.loads((directory/'manifest.json').read_text('utf-8'))
    app=(directory/f'elink-bwr-{meta["version"]}-app.bin').read_bytes()
    update=json.loads(package.read_text('utf-8'));raw,_=validate_package(update)
    if raw!=app or hashlib.sha256(app).hexdigest()!=meta['app_sha256'] or any(update[k]!=meta[k] for k in ('version','firmware_id')):
        raise ValueError('Preview application does not match the specified OTA package')
    return {'version':meta['version'],'firmware_id':meta['firmware_id'],'application_sha256':meta['app_sha256'],
            'ota_package':str(package.resolve()),'ota_package_sha256':hashlib.sha256(package.read_bytes()).hexdigest()}

def export_frame(directory,name,frame):
    im=frame_image(frame);png=Path(directory)/f'{name}.png';raw=Path(directory)/f'{name}.bwr.bin'
    im.save(png,format='PNG');raw.write_bytes(frame)
    with Image.open(png) as saved:
        if saved.size!=(250,122) or saved.convert('RGB').tobytes()!=im.tobytes():raise ValueError('PNG changed native pixels')
    return {'width':250,'height':122,'frame_bytes':len(frame),'frame_sha256':hashlib.sha256(frame).hexdigest(),
            'png_sha256':hashlib.sha256(png.read_bytes()).hexdigest(),'colors':len(im.getcolors()),'scale':1,
            'interpolation':False,'png_matches_frame':True}

if __name__=='__main__':
    if not os.environ.get('ELINK_TEST_FIRMWARE_DIR') or not os.environ.get('ELINK_PREVIEW_UPDATE_PACKAGE'):
        raise SystemExit('Set ELINK_TEST_FIRMWARE_DIR and ELINK_PREVIEW_UPDATE_PACKAGE explicitly; no legacy build fallback')
    provenance=verify_firmware(FIRMWARE_DIR,os.environ['ELINK_PREVIEW_UPDATE_PACKAGE'])
    out=Path(os.environ.get('ELINK_PREVIEW_OUT',ROOT/'build/native-quick-preview'))
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a new empty output directory to exclude stale previews')
    out.mkdir(parents=True,exist_ok=True)
    m=ProductMachine();m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1647))
    m.uc.mem_write(STATE+7,b'\x00')
    m.uc.mem_write(BASE+0xdd98+0x20,bytes(4)) # No season calculation in direct RTC fixture.
    pages={'clock':export_frame(out,'clock',m.draw(force=128))};m.finish()
    m.uc.mem_write(STATE+7,b'\x03')
    pages['calendar']=export_frame(out,'calendar',m.draw(force=128))
    (out/'proof.json').write_text(json.dumps({**provenance,'pages':pages},indent=2)+'\n',encoding='utf-8')
