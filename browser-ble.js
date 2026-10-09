"use strict";
const portable={device:null,address:"",session:"",connecting:null,paused:sessionStorage.getItem("elink-paused")==="1",retryAfter:0};
const ELinkBLE = (() => {
    const P=ELinkProtocol,L=ELinkLocal,sleep=ms=>new Promise(r=>setTimeout(r,ms));
    let control,volts,caps={},battery={},working=false,closing=false;
    async function bounded(promise,label,ms=8000,device=portable.device){let timer,expired=false;try{return await Promise.race([promise.then(value=>{if(expired)device?.gatt.disconnect();return value;}),new Promise((_,reject)=>timer=setTimeout(()=>{expired=true;device?.gatt.disconnect();const e=Error(label+"超时，已断开蓝牙以停止旧命令");e.connection=e.timeout=true;reject(e);},ms))]);}finally{clearTimeout(timer);}}
    async function write(b){
        if(!portable.device?.gatt.connected||!control){const e=Error("屏幕蓝牙已断开");e.connection=true;throw e;}if(!(b instanceof Uint8Array)||!b.length||b.length>20)throw Error("蓝牙写入长度不合法");
        try{await bounded(control.writeValueWithResponse?control.writeValueWithResponse(b):control.writeValue(b),"蓝牙写入");}catch(e){e.connection=true;throw e;}
    }
    async function read(characteristic=control){if(!portable.device?.gatt.connected||!characteristic){const e=Error("屏幕蓝牙已断开");e.connection=true;throw e;}try{const v=await bounded(characteristic.readValue(),"蓝牙读取");return new Uint8Array(v.buffer,v.byteOffset,v.byteLength);}catch(e){e.connection=true;throw e;}}
    async function query(command,decode){
        for(let i=0;i<3;i++){await write(command);await sleep(120);const b=await read();try{return decode(b);}catch(e){if(i===2)throw e;}}
    }
    async function status(){return {...await query(Uint8Array.of(0x93),P.status),...caps,...battery};}
    function block(size){return b=>{if(b.length!==size)throw Error("像素读回长度不一致");return b;};}
    async function idle(s,seconds=95){const end=Date.now()+seconds*1000;while(s.busy){if(Date.now()>end)throw Error("屏幕仍忙，请等待后读取状态");await sleep(1000);s=await status();}return s;}
    async function committed(j,phase){await L.updateJob(j,{committed:true,status:"awaiting_display",phase});}
    async function configure(c,s){
        c=P.settings({...c,advertise_minutes:1,window_seconds:0});if(c.mode===1&&!s.global_clock_refresh)throw Error("此固件不支持整页快刷，请选择全刷或升级固件");if(c.mode===2&&!s.minute_region_refresh)throw Error("此固件不支持分钟局刷");if(c.clock_timezone!=="local"&&!s.timezone_clock)throw Error("荷兰时钟需要 V1.3.0 固件");
        s=await idle(s);if(s.timezone_clock)await write(P.timezone(c.clock_timezone));await write(Uint8Array.of(0x94,c.mode,c.full_every));await write(Uint8Array.of(0x99,c.refresh_minutes,1,0));const actual=await status(),wanted={mode:c.mode,full_every:c.full_every,clock_refresh_minutes:c.refresh_minutes,advertise_every_minutes:1,advertise_window_seconds:0};if(s.timezone_clock)wanted.clock_timezone=c.clock_timezone;if(actual.error||Object.entries(wanted).some(([k,v])=>actual[k]!==v))throw Error("设备设置读回不一致");return actual;
    }
    async function sync(c,s,quiet){
        if(s.offline_reminders)await write(P.packet(0xb3,[[4,-new Date().getTimezoneOffset()*60,true]]));const packet=P.sync(c.clock_timezone,new Date(),!!quiet&&!!s.quiet_sync);await write(packet);await sleep(300);return packet;
    }
    async function initialized(c,s){s=await configure(c,s);if(!s.time_initialized){await sync(c,s,true);s=await status();if(!s.time_initialized)throw Error("首次校时未取得设备确认，未开始传图");}return idle(s);}
    async function completed(j,generation,mode,transfer){
        const end=Date.now()+190000;while(Date.now()<end){await sleep(1000);const s=await status();if(s.error)throw Error("提交后设备报错："+s.error);if(!s.busy&&s.display_mode===mode&&(transfer===undefined||s.transfer_id===transfer)&&s.display_generation!==generation){await L.updateState(j.address,s);return s;}}
        throw Error("190 秒内未取得刷新完成回执，请读取状态并查看屏幕");
    }
    async function slots(){const values=[];for(let i=0;i<8;i++){const s=await query(Uint8Array.of(0xb4,i),P.slot);if(caps.reminder_summary)Object.assign(s,await query(Uint8Array.of(0xbb,i),P.runtime));values.push(s);}return values;}
    async function ram(){const frame=new Uint8Array(8000);for(const plane of [0,4000])for(let off=0;off<4000;off+=128){const b=await query(P.packet(0x9a,[[2,plane+off]]),block(128));frame.set(b.subarray(0,Math.min(128,4000-off)),plane+off);}return frame;}
    async function previewReminder(j,s,values){
        if(s.display_mode!==2||values[0]?.last_slot<0||s.busy)return;const slot=values[values[0].last_slot];if(!slot||![254,252].includes(slot.state)||s.transfer_id!==(slot.token&65535))return;
        const state=L.summary(),r=state.reminders.find(r=>r.address===j.address&&r.token===slot.token),old=r?.job_id?L.job(r.job_id):null;if(!old||old.status!=="succeeded")return;const frame=await ram(),after=await status();if(after.busy||after.error||after.display_generation!==s.display_generation||after.transfer_id!==s.transfer_id)return;
        old.payload={...old.payload,display_png:ELinkRenderer.png(frame),frame:P.bytes64(frame),png:ELinkRenderer.png(frame),sha256:await P.sha256(frame)};old.receipt={...old.receipt,result:"offline_reminder_ram_verified",generation_after:s.display_generation,transfer_id:s.transfer_id,firmware_id:s.firmware_id,sha256:old.payload.sha256,optical_result_verified:false};await L.persist();
    }
    async function overview(j,s){
        if(!s.reminder_summary)throw Error("任务汇总需要 V1.5.0 固件");s=await idle(s,190);if(!s.time_initialized)s=await initialized(L.device(j.address).settings,s);
        await write(P.packet(0xb3,[[4,-new Date().getTimezoneOffset()*60,true]]));const generation=s.display_generation;await committed(j,"切换今日任务汇总，等待屏幕完成");await write(Uint8Array.of(0xb9));const after=await completed(j,generation,5),frame=await ram(),check=await status();if(check.busy||check.display_mode!==5||check.display_generation!==after.display_generation)throw Error("读回期间页面已变化，请重新读取状态");
        j.payload.display_png=ELinkRenderer.png(frame);await L.updateJob(j,{payload:j.payload});L.stopPlans(j.address);return {...check,result:"reminder_summary_ram_verified",generation_after:check.display_generation,summary_sha256:await P.sha256(frame),optical_result_verified:false};
    }
    async function cancelTokens(j,tokens,values){
        for(const token of new Set(tokens.filter(Boolean)))for(const s of values){if(s.token!==token||s.state===248)continue;await committed(j,"取消日程并读回确认");await write(P.packet(0xb5,[[1,s.slot],[4,token]]));const check=await query(Uint8Array.of(0xb4,s.slot),P.slot);if(check.token!==token||check.state!==248)throw Error("设备未确认日程取消");}
    }
    async function install(j,s){
        if(!s.reminder_summary)throw Error("离线重复提醒需要 V1.5.0 或更新固件");s=await idle(s,190);let values=await slots();const p=j.payload;
        if(p.operation==="cancel"){await cancelTokens(j,[p.token,p.previous_token],values);return {...await overview(j,await status()),result:"reminder_cancel_verified",token:p.token};}
        if(!s.time_initialized)s=await initialized(L.device(j.address).settings,s);await write(P.packet(0xb3,[[4,-new Date().getTimezoneOffset()*60,true]]));const frame=P.decode64(p.frame);if(frame.length!==8000||await P.sha256(frame)!==p.sha256)throw Error("提醒像素校验失败");
        const checksum=P.crc32(frame),metadata=await ELinkRenderer.metadata(p.title,p.options,s.reminder_large_text),existing=values.find(v=>v.token===p.token&&[254,252].includes(v.state));let slot;
        if(existing){if(existing.due!==p.due||existing.crc32!==checksum)throw Error("提醒标识与设备内容冲突");slot=existing.slot;}
        else{
            const free=values.find(v=>v.state!==254);if(!free)throw Error("设备提醒存储已满，请先取消旧提醒");slot=free.slot;
            await L.updateJob(j,{phase:"提前写入提醒画面到设备 Flash"});await write(Uint8Array.of(0xb6));await write(P.packet(0xb0,[[1,slot],[4,p.token],[4,p.due],[4,checksum]]));
            for(let off=0;off<8000;off+=17){await write(P.packet(0xb1,[[2,off]],frame.subarray(off,off+17)));if(Math.floor(off/17)%32===0||off+17>=8000){const check=await query(Uint8Array.of(0xb4,slot),P.slot);if(check.received!==Math.min(off+17,8000)||!check.writing)throw Error("提醒写入位置不一致");await L.updateJob(j,{progress:5+Math.floor(65*Math.min(off+17,8000)/8000)});}}
            await L.updateJob(j,{phase:"全量读回提醒像素，确认后激活"});const readback=new Uint8Array(8000);
            for(let off=0;off<8000;off+=128)readback.set(await query(P.packet(0xb7,[[1,slot],[2,off]]),block(Math.min(128,8000-off))),off);if(!P.equal(readback,frame))throw Error("全量提醒像素读回失败，未启用日程");
            for(let off=0;off<156;off+=18)await write(P.packet(0xb8,[[1,off]],metadata.subarray(off,off+18)));
            await committed(j,"启用已验证的离线提醒，等待设备确认");await write(P.packet(0xb2,[[4,p.token]]));
        }
        const readback=new Uint8Array(156);for(const off of [0,128])readback.set(await query(P.packet(0xba,[[1,slot],[2,off]]),block(Math.min(128,156-off))),off);if(!P.equal(readback,metadata))throw Error("提醒策略读回不一致");
        const check=await query(Uint8Array.of(0xb4,slot),P.slot);if(check.token!==p.token||![254,252].includes(check.state)||check.due!==p.due||check.crc32!==checksum||!check.clock_ready)throw Error("设备尚未确认离线提醒已启用");
        await cancelTokens(j,[p.previous_token],await slots());const summary=await overview(j,await status()),runtime=await query(Uint8Array.of(0xbb,slot),P.runtime);
        return {...summary,...runtime,result:"reminder_flash_verified",slot,token:p.token,due:p.due,crc32:checksum,sha256:p.sha256,bytes:8000,offline:true,slot_state:check.state,optical_result_verified:false};
    }
    async function publish(j,s){
        let p=j.payload;if(p.kind==="notice"){p={...p,...await ELinkRenderer.noticeBattery(p.png,s.battery_percent),battery};await L.updateJob(j,{payload:p});}
        const frame=P.decode64(p.frame);if(frame.length!==8000||await P.sha256(frame)!==p.sha256)throw Error("排队画面像素校验失败");
        if(p.scheduled){const old=L.summary().jobs.find(old=>old.address===j.address&&old.action==="publish"&&old.status==="succeeded");if(old?.sha256===p.sha256&&s.display_mode===2&&!s.busy&&old.receipt.transfer_id===s.transfer_id&&old.receipt.generation_after===s.display_generation&&old.receipt.firmware_id===s.firmware_id)return {...old.receipt,result:"content_unchanged"};}
        s=await initialized(L.device(j.address).settings,s);const transfer=1+crypto.getRandomValues(new Uint16Array(1))[0]%65535,generation=s.display_generation,sum=frame.reduce((a,b)=>a+b,0)&65535;
        await L.updateJob(j,{phase:"发送图片像素并核对接收位置"});await write(P.packet(0x95,[[2,transfer],[2,sum]]));let check=await status();if(check.error||check.transfer_id!==transfer||check.display_mode!==1)throw Error("设备拒绝开始传图");
        for(let off=0;off<8000;off+=17){await write(P.packet(0x96,[[2,off]],frame.subarray(off,off+17)));if((Math.floor(off/17)+1)%32===0||off+17>=8000){check=await status();const expected=Math.min(off+17,8000);if(check.error||check.received!==expected)throw Error("接收位置不一致，已停止发送");await L.updateJob(j,{progress:5+Math.floor(85*expected/8000)});}}
        if(check.sum16!==sum)throw Error("图片校验和不一致");const receipt={transfer_id:transfer,sha256:p.sha256,generation_before:generation,bytes:8000,firmware_id:s.firmware_id,battery};await L.updateJob(j,{receipt,progress:92});await committed(j,"图片已接收，等待清屏和刷新回执");await write(P.packet(0x97,[[2,transfer]]));const after=await completed(j,generation,2,transfer);
        return {...receipt,result:"busy_completed",generation_after:after.display_generation,optical_result_verified:false};
    }
    async function execute(j){
        if(working)throw Error("蓝牙事务尚未结束");working=true;caps={};battery={};
        try{
            if(portable.address!==j.address||!portable.device?.gatt.connected){const e=Error("目标屏幕未连接");e.connection=true;throw e;}
            let s;try{s=await query(Uint8Array.of(0x93),P.status);}catch(e){if(e.connection)throw e;s={protocol:0,display_mode:"legacy",note:"原版仅支持校时"};}
            if(s.protocol===1){try{caps=await query(Uint8Array.of(0x9d),P.capabilities);}catch(e){if(e.connection)throw e;await query(Uint8Array.of(0x93),P.status);}}
            try{battery={...P.battery(await read(volts)),battery_read_at:Date.now()/1000};}catch(e){battery={battery_mv:null,battery_percent:null,battery_error:e.message,battery_read_at:Date.now()/1000};if(!portable.device?.gatt.connected)throw e;}
            s={...s,...caps,...battery};await L.updateState(j.address,s);const c=L.device(j.address).settings;
            if(j.action==="probe"){if(s.offline_reminders&&!s.busy){const values=await slots();s.reminder_slots=values;await L.reconcile(j.address,values);await L.updateState(j.address,s);await previewReminder(j,s,values);}return s;}
            if(j.action==="sync"){
                if(s.protocol===1)s=await configure(c,s);else if(c.clock_timezone!=="local")throw Error("此固件不支持荷兰时间");const quiet=![0,3].includes(s.display_mode);if(!quiet||!s.quiet_sync)await committed(j,"校时已提交，等待读回确认");const packet=await sync(c,s,quiet);if(s.protocol===1){s=await status();if(s.display_mode===5)await overview(j,s);await L.updateState(j.address,await status());if(s.offline_reminders&&!s.busy)await L.reconcile(j.address,await slots());}return {result:"gatt_write_confirmed",packet_hex:P.hex(packet),physical_display_confirmed:false};
            }
            if(s.protocol!==1)throw Error("此操作需要 ELK1 优化固件，原版仅能校时");
            if(j.action==="settings"){
                const settings=P.settings(j.payload);let actual=await configure(settings,s);if(!s.time_initialized||s.clock_timezone!==settings.clock_timezone){await sync(settings,actual,![0,3].includes(s.display_mode));actual=await status();if(s.display_mode===5)actual=await overview(j,actual);}await L.saveSettings(j.address,{...settings,advertise_minutes:1,window_seconds:0});await L.updateState(j.address,actual);return actual;
            }
            if(j.action==="overview")return await overview(j,s);if(j.action==="reminder")return await install(j,s);if(j.action==="publish")return await publish(j,s);
            if(["default","resume","calendar"].includes(j.action)){
                const cap={default:"default_page",resume:"bold_clock",calendar:"embedded_calendar"}[j.action];if(!s[cap])throw Error("此固件不支持所选页面，请先升级");s=await idle(s);
                if(j.action!=="default"){const config=P.settings({...c,...j.payload});s=await configure(config,s);await sync(config,s,true);s=await idle(await status());await L.saveSettings(j.address,{...config,advertise_minutes:1,window_seconds:0});}
                const [view,mode]={default:[2,4],resume:[0,0],calendar:[1,3]}[j.action];await committed(j,"切换页面，等待屏幕刷新完成");await write(Uint8Array.of(0x9c,view));const after=await completed(j,s.display_generation,mode);L.stopPlans(j.address);return {...after,result:"busy_completed",optical_result_verified:false};
            }
            throw Error("未知设备动作");
        }finally{working=false;}
    }
    async function address(device,manual=""){return manual||"web-"+(await P.sha256(new TextEncoder().encode(device.id))).slice(0,32);}
    async function connect(expected,choose,restore){
        L.assertOwner();let dev;
        if(!navigator.bluetooth?.requestDevice)throw Error("此浏览器不支持网页蓝牙；安卓请使用 Chrome");if(!window.isSecureContext)throw Error("网页蓝牙需要 HTTPS");
        const manual=(choose?$("portable-address").value.trim().toUpperCase():"")||(expected&&!expected.startsWith("web-")?expected:"");
        if(manual&&!/^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(manual))throw Error("手动 MAC 格式不正确，可留空");
        $("portable-status").textContent="正在连接屏幕…";$("portable-connect").disabled=true;
        if(!choose){if(portable.address===expected)dev=portable.device;if(!dev&&navigator.bluetooth.getDevices){const known=await navigator.bluetooth.getDevices(),saved=localStorage.getItem("elink-device-"+expected);dev=known.find(d=>d.id===saved);if(!dev)for(const d of known)if(await address(d)===expected){dev=d;break;}}}
        if(!dev){if(restore||navigator.userActivation?.isActive===false)throw Error("请点击连接，选择 ELINK 开头的设备");dev=await navigator.bluetooth.requestDevice({filters:[{namePrefix:"ELINK-"},{namePrefix:"DLG-"}],optionalServices:[P.service]});}
        if(manual&&dev.name?.startsWith("ELINK-BWR-")&&dev.name!=="ELINK-BWR-"+manual.replaceAll(":","").slice(-6))throw Error("所选屏幕与 MAC 不一致");let actual=await address(dev,manual);
        if(expected&&actual!==expected){
            if(localStorage.getItem("elink-device-"+expected)===dev.id)actual=expected;
            else if(choose&&L.device(expected).name===dev.name&&await confirmAction("将所选的 "+dev.name+" 关联到当前屏幕记录？跨站点迁移后浏览器蓝牙标识会变化，请核对设备名称。"))actual=expected;
            else throw Error("选择的不是当前屏幕，请核对设备名称");
        }
        if(portable.device&&portable.device!==dev){if(working||pending(portable.address))throw Error("当前屏幕任务尚未完成，请先等待或取消队列");await stop();}
        try{
            for(let attempt=0;;attempt++){try{if(!dev.gatt.connected)await bounded(dev.gatt.connect(),"连接屏幕",20000,dev);break;}catch(e){if(e.timeout||attempt===2)throw e;await sleep(500*(attempt+1));}}
            const service=await dev.gatt.getPrimaryService(P.service);control=await service.getCharacteristic(P.control);try{volts=await service.getCharacteristic(P.volts);}catch{volts=null;}
            await L.api("/api/register",{address:actual,name:dev.name});portable.device=dev;portable.address=actual;portable.session=dev.id;portable.paused=false;sessionStorage.removeItem("elink-paused");localStorage.setItem("elink-last-address",actual);localStorage.setItem("elink-device-"+actual,dev.id);
            dev.ongattserverdisconnected=()=>{if(portable.device!==dev)return;portable.session="";control=volts=null;$("portable-disconnect").disabled=true;$("portable-connect").disabled=false;$("portable-status").textContent=closing?"屏幕已断开":"屏幕失联，正在等待重连 · 未确认提交不会重复发送";};
            $("portable-disconnect").disabled=false;$("portable-status").textContent="已连接 "+dev.name+" · 本机蓝牙";await refresh();return actual;
        }catch(e){if(dev.gatt.connected)dev.gatt.disconnect();throw e;}finally{$("portable-connect").disabled=!!portable.device?.gatt.connected;}
    }
    async function stop(forget=false){closing=true;portable.session="";if(forget){portable.paused=true;sessionStorage.setItem("elink-paused","1");}portable.device?.gatt.disconnect();control=volts=null;$("portable-status").textContent="屏幕已断开 · 下次操作先重连";$("portable-connect").disabled=false;$("portable-disconnect").disabled=true;closing=false;}
    return {execute,connect,stop,working:()=>working};
})();
async function ensurePortable(address,choose=false,restore=false){
    if(!restore){portable.paused=false;sessionStorage.removeItem("elink-paused");}
    if(address&&portable.address&&address!==portable.address&&!choose){const deadline=Date.now()+300000;while(ELinkLocal.summary().jobs.some(j=>j.address===portable.address&&["queued","waiting","running","awaiting_display"].includes(j.status))){if(portable.paused||Date.now()>deadline)throw Error("上一台屏幕尚未完成，请查看顶部进度后重试");await new Promise(r=>setTimeout(r,500));}}
    if(portable.connecting)await portable.connecting;if(!choose&&portable.address===address&&portable.session&&portable.device?.gatt.connected)return address;
    portable.connecting=ELinkBLE.connect(address,choose,restore);try{return await portable.connecting;}finally{portable.connecting=null;}
}
async function portableRestore(){const address=localStorage.getItem("elink-last-address");if(portable.paused||!address||!navigator.bluetooth?.getDevices)return;try{await ensurePortable(address,false,true);}catch{$("portable-status").textContent="屏幕未连接 · 点击连接可恢复";}}
function portableRecover(){if(portable.paused||portable.connecting||ELinkBLE.working()||Date.now()<portable.retryAfter)return;const j=state.jobs.find(j=>["queued","waiting"].includes(j.status)&&(portable.address===j.address||localStorage.getItem("elink-device-"+j.address)));if(!j||(portable.device?.gatt.connected&&portable.address===j.address))return;if(portable.device?.gatt.connected&&pending(portable.address))return;portable.retryAfter=Date.now()+15000;ensurePortable(j.address,false,true).catch(e=>{$("portable-status").textContent="等待连接屏幕 · "+e.message;});}
$("portable-connect").onclick=async()=>{try{await ELinkLocal.ready;const target=targets.size===1?[...targets][0]:"",address=await ensurePortable(target,true);selectDevice(address);if(!pending(address))await api("/api/jobs",{address,action:"probe"});}catch(e){message(e.message,true);$("portable-status").textContent="屏幕未连接 · "+e.message;$("portable-connect").disabled=false;}};
$("portable-disconnect").onclick=()=>ELinkBLE.stop(true);$("scan").onclick=()=>$("portable-connect").onclick();$("portable-status").textContent="屏幕未连接 · 选择 ELINK 开头的设备";
window.addEventListener("pagehide",()=>ELinkBLE.stop());window.addEventListener("pageshow",e=>{if(e.persisted)location.reload();});
setInterval(()=>ELinkLocal.tick().catch(e=>message(e.message,true)),1000);
