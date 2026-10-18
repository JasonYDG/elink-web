"""Elink Manager 1.5.8: loopback API, SQLite, actual BLE worker, no simulated fleet."""
import argparse,asyncio,base64,json,secrets,threading,time,uuid,re,signal,sys,os,webbrowser
import urllib.request
import socket
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from store import Store,snapshot,album_snapshot
from render import render
from gateway import Gateway,worker
from protocol import policy_packet,timing_packet
from data_lock import DataLock
from ota import validate_package
from clock_time import settings,dutch_zone
from builtin_gallery import gallery,native,entry as builtin_entry,resource as builtin_resource

VERSION='1.5.11'
SOURCE=Path(sys._MEIPASS)/'source' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
UI=SOURCE/'opendesign/mockups/elink-manager'
TOKENS=SOURCE/'opendesign/design-systems/elink-home/tokens/colors_and_type.css'

class LoopbackServer(ThreadingHTTPServer):
    allow_reuse_address=False
    def server_bind(self):
        if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()

class App:
    def __init__(self,data,port):
        self.store=Store(data/'elink.sqlite3');self.data=data;self.port=port
        self.token=secrets.token_hex(32);self.stop=threading.Event()
        self.worker_error=None;self.scanning=False
        self.loop=asyncio.new_event_loop();self.gateway=Gateway(self.store)
        self.thread=threading.Thread(target=self.run,name='elink-ble',daemon=True);self.thread.start()
    def run(self):
        asyncio.set_event_loop(self.loop)
        try:self.loop.run_until_complete(worker(self.store,self.gateway,self.stop))
        except Exception as exc:
            self.worker_error=str(exc);print('BLE worker stopped: '+str(exc),file=sys.stderr,flush=True)
        finally:self.loop.close()
    def scan(self):
        with self.store.lock:
            self.require_idle();self.scanning=True
        try:
            future=asyncio.run_coroutine_threadsafe(self.gateway.scan(),self.loop)
            try:return future.result(timeout=12)
            except Exception:
                future.cancel();raise
        finally:
            with self.store.lock:self.scanning=False
    def operation_state(self):
        with self.store.lock:
            count=self.store.rows("SELECT count(*) n FROM jobs WHERE status IN ('queued','waiting','running','awaiting_display')")[0]['n']
            pending=self.store.rows("SELECT count(*) n FROM reminders WHERE status='pending'")[0]['n']
            return {'busy':self.scanning or bool(count or pending),'scanning':self.scanning,'jobs':count,'pending_reminders':pending}
    def require_idle(self,allow_pending=False):
        state=self.operation_state()
        if state['scanning'] or state['jobs'] or (state['pending_reminders'] and not allow_pending):
            raise ValueError('屏幕操作尚未完成，请查看顶部执行进度；等待任务可先取消')
    def device_change(self,fn,*args,allow_pending=False,**kwargs):
        with self.store.lock:
            self.require_idle(allow_pending);return fn(*args,**kwargs)
    def cancel_pending_reminder(self,ident):
        with self.store.lock:
            rows=self.store.rows('SELECT status,previous_token,job_id FROM reminders WHERE id=?',(ident,))
            if not rows or rows[0]['status']!='pending' or rows[0]['previous_token'] or rows[0]['job_id']:
                raise ValueError('只可立即取消尚未派发且不含旧设备记录的提醒')
            self.store.change_reminder(ident,delete=True)
    def register(self,address):
        address=str(address).strip().upper()
        if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}',address):raise ValueError('请输入完整蓝牙 MAC 地址')
        created=self.store.register(address)
        return {'address':address,'created':created}
    def enqueue(self,address,action,payload):
        with self.store.lock:
            self.require_idle();return self._enqueue(address,action,payload)
    def enqueue_batch(self,addresses,action,payload):
        if not isinstance(addresses,list) or not 1<=len(addresses)<=100 or any(not isinstance(a,str) for a in addresses):raise ValueError('请选择 1..100 台屏幕')
        with self.store.lock:
            self.require_idle();results=[]
            for address in dict.fromkeys(addresses):
                try:results.append({'address':address,'id':self._enqueue(address,action,payload)})
                except (ValueError,KeyError,TypeError) as exc:results.append({'address':address,'error':str(exc)})
            return results
    def _enqueue(self,address,action,payload):
        if not self.thread.is_alive():raise ValueError('设备后台未运行，请保存日志并重启管理端：'+str(self.worker_error or 'stopped'))
        if not self.store.rows('SELECT address FROM devices WHERE address=?',(address,)):raise ValueError('请先扫描或登记设备')
        if action not in ('probe','sync','default','resume','calendar','settings','publish','photo_calendar','overview','ota','album','album_stop'):raise ValueError('未知动作')
        if self.store.rows("SELECT id FROM jobs WHERE address=? AND status IN ('queued','waiting','running','awaiting_display')",(address,)):
            raise ValueError('该设备已有未完成任务，请等待或取消等待中的任务')
        if action=='sync' and (not isinstance(payload,dict) or set(payload)-{'quiet'} or type(payload.get('quiet',False))!=bool):raise ValueError('校时设置不合法')
        if action=='settings':
            payload=settings(payload)
            policy_packet(payload.get('mode'),payload.get('full_every'))
            timing_packet(payload.get('refresh_minutes'),payload.get('advertise_minutes'),payload.get('window_seconds'))
        if action in ('resume','calendar'):
            if not isinstance(payload,dict) or set(payload)-{'clock_timezone','refresh_minutes'}:raise ValueError('页面设置不合法')
            config=settings(payload)
            timing_packet(config['refresh_minutes'],config['advertise_minutes'],config['window_seconds'])
        if action=='overview' and payload:raise ValueError('任务汇总不接受额外设置')
        if action in ('publish','photo_calendar'):
            if not isinstance(payload,dict) or set(payload)-{'template_id','photo_x'}:raise ValueError('图片设置不合法')
            payload=snapshot(self.store.template(payload['template_id']),photo=action=='photo_calendar',photo_x=payload.get('photo_x',42))
        if action=='album':payload=album_snapshot(self.store,payload)
        if action=='album_stop' and payload:raise ValueError('停止轮播不接受额外设置')
        if action=='ota':validate_package(payload['package'])
        if action in ('publish','photo_calendar','default','resume','calendar','overview','album','album_stop'):
            self.store.execute('UPDATE plans SET enabled=0 WHERE address=?',(address,))
        return self.store.queue(address,action,payload)

def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,data,kind='application/json'):
            if kind=='application/json':data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',kind+'; charset=utf-8' if kind.startswith(('text/','application/json')) else kind)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)
        def allowed(self,mutate=False):
            authority=f'127.0.0.1:{app.port}'
            if self.headers.get('Host')!=authority:
                self.reply(403,{'error':'仅允许本机 127.0.0.1 访问'});return False
            if mutate and (self.headers.get('Origin') not in (None,'http://'+authority) or self.headers.get('X-Elink-Token')!=app.token):
                self.reply(403,{'error':'页面已失效，请刷新控制台'});return False
            return True
        def do_GET(self):
            if not self.allowed():return
            path=urlsplit(self.path).path
            try:
                if path=='/api/config':return self.reply(200,{'version':VERSION,'gallery':gallery(),'firmware_versions':json.loads((UI/'firmware-versions.json').read_text('utf-8')),'token':app.token,'backend':'bleak/windows','data_directory':str(app.data),'firmware_validation':'candidate_pending_hardware','width':250,'height':122,'runtime_executable':sys.executable,'bundled_runtime':bool(getattr(sys,'frozen',False))})
                if path=='/api/state':
                    devs=app.store.rows('SELECT * FROM devices ORDER BY name,address')
                    for d in devs:
                        d['settings']=json.loads(d['settings']);d['state']=json.loads(d['state'])
                        d['preview']=app.store.display_preview(d['address'],d['state'])
                    jobs=app.store.rows("SELECT id,address,action,status,progress,error,receipt,created,updated,attempts,payload,phase FROM jobs WHERE status IN ('queued','waiting','running','awaiting_display') OR id IN (SELECT id FROM jobs ORDER BY created DESC LIMIT 80) ORDER BY (status IN ('queued','waiting','running','awaiting_display')) DESC,created DESC")
                    for j in jobs:
                        j['receipt']=json.loads(j['receipt']);p=json.loads(j.pop('payload'));j['sha256']=p.get('sha256')
                    return self.reply(200,{'devices':devs,'jobs':jobs,'templates':app.store.rows('SELECT id,title,spec,sha256,created FROM templates ORDER BY created DESC'),'plans':app.store.rows('SELECT * FROM plans'),'reminders':app.store.reminders(),'operation':app.operation_state(),'worker_alive':app.thread.is_alive(),'worker_error':app.worker_error})
                if path.startswith('/api/templates/') and path.endswith('/preview.png'):
                    row=app.store.template(path.split('/')[3]);return self.reply(200,render(json.loads(row['spec']))['png'],'image/png')
                if path=='/api/photo-date.png':
                    from photo_calendar import date_column
                    from clock_time import wall_time
                    from urllib.parse import parse_qs
                    zone=parse_qs(urlsplit(self.path).query).get('timezone',['local'])[0]
                    return self.reply(200,date_column(wall_time(zone).date())['png'],'image/png')
                if path.startswith('/api/jobs/') and path.endswith('/preview.png'):
                    rows=app.store.rows('SELECT payload FROM jobs WHERE id=?',(path.split('/')[3],))
                    if not rows:raise ValueError('任务不存在')
                    p=json.loads(rows[0]['payload']);return self.reply(200,base64.b64decode(p.get('display_png',p.get('png',''))),'image/png')
                files={'/':(UI/'index.html','text/html'),'/app.js':(UI/'app.js','text/javascript'),'/gallery.js':(UI/'gallery.js','text/javascript'),'/operation.js':(UI/'operation.js','text/javascript'),'/style.css':(UI/'style.css','text/css'),'/assets/tokens.css':(TOKENS,'text/css'),'/design-systems/elink-home/tokens/colors_and_type.css':(TOKENS,'text/css'),**{f'/page-{name}.png':(UI/f'page-{name}.png','image/png') for name in ('default','clock','calendar','reminders','photo-calendar')}}
                if path in files:
                    p,kind=files[path];return self.reply(200,p.read_bytes(),kind)
                picture=builtin_resource(path.lstrip('/'))
                if picture:return self.reply(200,picture.read_bytes(),'image/png' if picture.suffix=='.png' else 'application/octet-stream')
                self.reply(404,{'error':'未找到资源'})
            except (ValueError,KeyError) as exc:self.reply(400,{'error':str(exc)})
        def do_POST(self):
            if not self.allowed(True):return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=3_000_000:raise ValueError('请求体大小不合法')
                body=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
                if not isinstance(body,dict):raise ValueError('JSON 必须为对象')
                if path=='/api/scan':return self.reply(200,{'devices':app.scan()})
                if path=='/api/register':return self.reply(200,app.register(body['address']))
                if path=='/api/unregister':
                    address=str(body['address']).strip().upper()
                    app.device_change(app.store.unregister,address);app.gateway.devices.pop(address,None)
                    return self.reply(200,{'address':address,'ok':True})
                if path=='/api/preview':
                    frame=render(body['spec']);return self.reply(200,{'png':base64.b64encode(frame['png']).decode(),'sha256':frame['sha256'],'red_pixels':frame['red_pixels']})
                if path=='/api/ota/validate':
                    raw,_=validate_package(body['package'])
                    return self.reply(200,{'bytes':len(raw),'version':body['package'].get('version'),'firmware_id':body['package']['firmware_id'],'sha256':body['package']['sha256']})
                if path=='/api/builtin':
                    item=builtin_entry(body['path']);frame=native(item['path'])
                    with app.store.lock:
                        existing=app.store.rows("SELECT id FROM templates WHERE json_extract(spec,'$.builtin')=? LIMIT 1",(item['path'],))
                        ident=app.store.save_template(item['title'],{'kind':'image','builtin':item['path']},frame,existing[0]['id'] if existing else None)
                    return self.reply(200,{'id':ident,'sha256':frame['sha256']})
                if path=='/api/templates':
                    spec=body['spec'];frame=render(spec)
                    title=str(body.get('title','未命名模板')).strip()[:80] or '未命名模板'
                    ident=app.store.save_template(title,spec,frame,body.get('id'))
                    return self.reply(200,{'id':ident,'sha256':frame['sha256']})
                if path=='/api/templates/delete':
                    stopped=app.store.delete_template(body['id'])
                    return self.reply(200,{'ok':True,'stopped_plans':stopped})
                if path=='/api/jobs':return self.reply(202,{'id':app.enqueue(body['address'],body['action'],body.get('payload',{}))})
                if path=='/api/jobs/batch':return self.reply(202,{'results':app.enqueue_batch(body['addresses'],body['action'],body.get('payload',{}))})
                if path=='/api/cancel':
                    if not app.store.cancel(body['id']):raise ValueError('只可取消尚未执行的任务')
                    return self.reply(200,{'ok':True})
                if path=='/api/reminders/cancel-pending':
                    app.cancel_pending_reminder(body['id']);return self.reply(200,{'ok':True})
                if path=='/api/reminders':return self.reply(200,{'ids':app.device_change(app.store.save_reminder,body['addresses'],body['title'],body.get('body',''),body['due'],body.get('id'),body.get('options'))})
                if path in ('/api/reminders/delete','/api/reminders/complete'):
                    app.device_change(app.store.change_reminder,body['id'],delete=path.endswith('/delete'),allow_pending=True)
                    return self.reply(200,{'ok':True})
                if path=='/api/reminders/retry':
                    app.device_change(app.store.retry_reminder,body['id']);return self.reply(200,{'ok':True})
                if path=='/api/plans':
                    address=body['address']
                    interval=body['interval_minutes']
                    if type(interval)!=int or not 1<=interval<=10080:raise ValueError('更新间隔 1..10080 分钟')
                    if type(body.get('enabled'))!=bool:raise ValueError('enabled 必须为 true 或 false')
                    with app.store.lock:
                        app.require_idle()
                        app.store.template(body['template_id'])
                        if not app.store.rows('SELECT address FROM devices WHERE address=?',(address,)):raise ValueError('设备不存在')
                        app.store.execute('INSERT INTO plans VALUES(?,?,?,?,?) ON CONFLICT(address) DO UPDATE SET template_id=excluded.template_id,interval_minutes=excluded.interval_minutes,next_due=excluded.next_due,enabled=excluded.enabled',(address,body['template_id'],interval,time.time()+interval*60,int(bool(body.get('enabled',False)))))
                    return self.reply(200,{'ok':True})
                if path=='/api/backup':
                    ident='elink-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.sqlite3'
                    folder=app.data/'backups';folder.mkdir(exist_ok=True);app.store.backup(folder/ident)
                    return self.reply(200,{'path':str(folder/ident)})
                self.reply(404,{'error':'未知 API'})
            except (ValueError,KeyError,TypeError) as exc:self.reply(400,{'error':str(exc)})
            except Exception as exc:self.reply(500,{'error':str(exc)})
    return Handler

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18765)
    parser.add_argument('--open',action='store_true',help='Open the local control page after binding')
    default_data=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ElinkManager/data' if getattr(sys,'frozen',False) else SOURCE.parent/'runtime/data'
    parser.add_argument('--data',type=Path,default=default_data);args=parser.parse_args()
    args.data=args.data.resolve();args.data.mkdir(parents=True,exist_ok=True)
    if not UI.joinpath('index.html').exists() or not TOKENS.exists():raise RuntimeError('控制台资源未闭合，拒绝启动')
    for item in gallery():
        native(item['path'])
        if not builtin_resource(item['path']).is_file():raise RuntimeError('内置图片预览资源缺失')
    dutch_zone() # Validate the bundled TZif before accepting any clock jobs.
    # Bind before opening/migrating data: duplicate starts must not mark active jobs interrupted.
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/config',timeout=2) as response:existing=json.load(response)
        if Path(existing['runtime_executable']).resolve()==Path(sys.executable).resolve() and Path(existing['data_directory']).resolve()==args.data and existing['version']==VERSION:
            if args.open:webbrowser.open(f'http://127.0.0.1:{args.port}')
            print('Elink Manager already running; opened existing control page.',flush=True);return
    except (OSError,ValueError,KeyError):pass
    try:server=LoopbackServer(('127.0.0.1',args.port),BaseHTTPRequestHandler)
    except OSError:
        raise RuntimeError(f'端口 {args.port} 已被其他程序占用；请关闭旧管理端或使用 --port 指定不同端口。')
    try:ownership=DataLock(args.data/'backend.lock')
    except Exception:
        server.server_close();raise
    app=App(args.data,args.port);server.RequestHandlerClass=handler(app)
    print(f'Elink Manager {VERSION} http://127.0.0.1:{args.port} data={args.data}',flush=True)
    if args.open:threading.Timer(.5,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        app.stop.set();server.server_close();app.thread.join(timeout=30)
        if app.thread.is_alive():print('BLE transaction still settling; interrupted job marked unknown on next start.',flush=True)
        else:app.store.db.close()
        ownership.close()
if __name__=='__main__':main()
