"use strict";
// Protocol emulator tests the real transaction engine; it is not a hardware test.
const test=require("node:test"),assert=require("node:assert/strict"),vm=require("node:vm"),fs=require("node:fs"),path=require("node:path"),P=require("../protocol.js");
const root=path.join(__dirname,".."),frame=Uint8Array.from(fs.readFileSync(path.join(root,"image/13-space-rabbit.bin")));
async function harness(options={}){
    const model={mode:1,every:60,page:2,generation:9,received:0,transfer:0,sum:0,expected:0,time:1,window:0,advertise:1,refresh:5,error:0},commands=[],jobs=[],values=new Map(),device={id:"test-device",name:"ELINK-BWR-EE0001",gatt:{connected:true,disconnect(){this.connected=false;}}};
    const slots=Array.from({length:8},(_,slot)=>({slot,state:255,token:0,due:0,crc:0,received:0,frame:new Uint8Array(8000),metadata:new Uint8Array(156),writing:false}));let currentSlot=0,answer=new Uint8Array(32),commitCount=0;
    function state(){const b=new Uint8Array(32);b.set([69,76,75,49,1,model.mode,model.every,model.page,0,model.error]);const v=P.view(b);v.setUint16(10,model.received,true);v.setUint16(12,model.transfer,true);v.setUint16(14,model.sum,true);v.setUint16(16,model.expected,true);v.setUint16(18,model.generation,true);b[21]=model.window;b[22]=model.advertise;b[24]=model.refresh;b[27]=model.time;b.set([1,2,3,4],28);return b;}
    function slotData(i){const s=slots[i],b=new Uint8Array(24),v=P.view(b);b.set([69,82,77,49,1,i,s.state,Number(s.writing)]);v.setUint32(8,s.token,true);v.setUint32(12,s.due,true);v.setUint32(16,s.crc,true);v.setUint16(20,s.received,true);b[22]=currentSlot;b[23]=1;return b;}
    function runtime(i){const s=slots[i],b=new Uint8Array(20),v=P.view(b);b.set([69,82,77,50,s.metadata[1]||0,s.metadata[2]||1,s.metadata[3]||5,s.metadata[0]||255]);v.setUint32(8,s.due,true);return b;}
    const characteristic={async writeValueWithResponse(b){
        assert.ok(b.length<=20);commands.push(Uint8Array.from(b));const v=P.view(b),code=b[0];
        if(code===0x93)answer=state();
        else if(code===0x9d)answer=Uint8Array.from([69,76,85,73,1,255,3,0]);
        else if(code===0x94){model.mode=b[1];model.every=b[2];}
        else if(code===0x99){model.refresh=b[1];model.advertise=b[2];model.window=b[3];}
        else if(code===0x95){model.page=1;model.transfer=v.getUint16(1,true);model.expected=v.getUint16(3,true);model.received=0;model.sum=0;}
        else if(code===0x96){assert.equal(v.getUint16(1,true),model.received);const bytes=b.subarray(3);model.received+=bytes.length;model.sum=(model.sum+bytes.reduce((a,b)=>a+b,0))&65535;if(options.badPosition&&model.received>=544)model.received--;}
        else if(code===0x97){assert.equal(model.received,8000);assert.equal(model.sum,model.expected);model.page=2;model.generation++;commitCount++;if(options.disconnectCommit){device.gatt.connected=false;throw Error("disconnected after device accepted commit");}}
        else if(code===0x9c){model.page={0:0,1:3,2:4}[b[1]];model.generation++;commitCount++;}
        else if(code===0x91||code===0x9e){model.time=1;if(code===0x91)model.page=0;}
        else if(code===0xb4)answer=slotData(b[1]);
        else if(code===0xbb)answer=runtime(b[1]);
        else if(code===0xb0){currentSlot=b[1];const s=slots[currentSlot];s.token=v.getUint32(2,true);s.due=v.getUint32(6,true);s.crc=v.getUint32(10,true);s.received=0;s.writing=true;}
        else if(code===0xb1){const s=slots[currentSlot],off=v.getUint16(1,true);assert.equal(off,s.received);s.frame.set(b.subarray(3),off);s.received+=b.length-3;}
        else if(code===0xb7){const s=slots[b[1]],off=v.getUint16(2,true);answer=s.frame.slice(off,Math.min(8000,off+128));if(options.corruptReadback)answer[0]^=1;}
        else if(code===0xb8)slots[currentSlot].metadata.set(b.subarray(2),b[1]);
        else if(code===0xb2){const s=slots[currentSlot];assert.equal(s.crc,P.crc32(s.frame));assert.equal(s.received,8000);assert.equal(s.token,v.getUint32(1,true));s.state=254;s.writing=false;commitCount++;}
        else if(code===0xba){const off=v.getUint16(2,true);answer=slots[b[1]].metadata.slice(off,Math.min(156,off+128));}
        else if(code===0xb9){model.page=5;model.generation++;commitCount++;}
        else if(code===0xb5){const s=slots[b[1]];assert.equal(s.token,v.getUint32(2,true));s.state=248;}
        else if(code===0x9a)answer=new Uint8Array(128).fill(v.getUint16(1,true)<4000?255:0);
    },async readValue(){return new DataView(answer.buffer,answer.byteOffset,answer.byteLength);}};
    device.gatt.getPrimaryService=async()=>({getCharacteristic:async id=>id===P.control?characteristic:{readValue:async()=>new DataView(Uint8Array.of(228,11).buffer)}});
    const store={ready:Promise.resolve(),assertOwner(){},summary:()=>({jobs,reminders:[]}),device:()=>({settings:P.settings()}),job:ident=>jobs.find(j=>j.id===ident),async updateJob(j,change){Object.assign(j,change);},async updateState(address,s){values.set(address,s);},async saveSettings(){},async reconcile(){},async persist(){},stopPlans(){},async api(){return {address:"AA:BB:CC:DD:EE:01"};},async tick(){}};
    const elements=new Map(),storage=new Map(),context=vm.createContext({ELinkProtocol:P,ELinkLocal:store,ELinkRenderer:{metadata:async()=>{const b=new Uint8Array(156);b.set([166,127,1,5]);P.view(b).setUint32(152,P.crc32(b.subarray(0,152)),true);return b;},png:()=>"preview",noticeBattery:async()=>{throw Error("unexpected notice render");}},console,crypto,Uint8Array,Uint16Array,Uint32Array,DataView,Date,Math,Set,Map,TextEncoder,Promise,Error,Number,Array,String,Object,location:{reload(){}},window:{isSecureContext:true,addEventListener(){}},navigator:{bluetooth:{requestDevice:async()=>device,getDevices:async()=>[device]},userActivation:{isActive:true}},sessionStorage:{getItem:()=>null,setItem(){},removeItem(){}},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},setInterval(){},setTimeout(fn,ms){if(ms<=1000)queueMicrotask(fn);return 0;},clearTimeout(){},pending:()=>false,refresh:async()=>{},selectDevice(){},message(){},confirmAction:async()=>options.confirmRebind!==false,state:{jobs:[]},targets:new Set(),$:id=>{if(!elements.has(id))elements.set(id,{value:"",disabled:false,textContent:""});return elements.get(id);}});
    if(options.fireConnectTimeout)context.setTimeout=(fn,ms)=>{if(ms<=1000||ms===20000)queueMicrotask(fn);return 0;};
    vm.runInContext(fs.readFileSync(path.join(root,"browser-ble.js"),"utf8"),context);const actualAddress=await vm.runInContext('ELinkBLE.connect("",true,false)',context);
    return {context,model,commands,slots,jobs,values,store,storage,device,commitCount:()=>commitCount,async execute(action,payload={}){const j={id:String(jobs.length),address:actualAddress,action,payload,status:"running",committed:false};jobs.push(j);context.nextJob=j;return {job:j,promise:vm.runInContext("ELinkBLE.execute(nextJob)",context)};}};
}
test("publish sends exact native bytes, checks offsets/checksum and generation",async()=>{
    const h=await harness(),{job,promise}=await h.execute("publish",{kind:"image",frame:P.bytes64(frame),sha256:await P.sha256(frame)}),receipt=await promise;
    assert.equal(receipt.result,"busy_completed");assert.equal(receipt.generation_after,10);assert.equal(receipt.bytes,8000);assert.equal(h.commitCount(),1);assert.equal(job.committed,true);
    const sent=Buffer.concat(h.commands.filter(c=>c[0]===0x96).map(c=>Buffer.from(c.subarray(3))));assert.deepEqual(sent,Buffer.from(frame));assert.equal(h.commands.find(c=>c[0]===0x99)[3],0);
});
test("wrong receive offset stops before committing",async()=>{const h=await harness({badPosition:true}),{job,promise}=await h.execute("publish",{kind:"image",frame:P.bytes64(frame),sha256:await P.sha256(frame)});await assert.rejects(promise,/接收位置/);assert.equal(h.commitCount(),0);assert.equal(job.committed,false);});
test("disconnect after accepted commit remains uncertain and cannot be auto-replayed",async()=>{const h=await harness({disconnectCommit:true}),{job,promise}=await h.execute("publish",{kind:"image",frame:P.bytes64(frame),sha256:await P.sha256(frame)});await assert.rejects(promise,/disconnected/);assert.equal(job.committed,true);assert.equal(job.status,"awaiting_display");assert.equal(h.commitCount(),1);assert.equal(h.commands.filter(c=>c[0]===0x97).length,1);});
test("page selection waits for the matching display generation",async()=>{const h=await harness(),{promise}=await h.execute("calendar",{}),receipt=await promise;assert.equal(receipt.display_mode,3);assert.equal(receipt.display_generation,10);assert.equal(receipt.result,"busy_completed");});
test("reminder verifies every Flash pixel and metadata before reporting offline readiness",async()=>{
    const h=await harness(),payload={operation:"install",token:87654,due:1900000000,title:"Reminder",options:{repeat_mask:127,check_minutes:1,duration_minutes:5,utc_offset:0},frame:P.bytes64(frame),sha256:await P.sha256(frame)},r=await h.execute("reminder",payload),receipt=await r.promise;
    assert.equal(receipt.result,"reminder_flash_verified");assert.equal(receipt.slot_state,254);assert.equal(receipt.offline,true);assert.deepEqual(h.slots[0].frame,frame);assert.equal(h.commands.filter(c=>c[0]===0xb7).length,63);assert.equal(h.commands.filter(c=>c[0]===0xba).length,2);
    const again=await h.execute("reminder",payload);await again.promise;assert.equal(h.commands.filter(c=>c[0]===0xb0).length,1,"idempotent recheck does not rewrite an armed slot");
});
test("corrupt Flash readback never activates the reminder",async()=>{const h=await harness({corruptReadback:true}),r=await h.execute("reminder",{operation:"install",token:123,due:1900000000,title:"Reminder",options:{},frame:P.bytes64(frame),sha256:await P.sha256(frame)});await assert.rejects(r.promise,/读回失败/);assert.equal(h.commands.filter(c=>c[0]===0xb2).length,0);assert.equal(r.job.committed,false);});

test("cross-origin migration rebinds only the explicitly chosen matching screen",async()=>{
    const h=await harness(),old="web-"+"ab".repeat(16);h.store.device=()=>({name:h.device.name,settings:P.settings()});h.context.oldAddress=old;
    assert.equal(await vm.runInContext('ELinkBLE.connect(oldAddress,true,false)',h.context),old);assert.equal(h.storage.get("elink-device-"+old),h.device.id);
    assert.equal(await vm.runInContext('ELinkBLE.connect(oldAddress,false,true)',h.context),old,"remembered association reconnects without another prompt");
});
test("migration rejects a different screen or declined association",async()=>{
    const h=await harness();h.store.device=()=>({name:"ELINK-BWR-OTHER",settings:P.settings()});h.context.oldAddress="web-"+"cd".repeat(16);
    await assert.rejects(vm.runInContext('ELinkBLE.connect(oldAddress,true,false)',h.context),/不是当前屏幕/);
    const declined=await harness({confirmRebind:false});declined.store.device=()=>({name:declined.device.name,settings:P.settings()});declined.context.oldAddress=h.context.oldAddress;
    await assert.rejects(vm.runInContext('ELinkBLE.connect(oldAddress,true,false)',declined.context),/不是当前屏幕/);
});
test("connection timeout stops retries and disconnects a late completion",async()=>{
    const h=await harness({fireConnectTimeout:true});let finish,calls=0;h.device.gatt.connected=false;h.device.gatt.connect=()=>{calls++;return new Promise(resolve=>finish=resolve);};
    await assert.rejects(vm.runInContext('ELinkBLE.connect("",true,false)',h.context),/超时/);assert.equal(calls,1);
    h.device.gatt.connected=true;finish(h.device.gatt);await Promise.resolve();assert.equal(h.device.gatt.connected,false);
});
