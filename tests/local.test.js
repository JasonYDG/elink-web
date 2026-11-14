"use strict";
// The real local engine runs against an in-memory IndexedDB boundary; browser persistence is also tested in the UI.
const test=require("node:test"),assert=require("node:assert/strict"),vm=require("node:vm"),fs=require("node:fs"),path=require("node:path"),P=require("../protocol.js");
const root=path.join(__dirname,".."),address="AA:BB:CC:DD:EE:01",frame=Uint8Array.from(fs.readFileSync(path.join(root,"image/13-space-rabbit.bin"))),ident=n=>n.toString(16).padStart(32,"0");
function workspace(){return {format:"elink-web",schema:1,devices:[{address,name:"ELINK-BWR-DDEE01",settings:P.settings(),state:{display_mode:2},updated:1}],templates:[],jobs:[],plans:[],reminders:[]};}
async function harness(initial=workspace(),execute=async()=>({})){
    const saved=new Map([["current",structuredClone(initial)]]);
    const db={transaction(){const t={};t.objectStore=()=>({get(key){const r={};queueMicrotask(()=>{r.result=structuredClone(saved.get(key));r.onsuccess();});return r;},put(value,key){saved.set(key,structuredClone(value));queueMicrotask(()=>t.oncomplete?.());}});return t;}};
    const context=vm.createContext({ELinkProtocol:P,ELinkRenderer:{png:()=>"canonical-png",render:async spec=>{const b=spec.test_frame||frame;return {frame:P.bytes64(b),sha256:await P.sha256(b),png:"canonical-png"};}},ELinkBLE:{execute},console,crypto,structuredClone,Uint32Array,Promise,Error,Date,Math,JSON,Set,Map,Object,Array,Number,String,URL,Blob,setTimeout,window:{isSecureContext:true,addEventListener(){}},location:{href:"https://example.test/elink-web/"},navigator:{locks:{request:async(name,options,handler)=>handler({name})}},indexedDB:{open(){const r={};queueMicrotask(()=>{r.result=db;r.onsuccess();});return r;}},fetch:async url=>String(url).endsWith(".bin")?{ok:true,arrayBuffer:async()=>Uint8Array.from(fs.readFileSync(path.join(root,url))).buffer}:{json:async()=>JSON.parse(fs.readFileSync(path.join(root,"config.json"),"utf8"))},portable:{address,device:{gatt:{connected:true}}}});
    vm.runInContext(fs.readFileSync(path.join(root,"local.js"),"utf8"),context);const local=vm.runInContext("ELinkLocal",context);await local.ready;return {local,saved,context};
}
test("queued image stays immutable after editing and deleting its template",async()=>{
    const w=workspace(),sha=await P.sha256(frame);w.templates.push({id:ident(1),title:"original",spec:'{"kind":"image"}',frame:P.bytes64(frame),sha256:sha,png:"original",created:1});const {local}=await harness(w);
    const j=await local.api("/api/jobs",{address,action:"publish",payload:{template_id:ident(1)}}),changed=frame.slice();changed[0]^=1;
    await local.api("/api/templates",{id:ident(1),title:"edited",spec:{kind:"image",test_frame:changed}});await local.api("/api/templates/delete",{id:ident(1)});
    assert.equal(local.job(j.id).payload.sha256,sha);assert.deepEqual(P.decode64(local.job(j.id).payload.frame),frame);assert.equal(local.summary().templates.length,0);
});

test("upgrading the web app preserves records and requests a fresh capability read",async()=>{
    const w=workspace();w.devices[0].state={protocol:1,firmware_id:"fde89808",display_mode:8,display_generation:2};const h=await harness(w);
    assert.equal(h.local.device(address).state.firmware_id,"fde89808");assert.equal(h.local.device(address).state.capabilities_stale,true);assert.equal(h.saved.get("current").app_version,"1.1.15");
    await h.local.updateState(address,{protocol:1,firmware_id:"fde89808",photo_calendar_wide:true});assert.equal(h.local.device(address).state.capabilities_stale,undefined);
});

test("readback restores native originals and duplicate pictures to distinct editable slots",async()=>{
    const h=await harness(),other=frame.slice();other[0]^=1;const a={capacity:7,count:2,crc32:[P.crc32(frame),P.crc32(other)],photo_x:[10,60],sequence:3,mode:1,enabled:true,interval_minutes:1440};
    await assert.rejects(h.local.api("/api/builtin",{path:"image/13-space-rabbit.png"}),/内置图片不存在/);
    const restored=await h.local.restoreAlbum(a,[frame,other]);assert.equal(restored.editable,true);assert.equal(restored.items[0].title,"月球小兔");assert.deepEqual(Array.from(h.local.albumMatches(restored)),Array.from(restored.items,i=>i.template_id));
    const copy=await h.local.restoreAlbum({...a,crc32:[P.crc32(frame),P.crc32(frame)]},[null,frame]);assert.notEqual(copy.items[0].template_id,copy.items[1].template_id);
    await h.local.updateState(address,{album_capacity:7,display_mode:8,album:copy});const payload={mode:"calendar",interval_minutes:1440,items:copy.items.map(i=>({template_id:i.template_id,photo_x:i.photo_x}))};
    const result=await h.local.api("/api/jobs",{address,action:"album",payload:{...payload,expected_sequence:3,max_image_writes:2}});const queued=h.local.job(result.id);assert.equal(queued.payload.items.length,2);assert.deepEqual(P.decode64(queued.payload.items[1].frame),frame);
    assert.equal(queued.payload.auto_rotate,false);
    await h.local.api("/api/templates/delete",{id:copy.items[1].template_id});assert.deepEqual(P.decode64(queued.payload.items[1].frame),frame);
    await h.local.api("/api/cancel",{id:result.id});const photo=await h.local.api("/api/jobs",{address,action:"photo_calendar",payload:{template_id:copy.items[0].template_id,photo_x:10}});assert.deepEqual(P.decode64(h.local.job(photo.id).payload.frame),P.photoFrame(frame,10));
    const backup=structuredClone(h.saved.get("current"));backup.templates[0].spec=JSON.stringify({...JSON.parse(backup.templates[0].spec),native_frame:P.bytes64(other)});await assert.rejects(h.local.validateImport(backup),/像素校验/);
});

test("gallery rename updates only the previous default title and preserves retired pictures and aliases",async()=>{
    const w=workspace(),config=JSON.parse(fs.readFileSync(path.join(root,"config.json"))),item=config.legacy_gallery.find(i=>i.path==="image/26-summit-overlook.png"),old=config.retired_gallery.find(i=>i.path==="image/17-mountain-summit.png");w.app_version="1.1.7";
    for(const [i,title,picture] of [[1,"登高望岳",item],[2,"我的山景",item],[3,"绝顶凌云",old]]){const bytes=fs.readFileSync(path.join(root,picture.frame));w.templates.push({id:ident(i),title,spec:JSON.stringify({kind:"image",builtin:picture.path}),frame:P.bytes64(bytes),sha256:picture.sha256,png:"original",created:1});}
    const {local,saved}=await harness(w),templates=local.summary().templates;assert.deepEqual(Array.from(templates,t=>t.title),["绝顶凌云","我的山景","绝顶凌云"]);
    for(let i=0;i<3;i++)assert.deepEqual({...saved.get("current").templates[i],title:w.templates[i].title},w.templates[i]);
    for(const picture of config.retired_gallery)await assert.rejects(local.api("/api/builtin",{path:picture.path}),/内置图片不存在/);
});

test("rotation requests validate metadata, bind an immutable inventory and never attach image payloads",async()=>{
    const h=await harness(),a={sequence:4,count:7,crc32:[1,2,3,4,5,6,7],photo_x:[0,0,0,0,0,0,0],mode:0,interval_minutes:1440,enabled:false};
    await h.local.updateState(address,{album:a,album_minute_tick:true});
    const valid={sequence:4,auto_rotate:true,interval_minutes:60};
    for(const payload of [{...valid,sequence:3},{...valid,auto_rotate:1},{...valid,interval_minutes:59},{...valid,items:[]}])await assert.rejects(h.local.api("/api/jobs",{address,action:"album_rotation",payload}));
    const result=await h.local.api("/api/jobs",{address,action:"album_rotation",payload:valid}),job=h.local.job(result.id);a.crc32[0]=999;
    assert.equal(job.payload.expected_album.crc32[0],1);assert.equal(job.payload.items,undefined);assert.equal(job.payload.frame,undefined);
});

test("inventory names use metadata without loading originals, and slot requests reject stale or malformed targets",async()=>{
    const h=await harness(),a={capacity:7,count:1,crc32:[P.crc32(frame)],photo_x:[38],sequence:0,mode:0,enabled:false,interval_minutes:1440};
    const listed=await h.local.restoreAlbum(a,[]);assert.equal(listed.items[0].title,"月球小兔");assert.equal(listed.items[0].template_id,null);assert.equal(listed.editable,false);assert.equal(h.local.summary().templates.length,0);
    await h.local.updateState(address,{album_capacity:7,offline_album:true,album:listed});
    for(const payload of [{index:1,sequence:0,crc32:a.crc32[0]},{index:0,sequence:2,crc32:a.crc32[0]},{index:0,sequence:0,crc32:0},{index:0.5,sequence:0,crc32:a.crc32[0]}])await assert.rejects(h.local.api("/api/jobs",{address,action:"album_show",payload}));
    assert.equal(h.local.summary().jobs.length,0);
    const job=await h.local.api("/api/jobs",{address,action:"album_read",payload:{index:0,sequence:0,crc32:a.crc32[0]}});assert.equal(h.local.job(job.id).action,"album_read");
});

test("calendar-specific native images force x=0 and reject use in the fullscreen mode",async()=>{
    const h=await harness(),config=JSON.parse(fs.readFileSync(path.join(root,"config.json"))),item=config.gallery.find(i=>i.layout==="calendar"),r=await h.local.api("/api/builtin",{path:item.path});
    assert.equal(JSON.parse(h.local.summary().templates.find(t=>t.id===r.id).spec).builtin_layout,"calendar");
    await assert.rejects(h.local.api("/api/jobs",{address,action:"publish",payload:{template_id:r.id}}),/日历专用/);
    const result=await h.local.api("/api/jobs",{address,action:"photo_calendar",payload:{template_id:r.id,photo_x:38}}),j=h.local.job(result.id);
    assert.equal(j.payload.photo_x,0);assert.deepEqual(P.decode64(j.payload.frame),Uint8Array.from(fs.readFileSync(path.join(root,item.frame))));
});
test("legacy calendar albums stay editable after an identical new fullscreen image was cached",async()=>{
    const h=await harness(),config=JSON.parse(fs.readFileSync(path.join(root,"config.json"))),full=config.gallery.find(i=>i.path==="image/fullscreen/01-sunrise-lake.png"),original=Uint8Array.from(fs.readFileSync(path.join(root,full.frame)));
    const chosen=await h.local.api("/api/builtin",{path:full.path}),a={capacity:7,count:1,sequence:4,crc32:[P.crc32(original)],photo_x:[38],mode:1,enabled:true,interval_minutes:1440};
    assert.equal(h.local.albumMatches(a)[0],null);
    const restored=await h.local.restoreAlbum(a,[original]),id=restored.items[0].template_id;assert.notEqual(id,chosen.id);assert.equal(JSON.parse(h.local.summary().templates.find(t=>t.id===id).spec).builtin_layout,undefined);
    const j=await h.local.api("/api/jobs",{address,action:"photo_calendar",payload:{template_id:id,photo_x:38}});assert.deepEqual(P.decode64(h.local.job(j.id).payload.frame),P.photoFrame(original,38));
});
test("one hundred existing templates plus all seventy new variants remain selectable and importable",async()=>{
    const w=workspace(),sha=await P.sha256(frame);for(let i=0;i<100;i++)w.templates.push({id:ident(i+1),title:"old "+i,spec:'{"kind":"image"}',frame:P.bytes64(frame),sha256:sha,png:"old",created:1});
    const h=await harness(w),config=JSON.parse(fs.readFileSync(path.join(root,"config.json")));
    for(const item of config.gallery)await h.local.api("/api/builtin",{path:item.path});
    assert.equal(h.local.summary().templates.length,170);const backup=await h.local.validateImport(structuredClone(h.saved.get("current")));assert.equal(backup.templates.length,170);
    assert.equal(h.local.summary().templates.slice(0,100).every(t=>JSON.parse(t.spec).builtin_layout===undefined),true);
});

test("seven-image request is refused by old device capacity before a job is admitted",async()=>{
    const h=await harness();await assert.rejects(h.local.api("/api/jobs",{address,action:"album",payload:{mode:"image",interval_minutes:1440,items:Array.from({length:7},(_,i)=>({template_id:ident(i+1),photo_x:38}))}}),/上限/);assert.equal(h.local.summary().jobs.length,0);
});

test("an interrupted album restore commit inside calibration cannot be automatically replayed",async()=>{
    let attempts=0;const h=await harness(workspace(),async()=>{attempts++;const e=Error("resume commit lost");e.connection=e.submitted=true;throw e;});
    const j=await h.local.api("/api/jobs",{address,action:"sync"});await h.local.tick();await h.local.tick();assert.equal(attempts,1);assert.equal(h.local.job(j.id).status,"delivery_unknown");
});
test("commit followed by disconnect is recorded once and never automatically replayed",async()=>{
    let attempts=0,h;h=await harness(workspace(),async j=>{attempts++;await h.local.updateJob(j,{committed:true,status:"awaiting_display"});const e=Error("connection lost after commit");e.connection=true;throw e;});
    const j=await h.local.api("/api/jobs",{address,action:"calendar"});await h.local.tick();await h.local.tick();assert.equal(attempts,1);assert.equal(h.local.job(j.id).status,"delivery_unknown");
});
test("reload preserves interrupted result as unknown, instead of resuming the write",async()=>{
    const w=workspace();w.jobs.push({id:ident(2),address,action:"probe",payload:{},receipt:{},status:"running",created:1,updated:1});let attempts=0;
    const h=await harness(w,async()=>{attempts++;});await h.local.tick();assert.equal(h.local.job(ident(2)).status,"delivery_unknown");assert.equal(attempts,0);
});
test("import preserves old workspace, disables old queues and plans, and rejects corrupt pixels",async()=>{
    const h=await harness(),next=workspace();next.jobs.push({id:ident(3),address,action:"publish",payload:{frame:P.bytes64(frame),sha256:await P.sha256(frame)},receipt:{},status:"running",created:1});next.templates.push({id:ident(4),title:"image",spec:'{"kind":"image"}',frame:P.bytes64(frame),sha256:await P.sha256(frame),png:"old",created:1});next.plans.push({address,template_id:ident(4),enabled:true,interval_minutes:5});
    const corrupt=structuredClone(next);corrupt.templates[0].sha256="0".repeat(64);await assert.rejects(h.local.importBackup(corrupt),/像素校验失败/);assert.equal(h.saved.has("before-import"),false);
    await h.local.importBackup(next);assert.equal(h.saved.get("before-import").templates.length,0);assert.equal(h.local.job(ident(3)).status,"cancelled");assert.equal(h.local.summary().plans[0].enabled,false);assert.deepEqual(structuredClone(h.local.device(address).state),{});
});
test("backup accepts historical jobs and completed reminders after unregistering a screen",async()=>{
    const w=workspace();w.devices=[];w.jobs.push({id:ident(5),address,action:"probe",payload:{},receipt:{},status:"succeeded",created:1});w.reminders.push({id:ident(6),address,title:"past",body:"done",due:1900000000,token:42,options:"{}",status:"completed",job_id:ident(5)});
    const h=await harness();const checked=await h.local.validateImport(w);assert.equal(checked.jobs.length,1);assert.equal(checked.reminders[0].status,"completed");
    w.reminders[0].status="armed";await assert.rejects(h.local.validateImport(w),/提醒无效/);
});
test("retention keeps the latest 100 finished jobs plus referenced reminders and unfinished work",async()=>{
    const w=workspace();for(let n=1;n<=120;n++)w.jobs.push({id:ident(n),address,action:"probe",payload:{},receipt:{},status:"succeeded",created:n});w.reminders.push({id:ident(200),address,job_id:ident(1),status:"completed"});
    const h=await harness(w);await h.local.api("/api/jobs",{address,action:"probe"});const stored=h.saved.get("current").jobs;assert.equal(stored.length,102);assert.ok(stored.some(j=>j.id===ident(1)));assert.equal(stored.filter(j=>j.status==="queued").length,1);assert.ok(!stored.some(j=>j.id===ident(2)));
});
test("deleting a reminder while its pixels render does not enqueue a ghost reminder",async()=>{
    const h=await harness(),r=await h.local.api("/api/reminders",{addresses:[address],title:"test",body:"",due:Math.floor(Date.now()/1000)+3600,options:{}});let finish,started;
    const ready=new Promise(resolve=>started=resolve);h.context.ELinkRenderer.render=()=>new Promise(resolve=>{finish=resolve;started();});const running=h.local.tick();await ready;
    await h.local.api("/api/reminders/delete",{id:r.ids[0]});finish({frame:P.bytes64(frame),sha256:await P.sha256(frame),png:"canonical-png"});await running;
    assert.equal(h.local.summary().reminders.length,0);assert.equal(h.local.summary().jobs.length,0);
});

test("all unfinished states reserve the workspace across devices and concurrent submissions",async()=>{
    const other="AA:BB:CC:DD:EE:02";
    for(const status of ["queued","waiting","running","awaiting_display"]){
        const w=workspace();w.devices.push({...w.devices[0],address:other});w.jobs.push({id:ident(300),address,action:"probe",status,payload:{},receipt:{},created:1});
        const h=await harness(w);if(status==="running"||status==="awaiting_display")await h.local.updateJob(h.local.job(ident(300)),{status,progress:100});
        assert.equal(h.local.summary().operation.busy,true);
        await assert.rejects(h.local.api("/api/jobs",{address:other,action:"probe"}),/尚未完成/);
        await assert.rejects(h.local.importBackup(workspace()),/尚未完成/);
    }
    const w=workspace();w.devices.push({...w.devices[0],address:other});const h=await harness(w),results=await Promise.allSettled([address,other].map(address=>h.local.api("/api/jobs",{address,action:"probe"})));
    assert.equal(results.filter(r=>r.status==="fulfilled").length,1);assert.equal(h.local.summary().operation.jobs,1);
});

test("batch admits one group, waiting cancellation releases it, and summaries retain every unfinished job",async()=>{
    const w=workspace(),other="AA:BB:CC:DD:EE:02";w.devices.push({...w.devices[0],address:other});const h=await harness(w);
    const batch=await h.local.api("/api/jobs/batch",{addresses:[address,other],action:"probe"});assert.equal(batch.results.length,2);assert.ok(batch.results.every(r=>r.id));
    await assert.rejects(h.local.api("/api/jobs/batch",{addresses:[address],action:"probe"}),/尚未完成/);
    for(const r of batch.results)await h.local.api("/api/cancel",{id:r.id});assert.equal(h.local.summary().operation.busy,false);
    const many=workspace();for(let n=1;n<=101;n++)many.jobs.push({id:ident(n),address,action:"probe",payload:{},receipt:{},status:"queued",created:n});
    const loaded=await harness(many);await loaded.local.updateJob(loaded.local.job(ident(1)),{status:"running"});assert.equal(loaded.local.summary().jobs.length,101);assert.equal(loaded.local.summary().jobs[0].id,ident(1));
});

test("pending reminders reserve the workspace but only uninstalled ones can be cancelled locally",async()=>{
    const h=await harness(),r=await h.local.api("/api/reminders",{addresses:[address],title:"test",body:"",due:Math.floor(Date.now()/1000)+3600,options:{}});
    assert.equal(h.local.summary().operation.pending_reminders,1);await assert.rejects(h.local.api("/api/jobs",{address,action:"probe"}),/尚未完成/);
    await h.local.api("/api/reminders/cancel-pending",{id:r.ids[0]});assert.equal(h.local.summary().operation.busy,false);
    const w=workspace();w.reminders.push({id:ident(302),address,title:"old",body:"",status:"pending",previous_token:42,job_id:""});const old=await harness(w);
    await assert.rejects(old.local.api("/api/reminders/cancel-pending",{id:ident(302)}),/尚未派发/);assert.equal(old.local.summary().reminders.length,1);
});
