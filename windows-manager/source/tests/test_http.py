import sys,base64,unittest,tempfile,threading,json,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import App,handler
from http.server import ThreadingHTTPServer

class Http(unittest.TestCase):
    def test_real_api_auth_templates_backup_and_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            http=ThreadingHTTPServer(('127.0.0.1',0),None);port=http.server_port
            app=App(Path(folder),port);http.RequestHandlerClass=handler(app)
            thread=threading.Thread(target=http.serve_forever);thread.start()
            root=f'http://127.0.0.1:{port}'
            def request(path,body=None,token=None,origin=None,host=None):
                headers={}
                if token:headers['X-Elink-Token']=token
                if origin:headers['Origin']=origin
                if host:headers['Host']=host
                raw=None if body is None else json.dumps(body).encode()
                with urllib.request.urlopen(urllib.request.Request(root+path,data=raw,headers=headers),timeout=5) as r:
                    b=r.read();return json.loads(b) if r.headers['Content-Type'].startswith('application/json') else b
            try:
                c=request('/api/config');token=c['token'];self.assertEqual(c['version'],'1.5.14')
                app.stop.set();app.thread.join(5) # HTTP schedule CRUD must never trigger real hardware writes.
                self.assertIn(b'Elink',request('/'));self.assertIn(b'--accent',request('/assets/tokens.css'))
                page=request('/').decode()
                for name in ('default','resume','calendar','reminder','publish'):self.assertIn('name="page" value="'+name+'"',page)
                self.assertNotIn('恢复设备时钟',page)
                for name in ('default','clock','calendar','reminders'):self.assertTrue(request('/page-'+name+'.png').startswith(b'\x89PNG'))
                for kw in ({},{'token':token,'origin':'https://attacker.test'},{'token':token,'host':'attacker.test'}):
                    with self.assertRaises(urllib.error.HTTPError) as error:request('/api/register',{'address':'18:BC:5A:6B:91:A7'},**kw)
                    self.assertEqual(error.exception.code,403)
                t=request('/api/templates',{'title':'My calendar','spec':{'kind':'calendar','title':'日历','body':'{date}\n{weekday}'}},token)
                self.assertTrue(request('/api/templates/'+t['id']+'/preview.png').startswith(b'\x89PNG'))
                app.store.execute('UPDATE templates SET png=? WHERE id=?',(b'old-renderer-cache',t['id']))
                self.assertTrue(request('/api/templates/'+t['id']+'/preview.png').startswith(b'\x89PNG'),'Saved templates must preview with the current renderer after a font upgrade')
                self.assertTrue(request('/api/register',{'address':'18:BC:5A:6B:91:A7'},token)['created'])
                app.store.device('18:BC:5A:6B:91:A7','actual-advertisement-name')
                self.assertFalse(request('/api/register',{'address':' 18:bc:5a:6b:91:a7 '},token)['created'])
                state=request('/api/state');self.assertEqual(len(state['devices']),1);self.assertEqual(len(state['templates']),1)
                self.assertEqual(state['devices'][0]['name'],'actual-advertisement-name')
                b=request('/api/backup',{},token);self.assertTrue(Path(b['path']).exists())
                self.assertEqual(request('/api/state')['jobs'],[])
                original=app.store.template(t['id'])
                updated=request('/api/templates',{'id':t['id'],'title':'Edited calendar','spec':{'kind':'notice','title':'编辑后','body':'同一模板'}},token)
                self.assertEqual(updated['id'],t['id']);self.assertEqual(len(request('/api/state')['templates']),1)
                self.assertEqual(app.store.template(t['id'])['created'],original['created'])
                with self.assertRaises(urllib.error.HTTPError):request('/api/templates',{'id':'missing','spec':{'kind':'notice'}},token)
                from store import snapshot
                content=snapshot(app.store.template(t['id']))
                # Install a completed fixture atomically; never let the real worker claim it.
                with app.store.lock:
                    ident=app.store.queue('18:BC:5A:6B:91:A7','publish',content)
                    app.store.update_job(ident,status='succeeded',receipt={'generation_after':7,'transfer_id':42,'firmware_id':'test-id'})
                app.store.state('18:BC:5A:6B:91:A7',{'display_mode':2,'display_generation':7,'transfer_id':42,'firmware_id':'test-id'})
                state=request('/api/state');self.assertEqual(state['devices'][0]['preview']['url'],'/api/jobs/'+ident+'/preview.png')
                frozen=request('/api/jobs/'+ident+'/preview.png')
                app.store.execute('INSERT INTO plans VALUES(?,?,?,?,?)',('18:BC:5A:6B:91:A7',t['id'],5,9999999999,1))
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/templates/delete',{'id':t['id']})
                self.assertEqual(error.exception.code,403)
                self.assertEqual(request('/api/templates/delete',{'id':t['id']},token)['stopped_plans'],1)
                state=request('/api/state');self.assertEqual(state['templates'],[]);self.assertEqual(state['plans'],[])
                self.assertEqual(request('/api/jobs/'+ident+'/preview.png'),frozen)
                app.store.state('18:BC:5A:6B:91:A7',{'display_mode':2,'display_generation':8,'transfer_id':42,'firmware_id':'test-id'})
                self.assertIsNone(request('/api/state')['devices'][0]['preview'],'A stale announcement must not be presented as the confirmed screen')
                app.store.state('18:BC:5A:6B:91:A7',{'display_mode':0})
                self.assertIsNone(request('/api/state')['devices'][0]['preview'])
                read=app.store.queue('18:BC:5A:6B:91:A7','probe',{'display_png':base64.b64encode(frozen).decode()})
                app.store.update_job(read,status='succeeded',receipt={'display_mode':7,'generation_after':8,'transfer_id':0,'firmware_id':'read-id','pixel_readback_verified':True})
                app.store.state('18:BC:5A:6B:91:A7',{'display_mode':7,'display_generation':8,'transfer_id':0,'firmware_id':'read-id'})
                actual_preview=request('/api/state')['devices'][0]['preview'];self.assertEqual(actual_preview['label'],'设备像素读回')
                self.assertEqual(request(actual_preview['url']),frozen)
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/unregister',{'address':'18:BC:5A:6B:91:A7'})
                self.assertEqual(error.exception.code,403)
                import time
                schedule={'addresses':['18:BC:5A:6B:91:A7'],'title':'提醒','body':'离线日程','due':int(time.time()+3600)}
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/reminders',schedule)
                self.assertEqual(error.exception.code,403)
                reminder=request('/api/reminders',schedule,token)['ids'][0]
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/reminders',{**schedule,'id':reminder,'title':'修改日程'},token)
                self.assertEqual(error.exception.code,400)
                self.assertEqual(request('/api/state')['reminders'][0]['title'],'提醒')
                request('/api/reminders/delete',{'id':reminder},token);self.assertEqual(request('/api/state')['reminders'],[])
                request('/api/unregister',{'address':'18:BC:5A:6B:91:A7'},token)
                state=request('/api/state');self.assertEqual(state['devices'],[]);self.assertEqual(len(state['templates']),0)
                self.assertEqual(len(c['gallery']),16)
                for item in c['gallery']:
                    self.assertTrue(request('/'+item['path']).startswith(b'\x89PNG'))
                    self.assertEqual(len(request('/'+item['frame'])),8000)
                    first=request('/api/builtin',{'path':item['path']},token)
                    self.assertEqual(first,request('/api/builtin',{'path':item['path']},token))
                    self.assertEqual(first['sha256'],item['sha256'])
                self.assertEqual(len(request('/api/state')['templates']),16)
                for path in ('../config.json','config.json','image/not-in-gallery.png'):
                    with self.assertRaises(urllib.error.HTTPError):request('/api/builtin',{'path':path},token)
                self.assertIn(b'initGallery',request('/gallery.js'))
                self.assertIn(b'updateOperationDialog',request('/operation.js'))
                self.assertTrue(request('/api/photo-date.png?timezone=Europe/Amsterdam').startswith(b'\x89PNG'))
                with self.assertRaises(urllib.error.HTTPError):request('/api/photo-date.png?timezone=bad')
                self.assertTrue(request('/page-photo-calendar.png').startswith(b'\x89PNG'))
            finally:
                http.shutdown();thread.join();http.server_close();app.stop.set();app.thread.join(5);app.store.db.close()
if __name__=='__main__':unittest.main()
