import sqlite3,json,time,uuid,threading,math,datetime,base64
from contextlib import closing
from pathlib import Path

def now():return time.time()
def snapshot(template,photo=False,photo_x=42):
    from render import render,photo_calendar_frame
    import base64
    frame=render(json.loads(template['spec']))
    if photo:
        if json.loads(template['spec']).get('kind')!='image':raise ValueError('图片日历只能使用图片')
        frame=photo_calendar_frame(frame['frame'],photo_x)
    return {'template_id':template['id'],**({'photo_x':photo_x} if photo else {}),'kind':json.loads(template['spec']).get('kind','notice'),'frame':base64.b64encode(frame['frame']).decode(),
            'png':base64.b64encode(frame['png']).decode(),'sha256':frame['sha256']}

def album_snapshot(store,value):
    if not isinstance(value,dict) or set(value)!={'items','mode','interval_minutes'}:raise ValueError('图库设置不合法')
    if value['mode'] not in ('image','calendar') or type(value['interval_minutes']) is not int or not 60<=value['interval_minutes']<=10080:raise ValueError('换图间隔须为 1 小时至 7 天')
    items=value['items']
    if not isinstance(items,list) or not 1<=len(items)<=7:raise ValueError('屏幕图库请选择 1–7 张图片')
    result=[];seen=set()
    for item in items:
        if not isinstance(item,dict) or set(item)!={'template_id','photo_x'} or not isinstance(item['template_id'],str) or item['template_id'] in seen or type(item['photo_x']) is not int or not 0<=item['photo_x']<=84:raise ValueError('图库图片或取景位置不合法')
        seen.add(item['template_id']);frame=snapshot(store.template(item['template_id']))
        if frame['kind']!='image':raise ValueError('屏幕图库仅接受图片')
        result.append({**frame,'photo_x':item['photo_x']})
    return {**value,'items':result}

class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock()
        self.db=sqlite3.connect(self.path,check_same_thread=False);self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS devices(address TEXT PRIMARY KEY,name TEXT NOT NULL,settings TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT '{}',last_seen REAL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS templates(id TEXT PRIMARY KEY,title TEXT NOT NULL,spec TEXT NOT NULL,png BLOB NOT NULL,frame BLOB NOT NULL,sha256 TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,address TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,error TEXT,receipt TEXT NOT NULL DEFAULT '{}',created REAL NOT NULL,updated REAL NOT NULL,due REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS plans(address TEXT PRIMARY KEY,template_id TEXT NOT NULL,interval_minutes INTEGER NOT NULL,next_due REAL NOT NULL,enabled INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY,address TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,due REAL NOT NULL,status TEXT NOT NULL DEFAULT 'pending',token INTEGER NOT NULL,previous_token INTEGER NOT NULL DEFAULT 0,job_id TEXT,delete_after INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL);
        ''')
        if 'phase' not in {r[1] for r in self.db.execute('PRAGMA table_info(jobs)')}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN phase TEXT NOT NULL DEFAULT ''")
        columns={r[1] for r in self.db.execute('PRAGMA table_info(reminders)')}
        for column,kind in (('options',"TEXT NOT NULL DEFAULT '{}'"),('next_due','REAL'),('last_due','REAL')):
            if column not in columns:self.db.execute('ALTER TABLE reminders ADD COLUMN '+column+' '+kind)
        # Interrupted hardware writes cannot be silently claimed/retried as success.
        self.db.execute("UPDATE jobs SET status='delivery_unknown',error='管理端中断；请读取设备状态核对。' WHERE status IN ('running','awaiting_display')")
        self.db.commit()
    def execute(self,sql,args=()):
        with self.lock:
            c=self.db.execute(sql,args);self.db.commit();return c
    def rows(self,sql,args=()):
        with self.lock:return [dict(x) for x in self.db.execute(sql,args).fetchall()]
    def device(self,address,name):
        self.execute('INSERT INTO devices(address,name,last_seen,updated) VALUES(?,?,?,?) ON CONFLICT(address) DO UPDATE SET name=excluded.name,last_seen=excluded.last_seen,updated=excluded.updated',(address,name,now(),now()))
    def register(self,address):
        # Manual registration is not a sighting and must not replace discovered metadata.
        return self.execute('INSERT INTO devices(address,name,updated) VALUES(?,?,?) ON CONFLICT(address) DO NOTHING',(address,'ELINK-BWR-'+address.replace(':','')[-6:],now())).rowcount==1
    def unregister(self,address):
        with self.lock:
            if not self.rows('SELECT address FROM devices WHERE address=?',(address,)):raise ValueError('设备未登记')
            if self.rows("SELECT id FROM jobs WHERE address=? AND status IN ('running','awaiting_display')",(address,)):
                raise ValueError('设备任务正在执行，请结束后再取消登记')
            if self.rows("SELECT id FROM reminders WHERE address=? AND (status IN ('dispatched','armed','needs_sync','cancelling') OR (status='pending' AND previous_token!=0))",(address,)):
                raise ValueError('标签上还有离线日程，请先删除提醒并等设备确认，再取消登记')
            with self.db:
                self.db.execute("UPDATE jobs SET status='cancelled',error='设备已取消登记',updated=? WHERE address=? AND status IN ('queued','waiting')",(now(),address))
                self.db.execute('DELETE FROM plans WHERE address=?',(address,))
                self.db.execute("UPDATE reminders SET status='cancelled',updated=? WHERE address=? AND status IN ('pending','dispatched')",(now(),address))
                self.db.execute('DELETE FROM devices WHERE address=?',(address,))
    def state(self,address,state):
        with self.lock, self.db:
            self.db.execute('UPDATE devices SET state=?,updated=? WHERE address=?',(json.dumps(state,ensure_ascii=False),now(),address))
            if state.get('offline_reminders') and state.get('time_initialized') is False:
                self.db.execute("UPDATE reminders SET status='needs_sync',updated=? WHERE address=? AND status='armed'",(now(),address))
    def queue(self,address,action,payload):
        ident=uuid.uuid4().hex
        self.execute('INSERT INTO jobs(id,address,action,payload,status,created,updated,due) VALUES(?,?,?,?,?,?,?,?)',(ident,address,action,json.dumps(payload,ensure_ascii=False),'queued',now(),now(),now()))
        return ident
    def update_job(self,ident,**fields):
        allowed={'status','progress','error','receipt','due','attempts','payload','phase'}
        if not fields.keys()<=allowed:raise ValueError('Invalid job field')
        for k in ('receipt','payload'):
            if k in fields:fields[k]=json.dumps(fields[k],ensure_ascii=False)
        fields['updated']=now()
        self.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),ident))
    def save_reminder(self,addresses,title,body,due,ident=None,options=None):
        from protocol import reminder_options
        config=json.dumps(reminder_options(options))
        if not isinstance(addresses,list) or not addresses or len(addresses)>100 or any(not isinstance(a,str) for a in addresses):raise ValueError('请选择提醒屏幕')
        if not isinstance(title,str) or not title.strip() or len(title)>80:raise ValueError('提醒标题须为 1..80 个字')
        if not isinstance(body,str) or len(body)>240:raise ValueError('提醒内容最多 240 个字')
        if type(due) not in (int,float) or not math.isfinite(due) or not now()<due<2587680000:raise ValueError('请选择将来、2051 年之前的提醒时间')
        addresses=list(dict.fromkeys(addresses));saved=[]
        with self.lock:
            for address in addresses:
                if not self.rows('SELECT address FROM devices WHERE address=?',(address,)):raise ValueError('提醒屏幕未登记：'+address)
                if ident is None and len(self.rows("SELECT id FROM reminders WHERE address=? AND status NOT IN ('completed','cancelled','displayed')",(address,)))>=7:raise ValueError('每台屏幕最多 7 条等待提醒，先完成或删除日程')
            old=None
            if ident is not None:
                if not isinstance(ident,str):raise ValueError('提醒编号不合法')
                rows=self.rows('SELECT r.*,j.status AS job_status FROM reminders r LEFT JOIN jobs j ON j.id=r.job_id WHERE r.id=?',(ident,))
                if not rows or rows[0]['status'] not in ('pending','armed','needs_sync','displayed') or rows[0]['job_status'] in ('running','awaiting_display') or addresses!=[rows[0]['address']]:raise ValueError('提醒正在处理，或不是原屏幕日程')
                old=rows[0]
                if len(self.rows("SELECT id FROM reminders WHERE address=? AND id!=? AND status NOT IN ('completed','cancelled','displayed')",(old['address'],ident)))>=7:raise ValueError('每台屏幕最多 7 条等待提醒')
            with self.db:
                for address in addresses:
                    key=ident or uuid.uuid4().hex;token=int(uuid.uuid4().hex[:8],16) or 1
                    if old:
                        self.db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=? AND status IN ('queued','waiting')",(now(),old['job_id']))
                        self.db.execute("UPDATE reminders SET title=?,body=?,due=?,status='pending',token=?,previous_token=?,job_id=NULL,updated=? WHERE id=?",(title.strip(),body,due,token,(old['previous_token'] or (old['token'] if old['status']!='pending' else 0)),now(),key))
                    else:self.db.execute('INSERT INTO reminders(id,address,title,body,due,token,created,updated) VALUES(?,?,?,?,?,?,?,?)',(key,address,title.strip(),body,due,token,now(),now()))
                    self.db.execute('UPDATE reminders SET options=?,next_due=NULL,last_due=NULL WHERE id=?',(config,key))
                    saved.append(key)
        return saved
    def change_reminder(self,ident,delete=False):
        if not isinstance(ident,str):raise ValueError('提醒编号不合法')
        with self.lock:
            rows=self.rows('SELECT r.*,j.status AS job_status FROM reminders r LEFT JOIN jobs j ON j.id=r.job_id WHERE r.id=?',(ident,))
            if not rows:raise ValueError('提醒不存在')
            r=rows[0]
            if r['job_status'] in ('running','awaiting_display') or r['status']=='cancelling':raise ValueError('提醒正在处理，请完成后再操作')
            with self.db:
                self.db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=? AND status IN ('queued','waiting')",(now(),r['job_id']))
                if r['status'] in ('completed','cancelled') or (r['status']=='pending' and not r['previous_token']):
                    if delete:self.db.execute('DELETE FROM reminders WHERE id=?',(ident,))
                    else:self.db.execute("UPDATE reminders SET status='completed',updated=? WHERE id=?",(now(),ident))
                else:
                    job=uuid.uuid4().hex;payload={'operation':'cancel','reminder_id':ident,'token':r['token'],'previous_token':r['previous_token']}
                    self.db.execute('INSERT INTO jobs(id,address,action,payload,status,created,updated,due) VALUES(?,?,?,?,?,?,?,?)',(job,r['address'],'reminder',json.dumps(payload),'queued',now(),now(),now()))
                    self.db.execute("UPDATE reminders SET status='cancelling',job_id=?,delete_after=?,updated=? WHERE id=?",(job,int(delete),now(),ident))
    def dispatch_reminders(self):
        # Store pixels ahead of time. The screen, not this worker, fires the alarm.
        from render import render
        with self.lock:
            for r in self.rows("SELECT * FROM reminders WHERE status='pending' ORDER BY due,created"):
                if self.rows("SELECT id FROM jobs WHERE address=? AND status IN ('queued','waiting','running','awaiting_display')",(r['address'],)):continue
                config=json.loads(r['options']);zone=datetime.timezone(datetime.timedelta(seconds=config.get('utc_offset',int(datetime.datetime.now().astimezone().utcoffset().total_seconds()))));stamp=datetime.datetime.fromtimestamp(r['due'],zone).strftime('%Y-%m-%d %H:%M')
                if config.get('repeat_mask'):stamp=('每天' if config['repeat_mask']==127 else '重复')+datetime.datetime.fromtimestamp(r['due'],zone).strftime(' %H:%M')
                frame=render({'kind':'notice','title':r['title'],'body':r['body'] or r['title'],'footer':stamp,'red':True})
                key=uuid.uuid4().hex;payload={'operation':'install','reminder_id':r['id'],'token':r['token'],'previous_token':r['previous_token'],'due':int(r['due']),
                    'title':r['title'],'options':json.loads(r['options']),'kind':'notice','frame':base64.b64encode(frame['frame']).decode(),'png':base64.b64encode(frame['png']).decode(),'sha256':frame['sha256']}
                with self.db:
                    self.db.execute('INSERT INTO jobs(id,address,action,payload,status,created,updated,due) VALUES(?,?,?,?,?,?,?,?)',(key,r['address'],'reminder',json.dumps(payload,ensure_ascii=False),'queued',now(),now(),now()))
                    self.db.execute("UPDATE reminders SET status='dispatched',job_id=?,updated=? WHERE id=?",(key,now(),r['id']))
    def retry_reminder(self,ident):
        if not isinstance(ident,str) or not ident:raise ValueError('提醒编号不合法')
        with self.lock:
            rows=self.rows('SELECT j.id,j.status FROM reminders r JOIN jobs j ON j.id=r.job_id WHERE r.id=?',(ident,))
            if not rows or rows[0]['status'] not in ('failed','cancelled','delivery_unknown'):raise ValueError('此提醒无需重试')
            self.update_job(rows[0]['id'],status='queued',due=now(),error=None,phase='重新核对标签日程')
    def reminder_result(self,job,receipt):
        payload=json.loads(job['payload'])
        with self.lock, self.db:
            self.db.execute("UPDATE jobs SET status='succeeded',progress=100,receipt=?,error=NULL,updated=? WHERE id=?",(json.dumps(receipt,ensure_ascii=False),now(),job['id']))
            if payload['operation']=='cancel':
                row=self.rows('SELECT delete_after FROM reminders WHERE job_id=?',(job['id'],))
                if row and row[0]['delete_after']:self.db.execute('DELETE FROM reminders WHERE job_id=?',(job['id'],))
                else:self.db.execute("UPDATE reminders SET status='completed',updated=? WHERE job_id=?",(now(),job['id']))
            else:self.db.execute("UPDATE reminders SET status=?,previous_token=0,next_due=?,last_due=?,updated=? WHERE job_id=?",('displayed' if receipt.get('slot_state')==252 else 'armed',receipt.get('next_due'),receipt.get('last_due') if receipt.get('last_due',0)>1 else None,now(),job['id']))
    def reminders(self):
        return self.rows("SELECT r.*,j.status AS job_status,j.error AS job_error,j.phase AS job_phase FROM reminders r LEFT JOIN jobs j ON j.id=r.job_id ORDER BY (r.status NOT IN ('completed','cancelled')) DESC,r.due DESC")
    def reconcile_reminders(self,address,slots):
        for slot in slots:
            if slot.get('metadata_ready') and slot['clock_ready']:
                self.execute('UPDATE reminders SET next_due=?,last_due=? WHERE address=? AND token=?',(slot['next_due'],slot['last_due'] if slot['last_due']>1 else None,address,slot['token']))
            if slot['state']==254:self.execute("UPDATE reminders SET status=?,updated=? WHERE address=? AND token=? AND status IN ('armed','needs_sync')",('armed' if slot['clock_ready'] else 'needs_sync',now(),address,slot['token']))
            if slot['state']==252:self.execute("UPDATE reminders SET status='displayed',updated=? WHERE address=? AND token=? AND status IN ('armed','needs_sync','dispatched')",(now(),address,slot['token']))
            elif slot['state']==248:self.execute("UPDATE reminders SET status='cancelled',updated=? WHERE address=? AND token=? AND status IN ('armed','needs_sync')",(now(),address,slot['token']))
    def claim(self,ident):
        with self.lock:
            c=self.db.execute("UPDATE jobs SET status='running',progress=0,error=NULL,phase='等待蓝牙连接',updated=? WHERE id=? AND status IN ('queued','waiting')",(now(),ident))
            self.db.commit();return c.rowcount==1
    def cancel(self,ident):
        with self.lock:
            c=self.db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=? AND status IN ('queued','waiting')",(now(),ident))
            self.db.commit();return c.rowcount==1
    def template(self,ident):
        if not isinstance(ident,str) or not ident:raise ValueError('模板编号不合法')
        rows=self.rows('SELECT * FROM templates WHERE id=?',(ident,))
        if not rows:raise ValueError('模板不存在')
        return rows[0]
    def save_template(self,title,spec,frame,ident=None):
        with self.lock:
            if ident is not None:
                if not isinstance(ident,str):raise ValueError('模板编号不合法')
                self.template(ident)
                self.execute('UPDATE templates SET title=?,spec=?,png=?,frame=?,sha256=? WHERE id=?',
                    (title,json.dumps(spec,ensure_ascii=False),frame['png'],frame['frame'],frame['sha256'],ident))
            else:
                ident=uuid.uuid4().hex
                self.execute('INSERT INTO templates VALUES(?,?,?,?,?,?,?)',
                    (ident,title,json.dumps(spec,ensure_ascii=False),frame['png'],frame['frame'],frame['sha256'],now()))
            return ident
    def delete_template(self,ident):
        with self.lock:
            self.template(ident)
            plans=self.rows('SELECT address FROM plans WHERE template_id=?',(ident,))
            with self.db:
                self.db.execute('DELETE FROM plans WHERE template_id=?',(ident,))
                self.db.execute('DELETE FROM templates WHERE id=?',(ident,))
            # Queued and historical deliveries have independent pixel snapshots.
            return len(plans)
    def display_preview(self,address,state):
        if state.get('busy') or state.get('error') or state.get('preview_error'):return None
        rows=self.rows("""SELECT id,action FROM jobs WHERE address=? AND action IN ('publish','photo_calendar','reminder','overview','album','probe') AND status='succeeded'
            AND json_extract(receipt,'$.generation_after')=? AND json_extract(receipt,'$.transfer_id')=?
            AND json_extract(receipt,'$.firmware_id')=? AND (json_extract(payload,'$.display_png') IS NOT NULL OR json_extract(payload,'$.png') IS NOT NULL)
            AND (action!='probe' OR (json_extract(receipt,'$.display_mode')=? AND json_extract(receipt,'$.pixel_readback_verified')=1))
            ORDER BY created DESC LIMIT 1""",(address,state.get('display_generation'),state.get('transfer_id'),state.get('firmware_id'),state.get('display_mode')))
        if rows:return {'url':'/api/jobs/'+rows[0]['id']+'/preview.png','label':'设备像素读回' if rows[0]['action']=='probe' else '最近确认发送的画面'}
        return None
    def backup(self,target):
        with self.lock:
            with closing(sqlite3.connect(target)) as dst:self.db.backup(dst)
        with closing(sqlite3.connect(target)) as check:
            if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity failed')
