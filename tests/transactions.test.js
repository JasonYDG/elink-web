"use strict";
// Protocol emulator tests the real transaction engine; it is not a hardware test.
const test=require("node:test"),assert=require("node:assert/strict"),vm=require("node:vm"),fs=require("node:fs"),path=require("node:path"),P=require("../protocol.js");
const root=path.join(__dirname,".."),frame=Uint8Array.from(fs.readFileSync(path.join(root,"image/13-space-rabbit.bin")));
async function harness(options={}){
    const model={mode:1,every:60,page:2,generation:9,received:0,transfer:0,sum:0,expected:0,time:1,window:0,advertise:1,refresh:5,error:0,firmware:Uint8Array.of(1,2,3,4)},commands=[],jobs=[],updates=[],values=new Map(),device={id:"test-device",name:"ELINK-BWR-EE0001",gatt:{connected:true,disconnect(){this.connected=false;},async connect(){this.connected=true;return this;}}};
    const slots=Array.from({length:8},(_,slot)=>({slot,state:255,token:0,due:0,crc:0,received:0,frame:new Uint8Array(8000),metadata:new Uint8Array(156),writing:false}));let currentSlot=0,answer=new Uint8Array(32),commitCount=0;
    const pixels=new Uint8Array(8000),album={sequence:0,count:0,mode:0,minutes:1440,enabled:false,running:false,index:255,writing:false,step:0,staged:[],frames:[],positions:[]};pixels.fill(255,0,4000);
    function albumData(){const b=new Uint8Array(64),v=P.view(b);b.set([69,76,65,49,3,Number(!!album.sequence),Number(album.running),album.index,Number(album.writing),album.staged.length]);v.setUint16(10,album.step,true);if(album.sequence){const c=b.subarray(12),cv=P.view(c);c.set([69,76,71,50]);cv.setUint32(4,album.sequence,true);cv.setUint16(12,album.minutes,true);c[14]=album.count;c[15]=album.mode+Number(album.enabled)*4;album.frames.forEach((f,i)=>cv.setUint32(16+i*4,P.crc32(f),true));c.set(album.positions,44);c[51]=254;cv.setUint32(8,P.crc32(Uint8Array.from([...c.subarray(0,8),...c.subarray(12,51)])),true);}return b;}
    function state(){const busy=model.busyReads>0;if(busy)model.busyReads--;const b=new Uint8Array(32);b.set([69,76,75,49,1,model.mode,model.every,model.page,Number(busy),model.error]);const v=P.view(b);v.setUint16(10,model.received,true);v.setUint16(12,model.transfer,true);v.setUint16(14,model.sum,true);v.setUint16(16,model.expected,true);v.setUint16(18,model.generation,true);b[21]=model.window;b[22]=model.advertise;b[24]=model.refresh;b[27]=model.time;b.set(model.firmware,28);return b;}
    function slotData(i){const s=slots[i],b=new Uint8Array(24),v=P.view(b);b.set([69,82,77,49,1,i,s.state,Number(s.writing)]);v.setUint32(8,s.token,true);v.setUint32(12,s.due,true);v.setUint32(16,s.crc,true);v.setUint16(20,s.received,true);b[22]=currentSlot;b[23]=1;return b;}
    function runtime(i){const s=slots[i],b=new Uint8Array(20),v=P.view(b);b.set([69,82,77,50,s.metadata[1]||0,s.metadata[2]||1,s.metadata[3]||5,s.metadata[0]||255]);v.setUint32(8,s.due,true);return b;}
    const characteristic={async writeValueWithResponse(b){
        if(b.length>(options.maxWrite||((options.album||options.ota)?136:20)))throw Error("GATT write capacity exceeded");commands.push(Uint8Array.from(b));const v=P.view(b),code=b[0];
        if(options.beforeWrite)await options.beforeWrite(b,album);
        if(code===0x93){if(b.length!==1)model.error=1;answer=state();}
        else if(code===0x9d)answer=Uint8Array.from([69,76,85,73,1,255,options.album||options.ota?31:3,0]);
        else if(code===0x94){model.mode=b[1];model.every=b[2];model.error=0;}
        else if(code===0xa0){model.ota=new Uint8Array(Math.ceil((v.getUint16(2,true)+64)/256)*256);model.otaOffset=0;}
        else if(code===0xa2){model.ota.set(b.subarray(8),model.otaOffset);}
        else if(code===0xa3){model.ota.set(b.subarray(8),model.otaOffset+128);model.otaOffset+=256;}
        else if(code===0xa1){const off=v.getUint16(1,true);answer=model.ota.slice(off,off+128);if(!off){answer[2]=255;answer[3]=7;}if(options.corruptOTA&&off===128)answer[0]^=1;}
        else if(code===0xa4){model.firmware=model.ota.slice(64+0xe2d4+28,64+0xe2d4+32);if(options.wrongBoot)model.firmware[0]^=1;model.page=4;device.gatt.connected=false;commitCount++;if(options.disconnectOTACommit)throw Error("OTA commit reset before ATT reply");}
        else if(code===0x99){model.refresh=b[1];model.advertise=b[2];model.window=b[3];}
        else if(code===0x95){model.page=1;model.transfer=v.getUint16(1,true);model.expected=v.getUint16(3,true);model.received=0;model.sum=0;}
        else if(code===0x96){assert.equal(v.getUint16(1,true),model.received);const bytes=b.subarray(3);pixels.set(bytes,model.received);model.received+=bytes.length;model.sum=(model.sum+bytes.reduce((a,b)=>a+b,0))&65535;if(options.badPosition&&model.received>=544)model.received--;}
        else if(code===0x97){assert.equal(model.received,8000);assert.equal(model.sum,model.expected);model.page=2;model.generation++;commitCount++;if(options.disconnectCommit){device.gatt.connected=false;throw Error("disconnected after device accepted commit");}}
        else if(code===0x9c){model.page={0:0,1:3,2:4,3:6}[b[1]];model.generation++;commitCount++;}
        else if(code===0xbd){
            if(b[1]===0)answer=albumData();
            else if(b[1]===6){if(options.preflightUnsupported){model.error=1;answer=state();}else answer=Uint8Array.of(69,76,65,80,b[2]+(options.badPreflight?2:1),120,0,0);}
            else if(b[1]===1){if(!album.sequence)album.sequence=1;album.writing=true;album.staged=[];album.stagedPositions=[];album.step=0;}
            else if(b[1]===2){assert.equal(b[2],album.staged.length);assert.equal(b[8],album.step);assert.equal(v.getUint32(4,true),P.crc32(pixels));if(options.badAlbumStep&&album.step===3)throw Error("Flash step failed");album.step++;if(album.step===32){album.staged.push(pixels.slice());album.stagedPositions.push(b[3]);album.step=0;model.page=2;}}
            else if(b[1]===3){assert.equal(album.step,0);if(options.disconnectBeforeAlbumCommit){device.gatt.connected=false;throw Error("album commit never reached device");}if(album.writing){album.frames=album.staged;album.positions=album.stagedPositions;}album.count=album.frames.length;album.mode=b[2];album.minutes=v.getUint16(3,true);album.sequence++;album.enabled=album.running=true;album.writing=false;album.index=0;pixels.set(album.mode?P.photoFrame(album.frames[0],album.positions[0]):album.frames[0]);model.page=7+album.mode;model.generation++;commitCount++;if(options.disconnectAlbumCommit){device.gatt.connected=false;throw Error("album commit disconnected");}}
            else if(b[1]===4){album.enabled=album.running=album.writing=false;album.sequence++;}
            else if(b[1]===5){const off=v.getUint16(3,true);answer=album.frames[b[2]].slice(off,off+128);if(options.corruptAlbumReadback)answer[0]^=1;}
        }
        else if(code===0x91||code===0x9e){model.time=1;model.page=code===0x91?0:2;album.running=false;model.busyReads=options.busyAfterSync||0;model.error=options.syncError||0;}
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
        else if(code===0x9a){const off=v.getUint16(1,true);answer=new Uint8Array(128);answer.set(pixels.subarray(off,Math.min(off+128,off<4000?4000:8000)));if(options.corruptRAM)answer[0]^=1;if(options.changeDuringReadback||options.keepChanging){model.generation++;options.changeDuringReadback=false;}}
    },async readValue(){if(options.beforeRead)await options.beforeRead(album);return new DataView(answer.buffer,answer.byteOffset,answer.byteLength);}};
    device.gatt.getPrimaryService=async()=>({getCharacteristic:async id=>id===P.control?characteristic:{readValue:async()=>new DataView(Uint8Array.of(228,11).buffer)}});
    const store={ready:Promise.resolve(),assertOwner(){},summary:()=>({jobs,reminders:[]}),device:()=>({settings:P.settings()}),job:ident=>jobs.find(j=>j.id===ident),async updateJob(j,change){updates.push({...change});Object.assign(j,change);},async updateState(address,s){values.set(address,s);},async saveSettings(){},async reconcile(){},async persist(){},stopPlans(){},albumMatches:a=>a.crc32.map(()=>null),albumFrame:(a,index)=>options.cachedAlbum?album.frames[index]:null,async restoreAlbum(a,frames){store.restored=frames;return {...a,items:Array.from({length:a.count},(_,i)=>({template_id:frames[i]?"read-"+i:null,photo_x:a.photo_x[i]})),editable:Array.from({length:a.count},(_,i)=>!!frames[i]).every(Boolean)};},async api(){return {address:"AA:BB:CC:DD:EE:01"};},async tick(){}};
    const elements=new Map(),storage=new Map(),context=vm.createContext({ELinkProtocol:P,ELinkLocal:store,ELinkRenderer:{metadata:async()=>{const b=new Uint8Array(156);b.set([166,127,1,5]);P.view(b).setUint32(152,P.crc32(b.subarray(0,152)),true);return b;},png:()=>"preview",noticeBattery:async()=>{throw Error("unexpected notice render");}},console,crypto,Uint8Array,Uint16Array,Uint32Array,DataView,Date:options.clock?class extends Date{static now(){return options.clock();}}:Date,Math,Set,Map,TextEncoder,Promise,Error,Number,Array,String,Object,location:{reload(){}},window:{isSecureContext:true,addEventListener(){}},navigator:{bluetooth:{requestDevice:async()=>device,getDevices:async()=>[device]},userActivation:{isActive:true}},sessionStorage:{getItem:()=>null,setItem(){},removeItem(){}},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},setInterval(){},setTimeout(fn,ms){if(ms<=1000)queueMicrotask(fn);return 0;},clearTimeout(){},pending:()=>false,refresh:async()=>{},selectDevice(){},message(){},confirmAction:async()=>options.confirmRebind!==false,state:{jobs:[]},targets:new Set(),$:id=>{if(!elements.has(id))elements.set(id,{value:"",disabled:false,textContent:""});return elements.get(id);}});
    if(options.fireConnectTimeout)context.setTimeout=(fn,ms)=>{if(ms<=1000||ms===20000)queueMicrotask(fn);return 0;};
    const pendingTimers=new Map(),timers=context.setTimeout;let timerId=0;
    context.setTimeout=(fn,ms)=>ms===2000?(queueMicrotask(fn),0):ms>2000&&!options.fireConnectTimeout?(pendingTimers.set(++timerId,{fn,ms}),timerId):timers(fn,ms);
    context.clearTimeout=id=>pendingTimers.delete(id);
    vm.runInContext(fs.readFileSync(path.join(root,"ota.js"),"utf8"),context);vm.runInContext(fs.readFileSync(path.join(root,"browser-ble.js"),"utf8"),context);const actualAddress=await vm.runInContext('ELinkBLE.connect("",true,false)',context);
    return {context,model,commands,slots,jobs,updates,values,store,storage,device,pixels,album,commitCount:()=>commitCount,expire(ms){for(const [id,t] of pendingTimers)if(t.ms<=ms){pendingTimers.delete(id);t.fn();}},async execute(action,payload={}){const j={id:String(jobs.length),address:actualAddress,action,payload,status:"running",committed:false};jobs.push(j);context.nextJob=j;return {job:j,promise:vm.runInContext("ELinkBLE.execute(nextJob)",context)};}};
}
test("publish sends exact native bytes, checks offsets/checksum and generation",async()=>{
    const h=await harness(),{job,promise}=await h.execute("publish",{kind:"image",frame:P.bytes64(frame),sha256:await P.sha256(frame)}),receipt=await promise;
    assert.equal(receipt.result,"busy_completed");assert.equal(receipt.generation_after,10);assert.equal(receipt.bytes,8000);assert.equal(h.commitCount(),1);assert.equal(job.committed,true);
    const sent=Buffer.concat(h.commands.filter(c=>c[0]===0x96).map(c=>Buffer.from(c.subarray(3))));assert.deepEqual(sent,Buffer.from(frame));assert.equal(h.commands.find(c=>c[0]===0x99)[3],0);
});
test("wrong receive offset stops before committing",async()=>{const h=await harness({badPosition:true}),{job,promise}=await h.execute("publish",{kind:"image",frame:P.bytes64(frame),sha256:await P.sha256(frame)});await assert.rejects(promise,/接收位置/);assert.equal(h.commitCount(),0);assert.equal(job.committed,false);});

test("GATT DOMException retains command context without assigning its read-only message",async()=>{
    const cause=new DOMException("GATT operation failed for unknown reason.","NetworkError");
    const h=await harness({beforeWrite:async b=>{if(b[0]===0x95)throw cause;}}),r=await h.execute("publish",{kind:"image",frame:P.bytes64(frame),sha256:await P.sha256(frame)});
    await assert.rejects(r.promise,e=>{assert.match(e.message,/蓝牙写入 95.*GATT operation failed/);assert.equal(e.name,"NetworkError");assert.equal(e.cause,cause);assert.equal(e.connection,true);return true;});
    assert.equal(h.commitCount(),0);
});
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

test("search registers a new screen without connecting, then its card switches away from the selected old screen",async()=>{
    const h=await harness(),old=vm.runInContext('portable.address',h.context),registered=[];
    const other={id:"second-screen",name:"ELINK-BWR-EE0002",gatt:{connected:false,disconnect(){this.connected=false;},async connect(){this.connected=true;return this;},getPrimaryService:h.device.gatt.getPrimaryService}};
    h.context.navigator.bluetooth={requestDevice:async()=>other};h.context.targets.add(old);h.context.perform=async(button,fn)=>fn();
    h.store.api=async(path,b)=>{registered.push({path,...b});return {address:b.address};};let selected;h.context.selectDevice=a=>selected=a;
    await vm.runInContext('$("scan").onclick()',h.context);const next=selected;
    assert.notEqual(next,old);assert.equal(registered.length,1);assert.equal(registered[0].address,next);assert.equal(h.device.gatt.connected,true);assert.equal(other.gatt.connected,false);assert.equal(h.commands.length,0);assert.equal(h.jobs.length,0);assert.equal(vm.runInContext('portable.address',h.context),old);
    vm.runInContext('$("portable-address").value="AA:BB:CC:EE:00:01"',h.context);h.context.nextAddress=next;
    assert.equal(await vm.runInContext('ELinkBLE.connect(nextAddress,false,false)',h.context),next);assert.equal(h.device.gatt.connected,false);assert.equal(other.gatt.connected,true);assert.equal(vm.runInContext('portable.address',h.context),next);assert.equal(h.commands.length,0);
});

test("cancelled or busy search and a mismatched card preserve the current connection",async()=>{
    const h=await harness(),old=vm.runInContext('portable.address',h.context);h.context.oldAddress=old;h.store.device=()=>({name:h.device.name,settings:P.settings()});
    h.context.navigator.bluetooth.requestDevice=async()=>{throw Error("chooser cancelled");};await assert.rejects(vm.runInContext('ELinkBLE.discover()',h.context),/cancelled/);assert.equal(h.device.gatt.connected,true);
    const base=h.store.summary;h.store.summary=()=>({...base(),operation:{busy:true}});await assert.rejects(vm.runInContext('ELinkBLE.discover()',h.context),/尚未完成/);h.store.summary=base;
    h.context.navigator.bluetooth.requestDevice=async()=>({id:"wrong-device",name:"ELINK-BWR-EE0002",gatt:{connected:false}});
    await assert.rejects(vm.runInContext('ELinkBLE.connect(oldAddress,true,false)',h.context),/选择的不是当前屏幕/);assert.equal(h.device.gatt.connected,true);assert.equal(vm.runInContext('portable.address',h.context),old);assert.equal(h.commands.length,0);
});

test("searching an associated screen reuses its imported identity instead of adding a duplicate",async()=>{
    const h=await harness(),old="web-"+"ab".repeat(16);h.storage.set("elink-device-"+old,h.device.id);h.store.summary=()=>({devices:[{address:old,name:h.device.name}],jobs:[]});let registered;
    h.store.api=async(path,b)=>registered=b;assert.equal(await vm.runInContext('ELinkBLE.discover()',h.context),old);assert.equal(registered.address,old);assert.equal(h.device.gatt.connected,true);assert.equal(h.commands.length,0);
});
test("connection timeout stops retries and disconnects a late completion",async()=>{
    const h=await harness({fireConnectTimeout:true});let finish,calls=0;h.device.gatt.connected=false;h.device.gatt.connect=()=>{calls++;return new Promise(resolve=>finish=resolve);};
    await assert.rejects(vm.runInContext('ELinkBLE.connect("",true,false)',h.context),/超时/);assert.equal(calls,1);
    h.device.gatt.connected=true;finish(h.device.gatt);await Promise.resolve();assert.equal(h.device.gatt.connected,false);
});

test("idle disconnection stays idle and the next action reconnects without a probe or chooser; manual stop stays stopped",async()=>{
    const h=await harness();let connects=0;const before=h.commands.length;
    h.device.gatt.connect=async()=>{connects++;h.device.gatt.connected=true;return h.device.gatt;};
    h.context.navigator.bluetooth.requestDevice=async()=>{throw Error("Unexpected chooser during idle recovery");};
    h.device.gatt.connected=false;h.device.ongattserverdisconnected();await vm.runInContext("portableRecover()",h.context);
    assert.equal(connects,0);await vm.runInContext("ensurePortable(portable.address)",h.context);
    assert.equal(connects,1);assert.equal(h.device.gatt.connected,true);assert.equal(vm.runInContext("portable.session",h.context),h.device.id);
    assert.equal(h.commands.length,before);assert.equal(h.jobs.length,0);
    await vm.runInContext("ensurePortable(portable.address)",h.context);assert.equal(connects,1);
    await vm.runInContext("ELinkBLE.stop(true)",h.context);await vm.runInContext("portableRecover()",h.context);assert.equal(connects,1);
    const failed=await harness();let attempts=0;failed.device.gatt.connected=false;failed.device.ongattserverdisconnected();vm.runInContext('state.jobs=[{address:portable.address,status:"waiting"}]',failed.context);
    failed.device.gatt.connect=async()=>{attempts++;throw Error("unreachable");};await vm.runInContext("portableRecover()",failed.context);
    assert.equal(attempts,3);await vm.runInContext("portableRecover()",failed.context);assert.equal(attempts,3);
});
test("a delayed disconnect event cannot invalidate an already restored GATT session",async()=>{
    const h=await harness();h.device.ongattserverdisconnected();
    assert.equal(vm.runInContext("portable.session",h.context),h.device.id);
    const probe=await h.execute("probe");assert.equal((await probe.promise).result,"pixel_readback_verified");
});

test("idle connection releases at three minutes, waits for pending work and renews after an operation",async()=>{
    let now=1000000;const h=await harness({clock:()=>now});
    now+=179999;await vm.runInContext("ELinkBLE.releaseIdle()",h.context);assert.equal(h.device.gatt.connected,true);
    now++;h.jobs.push({status:"queued"});await vm.runInContext("ELinkBLE.releaseIdle()",h.context);assert.equal(h.device.gatt.connected,true);
    h.jobs.length=0;h.context.operationBusy=()=>true;await vm.runInContext("ELinkBLE.releaseIdle()",h.context);assert.equal(h.device.gatt.connected,true);
    h.context.operationBusy=()=>false;await vm.runInContext("ELinkBLE.releaseIdle()",h.context);assert.equal(h.device.gatt.connected,false);
    await vm.runInContext("portableRecover()",h.context);assert.equal(h.device.gatt.connected,false);
    await vm.runInContext("ensurePortable(portable.address)",h.context);assert.equal(h.device.gatt.connected,true);
    now+=170000;const probe=await h.execute("probe");await probe.promise;probe.job.status="succeeded";
    now+=179999;await vm.runInContext("ELinkBLE.releaseIdle()",h.context);assert.equal(h.device.gatt.connected,true);
    now++;await vm.runInContext("ELinkBLE.releaseIdle()",h.context);assert.equal(h.device.gatt.connected,false);
});

test("sync and settings wait for BUSY to finish instead of reporting early completion",async()=>{
    for(const action of ["sync","settings"]){const h=await harness({busyAfterSync:4});if(action==="settings")h.model.time=0;
        const {job,promise}=await h.execute(action,action==="settings"?P.settings():{});await promise;
        assert.equal(h.model.busyReads,0);assert.equal(job.progress,95);assert.equal(job.committed,true);assert.equal(h.values.values().next().value.busy,false);
    }
});

test("an immediate post-sync device error keeps the submitted result uncertain",async()=>{
    const h=await harness({syncError:4}),{job,promise}=await h.execute("sync");await assert.rejects(promise,/设备报错/);assert.equal(job.committed,true);assert.equal(job.status,"awaiting_display");
});

async function albumPayload(count=7,mode="image"){return {mode,auto_rotate:true,interval_minutes:1440,items:await Promise.all(Array.from({length:count},async(_,i)=>{const b=frame.slice();b[0]=i;return {template_id:String(i),frame:P.bytes64(b),sha256:await P.sha256(b),photo_x:i*10};}))};}
function pauseTransport(kind){
    let reached,release,used=false;const entered=new Promise(r=>reached=r),hold=new Promise(r=>release=r);
    return {entered,release,beforeWrite(b,a){if(!used&&((kind==="begin"&&b[0]===0xbd&&b[1]===1)||(kind==="status"&&a.writing&&b[0]===0x93)||(kind==="pixel"&&b[0]===0x96))){used=true;reached();return hold;}},beforeRead(a){if(!used&&kind==="read"&&a.writing){used=true;reached();return hold;}}};
}
test("seven-calendar preparation permits a slow initialization acknowledgement and status response",async()=>{
    for(const kind of ["begin","status","read"]){
        const pause=pauseTransport(kind),h=await harness({album:true,...pause}),run=await h.execute("album",await albumPayload(7,"calendar"));let failure;
        const result=run.promise.catch(e=>{failure=e;});await pause.entered;h.expire(9000);await new Promise(setImmediate);
        assert.equal(failure,undefined,kind+": initialization must not use the 8-second pixel deadline");assert.equal(h.device.gatt.connected,true);
        pause.release();const receipt=await result;assert.equal(receipt.album.count,7);assert.equal(h.model.page,8);assert.equal(h.commitCount(),1);
    }
});
test("a stuck album initialization stops at its longer deadline and cannot be automatically replayed",async()=>{
    const pause=pauseTransport("begin"),h=await harness({album:true,...pause}),run=await h.execute("album",await albumPayload(7,"calendar")),error=run.promise.catch(e=>e);
    await pause.entered;h.expire(30000);const e=await error;
    assert.match(e.message,/BD01.*超时/);assert.equal(e.timeout,true);assert.equal(run.job.committed,true);assert.equal(h.device.gatt.connected,false);
    assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===1).length,1);assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,0);
    h.device.gatt.connected=true;pause.release();await new Promise(setImmediate);assert.equal(h.device.gatt.connected,false);
});
test("ordinary pixel writes keep the short deadline after gallery preparation",async()=>{
    const pause=pauseTransport("pixel"),h=await harness({album:true,...pause}),run=await h.execute("album",await albumPayload(7,"calendar")),error=run.promise.catch(e=>e);
    await pause.entered;h.expire(9000);const e=await error;assert.match(e.message,/蓝牙写入.*超时/);assert.equal(h.device.gatt.connected,false);
    assert.equal(h.commitCount(),0);pause.release();await new Promise(setImmediate);
});

test("display commits can wait beyond eight seconds without disconnecting or replaying",async()=>{
    let reached,release;const entered=new Promise(r=>reached=r),hold=new Promise(r=>release=r);
    const h=await harness({album:true,beforeWrite(b){if(b[0]===0xbd&&b[1]===3){reached();return hold;}}}),run=await h.execute("album",await albumPayload(1));let failure;
    const result=run.promise.catch(e=>{failure=e;});await entered;h.expire(9000);await new Promise(setImmediate);
    assert.equal(failure,undefined);assert.equal(h.device.gatt.connected,true);release();await result;
    assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
});

test("seven-image playlist keeps every Flash check but a fresh probe reads only inventory and current display",async()=>{
    const h=await harness({album:true}),p=await albumPayload(),{promise}=await h.execute("album",p),receipt=await promise;
    assert.equal(receipt.offline,true);assert.equal(receipt.album.count,7);assert.equal(receipt.album.interval_minutes,1440);assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===2).length,224);
    assert.equal(h.commands.filter(b=>b[0]===0x97).length,0);assert.equal(h.commitCount(),1);
    assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===6).length,120);
    assert.ok(h.commands.findIndex(b=>b[0]===0xbd&&b[1]===6&&b[2]===119)<h.commands.findIndex(b=>b[0]===0xbd&&b[1]===1));
    const before=h.commands.length,again=await h.execute("album",p),reused=await again.promise;assert.equal(reused.transmitted_image_bytes,0);assert.equal(h.commands.slice(before).filter(b=>b[0]===0x96||b[0]===0xbd&&b[1]===6).length,0);
    const boundary=h.commands.length,probe=await h.execute("probe"),read=await probe.promise;assert.equal(read.album.count,7);assert.equal(read.album.editable,false);assert.equal(h.store.restored.length,0);assert.equal(h.commands.slice(boundary).filter(b=>b[0]===0xbd&&b[1]===5).length,0);assert.equal(h.commands.slice(boundary).filter(b=>b[0]===0x9a).length,64);
    assert.equal(read.result,"pixel_readback_verified");assert.ok(probe.job.payload.display_png);
});

test("unsupported or mismatched first-use checks stop before any gallery initialization",async()=>{
    for(const options of [{preflightUnsupported:true},{badPreflight:true}]){
        const h=await harness({album:true,...options}),run=await h.execute("album",await albumPayload(7,"calendar"));
        await assert.rejects(run.promise,/1\.5\.13|检查进度/);assert.equal(h.commands.filter(b=>b[0]===0xbd&&[1,2,3].includes(b[1])).length,0);assert.equal(run.job.committed,false);
    }
});
test("calendar album and single photo calendar use the native date commit without an extra refresh",async()=>{
    const h=await harness({album:true}),p=await albumPayload(2,"calendar"),run=await h.execute("album",p);await run.promise;assert.equal(h.model.page,8);
    const sequence=h.album.sequence,calibrate=await h.execute("sync");await calibrate.promise;assert.equal(h.model.page,8);assert.equal(h.album.running,true);assert.equal(h.album.sequence,sequence+1);assert.equal(h.album.frames.length,2);
    const f=P.photoFrame(frame,38),single=await h.execute("photo_calendar",{kind:"image",frame:P.bytes64(f),sha256:await P.sha256(f)});await single.promise;
    assert.equal(h.album.enabled,false);assert.equal(h.model.page,6);assert.equal(h.commands.filter(b=>b[0]===0x97).length,0);assert.equal(h.commands.filter(b=>b[0]===0x9c&&b[1]===3).length,1);
});
test("failed Flash step or corrupt retrieved data is never reported as a saved editable album",async()=>{
    const bad=await harness({album:true,badAlbumStep:true}),r=await bad.execute("album",await albumPayload(1));await assert.rejects(r.promise,/Flash step failed/);assert.equal(bad.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,0);
    const h=await harness({album:true,corruptAlbumReadback:true}),save=await h.execute("album",await albumPayload(1));await save.promise;const read=await h.execute("album_read",{index:0,sequence:h.album.sequence,crc32:P.crc32(h.album.frames[0])});await assert.rejects(read.promise,/CRC32/);assert.equal(h.store.restored.length,0);
});
test("lost album commit acknowledgement reconnects and verifies using reads without resubmitting",async()=>{
    const h=await harness({album:true,disconnectAlbumCommit:true}),run=await h.execute("album",await albumPayload(1)),receipt=await run.promise;
    assert.equal(receipt.result,"album_flash_verified");assert.equal(receipt.recovered_after_disconnect,true);assert.equal(run.job.committed,true);assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
    const commit=h.commands.findIndex(b=>b[0]===0xbd&&b[1]===3);assert.ok(h.commands.slice(commit+1).every(b=>b[0]===0x93||b[0]===0x9a||b[0]===0xbd&&b[1]===0));
});

test("saving defaults to rotation off even after recovering a lost commit acknowledgement",async()=>{
    for(const disconnectAlbumCommit of [false,true]){
        const h=await harness({album:true,disconnectAlbumCommit}),p=await albumPayload(2);delete p.auto_rotate;
        const run=await h.execute("album",p),receipt=await run.promise;
        assert.equal(receipt.album.count,2);assert.equal(receipt.album.enabled,false);assert.equal(receipt.album.running,false);assert.equal(h.model.page,7);assert.equal(h.commitCount(),1);
        assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===4).length,1);
    }
});

test("album verification advances from received pixel bytes and never reports a corrupt display as saved",async()=>{
    const h=await harness({album:true,disconnectAlbumCommit:true}),run=await h.execute("album",await albumPayload(1));await run.promise;
    const read=h.updates.filter(u=>u.phase?.startsWith("正在核对首张画面"));assert.deepEqual(read.map(u=>Number(u.phase.match(/(\d+)\/8000/)[1])),[1024,2048,3072,4000,5024,6048,7072,8000]);assert.equal(read[7].progress,97);
    assert.ok(h.updates.some(u=>u.phase?.includes("确认保存结果（1/3）")));assert.ok(h.updates.every(u=>!u.phase?.includes("提交回执中断")));assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
    const bad=await harness({album:true,corruptRAM:true}),save=await bad.execute("album",await albumPayload(1));await assert.rejects(save.promise,/首张像素读回不一致/);assert.equal(save.job.committed,true);assert.equal(bad.updates.some(u=>u.status==="succeeded"),false);
});

test("stalled recovery service and both characteristics have bounded retries without a second commit",{timeout:3000},async()=>{
    for(const stage of ["service","control","volts"]){
        const h=await harness({album:true,disconnectAlbumCommit:true}),base=h.device.gatt.getPrimaryService,entered=Array.from({length:3},()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};});let attempts=0;
        const stall=()=>{entered[attempts++].resolve();return new Promise(()=>{});};
        h.device.gatt.getPrimaryService=async(...args)=>{if(stage==="service")return stall();const service=await base(...args),get=service.getCharacteristic;service.getCharacteristic=id=>(id===(stage==="control"?P.control:P.volts))?stall():get(id);return service;};
        const run=await h.execute("album",await albumPayload(1)),result=run.promise.catch(e=>e);
        for(let i=0;i<3;i++){await entered[i].promise;await new Promise(setImmediate);h.expire(15000);}
        const error=await result;assert.equal(error.timeout,true);assert.match(error.message,/查找屏幕.*超时/);assert.equal(attempts,3);assert.equal(h.device.gatt.connected,false);assert.equal(run.job.committed,true);assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
    }
});

test("one stalled service lookup can recover on the next read-only attempt",{timeout:3000},async()=>{
    const h=await harness({album:true,disconnectAlbumCommit:true}),base=h.device.gatt.getPrimaryService;let resolve,attempts=0;const entered=new Promise(r=>resolve=r);
    h.device.gatt.getPrimaryService=(...args)=>{if(++attempts===1){resolve();return new Promise(()=>{});}return base(...args);};
    const run=await h.execute("album",await albumPayload(1));await entered;await new Promise(setImmediate);h.expire(15000);const receipt=await run.promise;
    assert.equal(receipt.result,"album_flash_verified");assert.equal(receipt.recovered_after_disconnect,true);assert.equal(attempts,2);assert.ok(h.updates.some(u=>u.phase?.includes("确认保存结果（2/3）")));assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
});

test("gallery checkpoints reduce queries while every ordered Flash step is still submitted",async()=>{
    const h=await harness({album:true}),run=await h.execute("album",await albumPayload());await run.promise;
    const from=h.commands.findIndex(b=>b[0]===0xbd&&b[1]===2),to=h.commands.findIndex(b=>b[0]===0xbd&&b[1]===3),saving=h.commands.slice(from,to);
    assert.equal(saving.filter(b=>b[0]===0xbd&&b[1]===2).length,224);
    assert.equal(saving.filter(b=>b[0]===0xbd&&b[1]===0).length,7);
    assert.equal(saving.filter((b,i)=>b[0]===0x93&&saving[i-1]?.[0]===0xbd&&saving[i-1]?.[1]===2).length,56);
});

test("reading one unknown slot transfers only that original and never writes a display or gallery",async()=>{
    const h=await harness({album:true}),save=await h.execute("album",await albumPayload());await save.promise;
    const before=h.commands.length,run=await h.execute("album_read",{index:5,sequence:h.album.sequence,crc32:P.crc32(h.album.frames[5])}),receipt=await run.promise,commands=h.commands.slice(before);
    assert.equal(receipt.result,"album_original_verified");assert.deepEqual(h.store.restored[5],h.album.frames[5]);assert.equal(commands.filter(b=>b[0]===0xbd&&b[1]===5).length,63);
    assert.ok(commands.every(b=>[0x93,0x9d].includes(b[0])||b[0]===0xbd&&(b[1]===0||b[1]===5&&b[2]===5)));
});

test("manual slot display preserves all stored images, stops rotation and reuses a cached original",async()=>{
    for(const mode of ["image","calendar"]){
        const h=await harness({album:true,cachedAlbum:true}),save=await h.execute("album",await albumPayload(7,mode));await save.promise;
        const originals=h.album.frames.map(f=>f.slice()),before=h.commands.length,index=4,run=await h.execute("album_show",{index,sequence:h.album.sequence,crc32:P.crc32(originals[index])}),receipt=await run.promise,commands=h.commands.slice(before);
        assert.equal(receipt.result,"album_slot_display_verified");assert.equal(receipt.album_slot,index);assert.equal(h.album.enabled,false);assert.equal(h.album.running,false);assert.deepEqual(h.album.frames,originals);
        assert.deepEqual(h.pixels,mode==="calendar"?P.photoFrame(originals[index],h.album.positions[index]):originals[index]);assert.equal(commands.filter(b=>b[0]===0xbd&&[1,2,3,5,6].includes(b[1])).length,0);
    }
});

test("a changed slot inventory is refused before reading an original or mutating the device",async()=>{
    const h=await harness({album:true}),save=await h.execute("album",await albumPayload(1));await save.promise;
    const before=h.commands.length,run=await h.execute("album_show",{index:0,sequence:h.album.sequence-1,crc32:P.crc32(h.album.frames[0])});await assert.rejects(run.promise,/图库已变化/);
    assert.ok(h.commands.slice(before).every(b=>[0x93,0x9d].includes(b[0])||b[0]===0xbd&&b[1]===0));assert.equal(run.job.committed,false);
});
test("a commit that never reached the screen stays uncertain without automatic replay",async()=>{
    const h=await harness({album:true,disconnectBeforeAlbumCommit:true}),run=await h.execute("album",await albumPayload(1));await assert.rejects(run.promise,/配置不一致/);assert.equal(run.job.committed,true);assert.equal(h.commitCount(),0);assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
});
test("gallery verification stops after three reconnect failures or a changed target, without replay",async()=>{
    const h=await harness({album:true,disconnectAlbumCommit:true});let attempts=0;h.device.gatt.connect=async()=>{attempts++;throw Error("unreachable");};const run=await h.execute("album",await albumPayload(1));
    await assert.rejects(run.promise,/unreachable/);assert.equal(attempts,3);assert.equal(h.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
    const changed=await harness({album:true,disconnectAlbumCommit:true});changed.device.gatt.connect=async()=>{changed.device.gatt.connected=true;vm.runInContext('portable.paused=true',changed.context);return changed.device.gatt;};const second=await changed.execute("album",await albumPayload(1));await assert.rejects(second.promise,/目标屏幕已变化/);assert.equal(changed.commands.filter(b=>b[0]===0xbd&&b[1]===3).length,1);
});
test("a changed framebuffer is never associated with old status",async()=>{
    const changed=await harness({changeDuringReadback:true}),probe=await changed.execute("probe"),receipt=await probe.promise;assert.equal(receipt.result,"pixel_readback_verified");assert.equal(receipt.generation_after,10);assert.ok(probe.job.payload.display_png);assert.equal(changed.commands.filter(b=>b[0]===0x9a).length,128);assert.ok(changed.commands.every(b=>[0x93,0x9d,0x9a,0xb4,0xbb].includes(b[0])));
});
test("a continuously changing screen stops after two pixel reads without claiming success",async()=>{
    const h=await harness({keepChanging:true}),probe=await h.execute("probe");await assert.rejects(probe.promise,/页面已变化/);assert.equal(probe.job.payload.display_png,undefined);assert.equal(h.commands.filter(b=>b[0]===0x9a).length,128);assert.ok(h.commands.every(b=>[0x93,0x9d,0x9a,0xb4,0xbb].includes(b[0])));
});
async function updatePackage(){const raw=new Uint8Array(60028);raw.fill(255);P.view(raw).setUint32(4,0x07fc0111,true);raw.set([121,19,165,249,134,236,90,6,11,0],0x300);raw.set([69,76,75,49,1],0xe2d4);raw.set([17,34,51,68],0xe2d4+28);return {format:"elink-update-1",board:"da14585-5pad-bwr-250x122",version:"1.5.11",application:P.bytes64(raw),sha256:await P.sha256(raw),firmware_id:"11223344"};}
test("large pixels use 63 packets only after a harmless capacity check; limited connections keep 471",async()=>{
    for(const [maxWrite,count] of [[136,63],[20,471]]){const h=await harness({album:true,maxWrite}),run=await h.execute("publish",{kind:"image",frame:P.bytes64(frame),sha256:await P.sha256(frame)}),r=await run.promise;assert.equal(h.commands.filter(b=>b[0]===0x96).length,count);assert.equal(r.pixel_packets,count);}
});
test("OTA reads back every padded byte before a single commit and verifies the rebooted version",async()=>{
    const h=await harness({ota:true,disconnectOTACommit:true}),run=await h.execute("ota",{package:await updatePackage()}),r=await run.promise;
    assert.equal(r.result,"ota_boot_verified");assert.equal(r.firmware_id,"11223344");const commands=h.commands;assert.equal(commands.filter(b=>b[0]===0xa4).length,1);assert.equal(commands.filter(b=>b[0]===0xa1).length,h.model.ota.length/128);assert.equal(commands.filter(b=>[0xa2,0xa3].includes(b[0])).length,h.model.ota.length/128);
    assert.ok(commands.findIndex(b=>b.length===136&&b[0]===0x93)<commands.findIndex(b=>b[0]===0xa0));assert.equal(commands.at(-1)[0],0x93);
});
test("bad OTA package/capacity stops before erase, corrupt readback never submits, wrong boot remains unknown",async()=>{
    const bad=await updatePackage();bad.sha256="0".repeat(64);const h=await harness({ota:true}),run=await h.execute("ota",{package:bad});await assert.rejects(run.promise,/SHA256/);assert.equal(h.commands.filter(b=>b[0]===0xa0).length,0);
    const tooLarge=await updatePackage(),raw=new Uint8Array(65535);raw.set(P.decode64(tooLarge.application));tooLarge.application=P.bytes64(raw);tooLarge.sha256=await P.sha256(raw);const big=await h.execute("ota",{package:tooLarge});await assert.rejects(big.promise,/应用镜像/);assert.equal(h.commands.filter(b=>b[0]===0xa0).length,0);
    const short=await harness({ota:true,maxWrite:20}),s=await short.execute("ota",{package:await updatePackage()});await assert.rejects(s.promise,/尚未擦写/);assert.equal(short.commands.filter(b=>b[0]===0xa0).length,0);
    const corrupt=await harness({ota:true,corruptOTA:true}),c=await corrupt.execute("ota",{package:await updatePackage()});await assert.rejects(c.promise,/未提交启动标记/);assert.equal(corrupt.commands.filter(b=>b[0]===0xa4).length,0);assert.equal(corrupt.commands.filter(b=>b[0]===0xa5).length,1);
    const boot=await harness({ota:true,wrongBoot:true}),b=await boot.execute("ota",{package:await updatePackage()});await assert.rejects(b.promise,/重启后版本/);assert.equal(b.job.committed,true);assert.equal(boot.commands.filter(b=>b[0]===0xa4).length,1);
});
