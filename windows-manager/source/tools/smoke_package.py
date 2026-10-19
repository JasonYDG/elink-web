"""Fresh ZIP startup on a clean PATH, real HTTP/resources/SQLite/WinRT scan."""
from pathlib import Path
import argparse,subprocess,zipfile,json,urllib.request,urllib.error,time,os,hashlib,sys,sqlite3,socket
ROOT=Path(__file__).resolve().parents[2]
folder=ROOT/'backup'/time.strftime('%Y-%m-%d')/('package-smoke-1.5.13-'+time.strftime('%H%M%S'));folder.mkdir(parents=True)
parser=argparse.ArgumentParser();parser.add_argument('--no-scan',action='store_true');args=parser.parse_args()
archive=ROOT/'releases/elink-manager-1.5.13-candidate.zip'
with zipfile.ZipFile(archive) as z:z.extractall(folder/'delivery')
delivery=folder/'delivery';exe=delivery/'app/ElinkManager.exe'
manifest=json.loads((delivery/'DELIVERY_MANIFEST.json').read_text())
for name,meta in manifest['files'].items():assert hashlib.sha256((delivery/name).read_bytes()).hexdigest()==meta['sha256']
env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON','CONDA'))}
env['PATH']=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot']
log=open(folder/'stdout.log','w',encoding='utf-8');err=open(folder/'stderr.log','w',encoding='utf-8')
def unused_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
data=folder/'private-data';port=unused_port();root=f'http://127.0.0.1:{port}'
process=subprocess.Popen([str(exe),'--port',str(port),'--data',str(data)],cwd=folder,env=env,stdout=log,stderr=err)
def request(path,body=None,token=None):
    headers={'X-Elink-Token':token,'Content-Type':'application/json'} if token else {}
    raw=json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(root+path,data=raw,headers=headers),timeout=15) as r:
        content=r.read();return json.loads(content) if r.headers['Content-Type'].startswith('application/json') else content
report={'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'fresh_directory':str(folder),'clean_path':env['PATH'],'hardware_flashed':False,'physical_display_verified':False}
try:
    for _ in range(40):
        if process.poll() is not None:raise RuntimeError((folder/'stderr.log').read_text())
        try:config=request('/api/config');break
        except (OSError,urllib.error.URLError):time.sleep(.25)
    else:raise TimeoutError('Packaged start timed out')
    assert config['version']=='1.5.13'
    assert manifest['manager_version']=='1.5.13' and manifest['firmware_version']=='1.5.11'
    assert config['bundled_runtime'] and Path(config['runtime_executable']).resolve()==exe.resolve()
    assert Path(config['data_directory']).resolve()==data.resolve()
    for path in ['/','/app.js','/gallery.js','/operation.js','/style.css','/design-systems/elink-home/tokens/colors_and_type.css']:assert request(path)
    for name in ('default','clock','calendar','reminders','photo-calendar'):assert request('/page-'+name+'.png').startswith(b'\x89PNG')
    assert config['firmware_versions']['85bba3ef']=='1.3.5' and config['firmware_versions']['2dbcfd7c']=='1.4.0'
    token=config['token'];initial=request('/api/state');assert initial['devices']==[] and initial['jobs']==[] and initial['worker_alive']
    try:request('/api/register',{'address':'bad-address'},token)
    except urllib.error.HTTPError as e:assert e.code==400
    else:raise AssertionError('Invalid address accepted')
    from zoneinfo import ZoneInfo
    tzif=delivery/'app/_internal/source/timezones/Europe-Amsterdam.tzif'
    with tzif.open('rb') as f:assert ZoneInfo.from_file(f).key is None
    t=request('/api/templates',{'title':'Fresh package validation','spec':{'kind':'notice','title':'软件验收','body':'黑白红独立运行','footer':'NO DEVICE WRITE'}},token)
    assert request('/api/templates/'+t['id']+'/preview.png').startswith(b'\x89PNG')
    assert request('/api/templates',{'id':t['id'],'title':'Updated same template','spec':{'kind':'meeting','title':'会议室','body':'等待安排'}},token)['id']==t['id']
    assert len(request('/api/state')['templates'])==1
    assert request('/api/templates/delete',{'id':t['id']},token)['ok']
    assert request('/api/state')['templates']==[]
    sys.path.insert(0,str(ROOT/'source/backend'))
    from clock_time import wall_time
    from photo_calendar import date_column
    from PIL import Image
    import io
    sample_day=wall_time('Europe/Amsterdam').date()
    pixels=request('/api/photo-date.png?timezone=Europe/Amsterdam')
    assert wall_time('Europe/Amsterdam').date()==sample_day
    assert Image.open(io.BytesIO(pixels)).convert('RGB').tobytes()==Image.open(io.BytesIO(date_column(sample_day)['png'])).convert('RGB').tobytes()
    report['frozen_small_type_pixels_match_source']=True
    assert len(config['gallery'])==16
    for item in config['gallery']:
        raw=request('/'+item['frame']);assert len(raw)==8000 and hashlib.sha256(raw).hexdigest()==item['sha256']
        assert request('/'+item['path']).startswith(b'\x89PNG')
        chosen=request('/api/builtin',{'path':item['path']},token)
        assert chosen==request('/api/builtin',{'path':item['path']},token)
    assert len(request('/api/state')['templates'])==16
    import base64
    from render import frame_png
    raw=request('/'+config['gallery'][0]['frame']);native_copy=request('/api/templates',{'title':'Native readback image','spec':{'kind':'image','native_frame':base64.b64encode(raw).decode()}},token)
    assert request('/api/templates/'+native_copy['id']+'/preview.png')==frame_png(raw)
    assert request('/api/templates/delete',{'id':native_copy['id']},token)['ok']
    report['native_readback_image_renderer_verified']=True
    assert config['firmware_versions']['ff001ff1']=='1.5.11'
    update=json.loads((delivery/'firmware/elink-bwr-1.5.11.elink-update.json').read_text())
    assert request('/api/ota/validate',{'package':update},token)['firmware_id']==update['firmware_id']
    b=request('/api/backup',{},token)
    with sqlite3.connect(b['path']) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    report['native_gallery_count']=len(config['gallery'])
    # Import/native DLL closure and adapter availability, without connecting/writing.
    if not args.no_scan:
        scan=request('/api/scan',{},token);report['scan_completed']=True;report['tag_count']=len(scan['devices'])
    else:report['scan_completed']=False
    duplicate=subprocess.run([str(exe),'--port',str(port),'--data',str(data)],cwd=folder,env=env,capture_output=True,text=True,timeout=10)
    (folder/'duplicate-stdout.log').write_text(duplicate.stdout,encoding='utf-8');(folder/'duplicate-stderr.log').write_text(duplicate.stderr,encoding='utf-8')
    assert duplicate.returncode==0 and 'already running' in duplicate.stdout
    conflicting=subprocess.run([str(exe),'--port',str(unused_port()),'--data',str(data)],cwd=folder,env=env,capture_output=True,timeout=10)
    assert conflicting.returncode!=0
    assert (delivery/'Start.cmd').read_bytes().isascii()
    launcher_env={**env,'LOCALAPPDATA':str(folder/'launcher-profile')}
    help_run=subprocess.run([os.environ['ComSpec'],'/d','/c','call',str(delivery/'Start.cmd'),'--help'],cwd=folder,env=launcher_env,input=b'',capture_output=True,timeout=10)
    assert help_run.returncode==0 and b'ERROR:' not in help_run.stdout
    console_path=folder/'launcher-conflict.txt'
    with console_path.open('wb') as console:
        launch=subprocess.Popen([os.environ['ComSpec'],'/d','/c','call',str(delivery/'Start.cmd'),'--port',str(port),'--data',str(folder/'other-data')],cwd=folder,env=launcher_env,stdin=subprocess.PIPE,stdout=console,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+15
            while b'Press any key' not in console_path.read_bytes():
                assert launch.poll() is None,'Launcher hid the startup error'
                if time.monotonic()>deadline:raise TimeoutError('Launcher did not display the startup error')
                time.sleep(.05)
            assert launch.poll() is None
            launch.communicate(b'\r\n',timeout=5)
            assert launch.returncode!=0
        finally:
            if launch.poll() is None:launch.terminate();launch.wait(timeout=5)
    assert b'Closing only the browser tab' in console_path.read_bytes()
    assert b'WinError 10048' in (folder/'launcher-profile/ElinkManager/logs/startup.log').read_bytes()
    report['ascii_launcher_and_visible_port_conflict_verified']=True
    assert request('/api/state')['jobs']==[]
    ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    stop_script=delivery/'tools/Stop-Manager.ps1'
    assert stop_script.read_bytes().isascii() and (delivery/'Stop.cmd').read_bytes().isascii()
    def stop_manager(target_port):
        return subprocess.run([str(ps),'-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',str(stop_script),'-Port',str(target_port)],cwd=folder,env=env,capture_output=True,timeout=30)
    # A future private fixture locks controls without causing any Bluetooth work.
    with sqlite3.connect(data/'elink.sqlite3') as fixture:
        fixture.execute("INSERT INTO jobs(id,address,action,payload,status,created,updated,due) VALUES(?,?,?,?,?,?,?,?)",('launcher-guard','AA:BB:CC:DD:EE:01','probe','{}','queued',time.time(),time.time(),time.time()+86400))
    refused=stop_manager(port)
    assert refused.returncode==3 and b'tasks are still pending' in refused.stdout and process.poll() is None,refused.stdout
    with sqlite3.connect(data/'elink.sqlite3') as fixture:fixture.execute('DELETE FROM jobs WHERE id=?',('launcher-guard',))
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    class Pretender(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            raw=json.dumps({'backend':'bleak/windows','bundled_runtime':True,'version':'1.5.13','runtime_executable':str(exe)}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    other=ThreadingHTTPServer(('127.0.0.1',0),Pretender);other_thread=threading.Thread(target=other.serve_forever,daemon=True);other_thread.start()
    try:
        wrong=stop_manager(other.server_port)
        assert wrong.returncode==2 and b'identity does not match' in wrong.stdout,wrong.stdout
    finally:other.shutdown();other.server_close();other_thread.join(timeout=5)
    stopped=stop_manager(port)
    assert stopped.returncode==0 and b'Port '+str(port).encode()+b' is free' in stopped.stdout,stopped.stdout+stopped.stderr
    process.wait(timeout=10)
    with sqlite3.connect(data/'elink.sqlite3') as fixture:assert fixture.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    # Prove that the OS data lock and the old port are reusable after stopping.
    process=subprocess.Popen([str(exe),'--port',str(port),'--data',str(data)],cwd=folder,env=env,stdout=log,stderr=err)
    for _ in range(40):
        try:
            if request('/api/config')['version']=='1.5.13':break
        except OSError:time.sleep(.25)
    else:raise TimeoutError('Restart after Stop failed')
    assert len(request('/api/state')['templates'])==16
    report['stop_busy_and_identity_guards_verified']=True
    report['stop_then_restart_same_data_verified']=True
    report.update({'passed':True,'version':config['version'],'runtime_executable':config['runtime_executable'],'required_files_verified':True,'source_and_conda_path_not_required':True,'template_png_verified':True,'backup_integrity':'ok','ota_package_id':update['firmware_id'],'duplicate_start_verified':True,'single_data_writer_verified':True})
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=10)
    log.close();err.close()
    (folder/'smoke-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
