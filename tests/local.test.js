"use strict";
// The real local engine runs against an in-memory IndexedDB boundary; browser persistence is also tested in the UI.
const test=require("node:test"),assert=require("node:assert/strict"),vm=require("node:vm"),fs=require("node:fs"),path=require("node:path"),P=require("../protocol.js");
const root=path.join(__dirname,".."),address="AA:BB:CC:DD:EE:01",frame=Uint8Array.from(fs.readFileSync(path.join(root,"image/13-space-rabbit.bin"))),ident=n=>n.toString(16).padStart(32,"0");
function workspace(){return {format:"elink-web",schema:1,devices:[{address,name:"ELINK-BWR-DDEE01",settings:P.settings(),state:{display_mode:2},updated:1}],templates:[],jobs:[],plans:[],reminders:[]};}
async function harness(initial=workspace(),execute=async()=>({})){
    const saved=new Map([["current",structuredClone(initial)]]);
    const db={transaction(){const t={};t.objectStore=()=>({get(key){const r={};queueMicrotask(()=>{r.result=structuredClone(saved.get(key));r.onsuccess();});return r;},put(value,key){saved.set(key,structuredClone(value));queueMicrotask(()=>t.oncomplete?.());}});return t;}};
    const context=vm.createContext({ELinkProtocol:P,ELinkRenderer:{png:()=>"canonical-png",render:async spec=>{const b=spec.test_frame||frame;return {frame:P.bytes64(b),sha256:await P.sha256(b),png:"canonical-png"};}},ELinkBLE:{execute},console,crypto,structuredClone,Uint32Array,Promise,Error,Date,Math,JSON,Set,Map,Object,Array,Number,String,URL,Blob,setTimeout,window:{isSecureContext:true,addEventListener(){}},location:{href:"https://example.test/elink-web/"},navigator:{locks:{request:async(name,options,handler)=>handler({name})}},indexedDB:{open(){const r={};queueMicrotask(()=>{r.result=db;r.onsuccess();});return r;}},fetch:async()=>({json:async()=>JSON.parse(fs.readFileSync(path.join(root,"config.json"),"utf8"))}),portable:{address,device:{gatt:{connected:true}}}});
    vm.runInContext(fs.readFileSync(path.join(root,"local.js"),"utf8"),context);const local=vm.runInContext("ELinkLocal",context);await local.ready;return {local,saved,context};
}
test("queued image stays immutable after editing and deleting its template",async()=>{
    const w=workspace(),sha=await P.sha256(frame);w.templates.push({id:ident(1),title:"original",spec:'{"kind":"image"}',frame:P.bytes64(frame),sha256:sha,png:"original",created:1});const {local}=await harness(w);
    const j=await local.api("/api/jobs",{address,action:"publish",payload:{template_id:ident(1)}}),changed=frame.slice();changed[0]^=1;
    await local.api("/api/templates",{id:ident(1),title:"edited",spec:{kind:"image",test_frame:changed}});await local.api("/api/templates/delete",{id:ident(1)});
    assert.equal(local.job(j.id).payload.sha256,sha);assert.deepEqual(P.decode64(local.job(j.id).payload.frame),frame);assert.equal(local.summary().templates.length,0);
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
