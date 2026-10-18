"""Allowlisted delivery with a per-file hash manifest; never includes runtime data."""
from pathlib import Path
import shutil,hashlib,json,zipfile,datetime,argparse
ROOT=Path(__file__).resolve().parents[2]
MANAGER_VERSION='1.5.12'
FIRMWARE_VERSION='1.5.10'
OUT=ROOT/f'releases/{MANAGER_VERSION}-candidate'
parser=argparse.ArgumentParser();parser.add_argument('--refresh',action='store_true');parser.add_argument('--publish',action='store_true',help='Update CURRENT only after package validation');args=parser.parse_args()
if OUT.exists() and not args.refresh:raise SystemExit('Delivery directory exists; use --refresh to add current verification evidence')
def copy(src,dst):
    if dst.is_file() and src.read_bytes()==dst.read_bytes():return
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def tree(src,dst):
    for file in src.rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':copy(file,dst/file.relative_to(src))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
tree(ROOT/'build/desktop/ElinkManager',OUT/'app')
tree(ROOT/f'releases/firmware-{FIRMWARE_VERSION}-test',OUT/'firmware')
copy(ROOT/'source/reference/hmclock-bwr-baseline-spi.bin',OUT/'rollback/hmclock-bwr-baseline-spi.bin')
copy(ROOT/'backup/2026-10-05/analysis/physical-flash-lower256k-before-v4.bin',OUT/'rollback/factory-lower256k.bin')
helper=Path('C:/Program Files (x86)/SmartSnippetsToolbox/SmartSnippetsToolbox5.0.10/common_resources/SupportPackages/DA14585-586/toolbox_resources/common/flash_programmer.bin')
assert sha(helper)=='1c982e96de4eea64289c54f76b8da0c5cea7bfc23eae544543a04b9d32213333'
copy(helper,OUT/'tools/wired-helper/flash_programmer.bin')
for folder in ['backend','firmware','tests','tools','reference','opendesign','fonts','timezones']:
    tree(ROOT/'source'/folder,OUT/'source'/folder)
copy(ROOT/'source/web/config.json',OUT/'source/web/config.json')
tree(ROOT/'source/web/image',OUT/'source/web/image')
copy(ROOT/'runtime/tools/zig-toolchain.json',OUT/'source/tools/zig-toolchain.json')
tree(ROOT/'source/docs',OUT/'docs');copy(ROOT/'source/README.md',OUT/'README.md')
(OUT/'Start.cmd').write_text('@echo off\ncd /d "%~dp0"\napp\\ElinkManager.exe --open\n',encoding='ascii')
legal=OUT/'legal';legal.mkdir(exist_ok=True)
sdk=ROOT/'reference/epd213/downloads/HMCLOCK-bc9c1ea/HMCLOCK-bc9c1ea04c8ec5ffc6c73cf4e1aaf382817ebdc3/src/user_custs1_impl.c'
(legal/'SDK_NOTICE.txt').write_text(sdk.read_text(encoding='utf-8').split('*/',1)[0]+'*/\n',encoding='utf-8')
site=ROOT/'runtime/venv/Lib/site-packages'
for dist in site.glob('*.dist-info'):
    for file in dist.rglob('*'):
        if file.is_file() and file.name.upper().startswith(('LICENSE','COPYING','NOTICE')):copy(file,legal/'dependencies'/dist.name/file.relative_to(dist))
for file in (ROOT/'source/fonts').rglob('*'):
    if file.is_file() and file.suffix.lower()=='.txt':copy(file,legal/'fonts'/file.relative_to(ROOT/'source/fonts'))
for p in [Path('D:/anaconda3/LICENSE_PYTHON.txt'),Path('D:/anaconda3/LICENSE_PYTHON')]:
    if p.exists():copy(p,legal/'PYTHON_LICENSE.txt');break
required=['Start.cmd','README.md','app/ElinkManager.exe','app/_internal/python312.dll','app/_internal/source/opendesign/mockups/elink-manager/index.html','app/_internal/source/opendesign/mockups/elink-manager/app.js','app/_internal/source/opendesign/mockups/elink-manager/style.css','app/_internal/source/opendesign/design-systems/elink-home/tokens/colors_and_type.css',f'firmware/elink-bwr-{FIRMWARE_VERSION}.elink-update.json','firmware/manifest.json','firmware/photo-calendar-preview.png','rollback/hmclock-bwr-baseline-spi.bin','docs/FLASHING.md','docs/REPAIR_1.5.2.md']
required += ['app/_internal/source/opendesign/mockups/elink-manager/page-'+name+'.png' for name in ('default','clock','calendar','reminders')]
required += ['app/_internal/source/opendesign/mockups/elink-manager/firmware-versions.json']
required += [f'docs/MANAGER_{MANAGER_VERSION}.md','docs/MANAGER_1.5.8.md','docs/MANAGER_1.5.2.md','docs/FAST_REFRESH_RESEARCH.md','docs/WORKITEMS_POWER_REVIEW.md']
required += ['app/_internal/source/opendesign/mockups/elink-manager/gallery.js','app/_internal/source/opendesign/mockups/elink-manager/operation.js','app/_internal/source/opendesign/mockups/elink-manager/page-photo-calendar.png','app/_internal/source/web/config.json']
for item in json.loads((ROOT/'source/web/config.json').read_text('utf-8'))['gallery']:
    required += ['app/_internal/source/web/'+item[key] for key in ('path','frame')]
required += ['app/_internal/sqlite3.dll','app/_internal/ffi.dll']
required += ['app/_internal/source/fonts/NotoSansSC/NotoSansSC-Black.otf','app/_internal/source/fonts/NotoSansSC/NotoSansSC-Medium.otf','legal/fonts/NotoSansSC/LICENSE.txt']
required += ['app/_internal/source/fonts/HarmonyOS/HarmonyOS_SansSC_Bold.ttf','app/_internal/source/fonts/HarmonyOS/HarmonyOS_Sans_Condensed_Bold.ttf','legal/fonts/HarmonyOS/LICENSE.txt']
assert all((OUT/p).is_file() for p in required)
for item in json.loads((OUT/'app/_internal/source/web/config.json').read_text('utf-8'))['gallery']:
    assert sha(OUT/'app/_internal/source/web'/item['frame'])==item['sha256']
pilot_path=ROOT/f'build/diagnostics/physical-{FIRMWARE_VERSION}-delivery-ota-result.json'
pilot=json.loads(pilot_path.read_text('utf-8')) if pilot_path.exists() else {}
evidence=ROOT/f'build/diagnostics/manager-{MANAGER_VERSION}'
for name in ('tests-final.txt','package-smoke.txt','previews.json','visual-verification.md','adversarial-review.md','native-offline-check.json','protected-region-check.json','regression-status.json','compressed-clock-proof.json','memory-map.json','ui-tests-final.txt','physical-boot-check.json'):
 p=evidence/name
 if p.is_file():copy(p,OUT/f'evidence/manager-{MANAGER_VERSION}'/name)
for pattern in ('visual-*.jpg','ui-*.png'):
 for p in evidence.glob(pattern):copy(p,OUT/f'evidence/manager-{MANAGER_VERSION}'/p.name)

files={}
for p in sorted(OUT.rglob('*')):
    relative=p.relative_to(OUT).as_posix();relative.encode('ascii')
    if p.is_file() and relative!='DELIVERY_MANIFEST.json':
        assert not p.name.endswith(('.sqlite3','.log','.pid'))
        files[relative]={'bytes':p.stat().st_size,'sha256':sha(p)}
info={'version':f'{MANAGER_VERSION}-candidate','manager_version':MANAGER_VERSION,'firmware_version':FIRMWARE_VERSION,'revision':1,'generated':datetime.datetime.now().astimezone().isoformat(),'hardware_tested':False,'persistent_gallery':True,'offline_photo_rotation':True,'required_files':required,'files':files}
info['hardware_ota_verified_devices']=int(pilot.get('job',{}).get('receipt',{}).get('result')=='ota_boot_verified');info['optical_result_verified']=False
(OUT/'DELIVERY_MANIFEST.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
archive=ROOT/f'releases/elink-manager-{MANAGER_VERSION}-candidate.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob('*'):
        if p.is_file():z.write(p,p.relative_to(OUT).as_posix())
with zipfile.ZipFile(archive) as z:
    assert set(required)<=set(z.namelist())
    for name in z.namelist():name.encode('ascii')
    for name,meta in files.items():assert hashlib.sha256(z.read(name)).hexdigest()==meta['sha256']
firmware_archive=ROOT/f'releases/elink-bwr-{FIRMWARE_VERSION}-test.zip'
firmware_meta=json.loads((OUT/'firmware/manifest.json').read_text())
assert sha(firmware_archive)==json.loads((ROOT/'releases/CURRENT_FIRMWARE_TEST.json').read_text())['archive_sha256']
(ROOT/('releases/CURRENT_DELIVERY.json' if args.publish else f'build/CURRENT_DELIVERY-{MANAGER_VERSION}.json')).write_text(json.dumps({'version':info['version'],'manager_version':MANAGER_VERSION,'firmware_version':FIRMWARE_VERSION,'revision':1,'status':'candidate','persistent_gallery':True,'offline_photo_rotation':True,'path':str(OUT),'archive':str(archive),'archive_sha256':sha(archive),'firmware_archive':str(firmware_archive),'firmware_archive_sha256':sha(firmware_archive),'firmware_id':firmware_meta['firmware_id'],'hardware_tested':False,'hardware_ota_verified_devices':info['hardware_ota_verified_devices']},indent=2),encoding='utf-8')
print(json.dumps({'directory':str(OUT),'zip':str(archive),'bytes':archive.stat().st_size,'files':len(files),'firmware_zip':str(firmware_archive),'firmware_zip_bytes':firmware_archive.stat().st_size,'hardware_tested':False},indent=2))
