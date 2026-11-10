"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.join(__dirname,".."),source=fs.readFileSync(path.join(root,"gallery.js"),"utf8");
function harness(){
    const elements=new Map(),storage=new Map([["elink-album-settings",JSON.stringify({enabled:true,items:["old-cache"]})]]),queued=[],confirmations=[],cards=[];
    const element=()=>({value:"",checked:false,children:[],dataset:{},classList:{toggle(){}},setAttribute(){},append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},get firstElementChild(){return this.children[0];}});
    const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
    const templates=Array.from({length:8},(_,i)=>({id:String(i),title:"Image "+i,sha256:"fixture-sha-"+i,spec:JSON.stringify({kind:"image",builtin:"image/"+i+".png"})}));
    const album={protocol_version:3,count:7,sequence:4,mode:0,index:3,photo_x:[0,10,20,30,40,50,60],crc32:[1,2,3,4,5,6,7],enabled:true,running:true,interval_minutes:360,items:templates.slice(0,7).map((t,i)=>({template_id:t.id,title:t.title,sha256:t.sha256,photo_x:i*10}))};
    const device={address:"screen",name:"Screen",state:{album,album_capacity:7,display_mode:7,album_minute_tick:true}};
    const c=vm.createContext({Date,Set,Map,Math,JSON,Number,String,Object,Array,Promise,Error,$:get,state:{templates,devices:[device],jobs:[{id:"new-probe",address:"screen",action:"probe",status:"succeeded",updated:Date.now()/1000}]},targets:new Set(["screen"]),localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},document:{createElement:element,querySelectorAll:s=>s==='[data-native-gallery]'?[{replaceChildren(){},append(b){cards.push(b);}}]:[],querySelector:()=>element()},selected:()=>device,singleDevice:()=>device,pageAction:()=>"publish",pageIssue:()=>"",operationBusy:()=>false,pageControls(){},showSaved(){},pending:()=>false,batching:false,resource:x=>x,perform:async(b,fn)=>fn(),api:async()=>({}),refresh:async()=>{},queue:async(action,payload)=>queued.push({action,payload}),confirmAction:async text=>{confirmations.push(text);return c.confirmed;},confirmed:true});
    vm.runInContext(source,c);get("publish-template").value="7";c.initGallery([{path:"image/7.png",title:"Image 7"}]);
    return {c,get,device,queued,confirmations,cards,selection:()=>Array.from(vm.runInContext("albumSelection",c))};
}
test("a remembered bulk editor never turns a preview click into a playlist edit",async()=>{
    const h=harness();assert.equal(h.get("album-save").checked,false);h.c.restoreDeviceAlbum();h.get("album-save").checked=true;
    const before=h.selection();await h.cards[0].onclick();assert.deepEqual(h.selection(),before);assert.equal(h.get("publish-template").value,"7");assert.equal(h.queued.length,0);
});
test("fresh device reads restore rotation and slots while stale records and unknown originals never masquerade as device drafts",()=>{
    const h=harness();h.c.restoreDeviceAlbum();assert.deepEqual(h.selection(),["0","1","2","3","4","5","6"]);assert.equal(h.get("album-auto").checked,true);assert.equal(h.get("album-interval").value,"360");assert.equal(h.get("album-save").checked,false);
    h.device.state.album.sequence++;h.device.state.album.items[2].template_id=null;h.device.state.album.enabled=false;h.c.restoreDeviceAlbum();assert.deepEqual(h.selection(),[]);assert.equal(h.get("album-auto").checked,false);assert.match(h.get("album-readback-note").textContent,/未沿用旧草稿/);
    h.c.state.jobs[0].updated=1;h.c.restoreDeviceAlbum();assert.match(h.get("album-readback-note").textContent,/上次记录与草稿/);assert.equal(h.queued.length,0);
});
test("replacing a draft slot prompts, changes only that slot, and performs no device write",async()=>{
    const h=harness();h.c.restoreDeviceAlbum();h.get("publish-template").value="7";h.c.confirmed=false;
    await h.c.replaceAlbumImage();assert.equal(h.selection()[3],"3");h.c.confirmed=true;await h.c.replaceAlbumImage();assert.deepEqual(h.selection(),["0","1","2","7","4","5","6"]);assert.match(h.confirmations[0],/第 4 张/);assert.equal(h.queued.length,0);
});
test("whole-album save confirms all seven writes and binds the queue to that device sequence",async()=>{
    const h=harness();h.c.restoreDeviceAlbum();h.get("publish-template").value="7";await h.c.replaceAlbumImage();h.c.confirmed=false;await h.c.saveDeviceAlbum();assert.equal(h.queued.length,0);
    h.c.confirmed=true;await h.c.saveDeviceAlbum();assert.equal(h.queued.length,1);assert.equal(h.queued[0].payload.max_image_writes,7);assert.equal(h.queued[0].payload.expected_sequence,4);assert.match(h.confirmations.at(-1),/写入 7 张（56000 字节）/);
    h.c.confirmAction=async()=>{h.device.state.album.sequence++;return true;};await assert.rejects(h.c.saveDeviceAlbum(),/已变化/);assert.equal(h.queued.length,1);
});
test("unchanged images confirm zero uploads, while a never-started album focuses the first slot",async()=>{
    const h=harness();h.device.state.album.index=255;h.c.restoreDeviceAlbum();assert.equal(h.get("publish-template").value,"0");await h.c.saveDeviceAlbum();assert.equal(h.queued[0].payload.max_image_writes,0);assert.match(h.confirmations.at(-1),/不上传图片/);
});
test("editing a template under the same ID confirms image writes instead of falsely promising reuse",async()=>{
    const h=harness();h.c.restoreDeviceAlbum();h.c.state.templates[3].sha256="edited-pixels";await h.c.saveDeviceAlbum();assert.equal(h.queued[0].payload.max_image_writes,7);assert.match(h.confirmations.at(-1),/写入 7 张/);
});
test("the main phone action confirms and displays exactly one preview even when the bulk editor is open",async()=>{
    const h=harness(),calls=[];h.c.pageAction=()=>"publish";h.get("album-save").checked=true;h.c.batch=async(action,payload)=>calls.push({action,payload});
    const line=fs.readFileSync(path.join(root,"app.js"),"utf8").split("\n").find(s=>s.startsWith('$("apply-page").onclick='));vm.runInContext(line,h.c);
    h.c.confirmed=false;await h.get("apply-page").onclick();assert.equal(calls.length,0);h.c.confirmed=true;await h.get("apply-page").onclick();assert.equal(calls.length,1);assert.equal(calls[0].action,"publish");assert.equal(calls[0].payload.template_id,"7");assert.match(h.confirmations.at(-1),/只发送这一张/);
});
