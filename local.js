"use strict";
// Browser-owned data. No household backend, account, or remote Bluetooth endpoint.
const ELinkLocal = (() => {
    const P=ELinkProtocol, unfinished=["queued","waiting","running","awaiting_display"], active=["running","awaiting_display"], addressPattern=/^(?:web-[0-9a-f]{32}|(?:[0-9A-F]{2}:){5}[0-9A-F]{2})$/;
    const empty=()=>({format:"elink-web",schema:1,devices:[],templates:[],jobs:[],plans:[],reminders:[]});
    const now=()=>Date.now()/1000,id=()=>crypto.randomUUID().replaceAll("-",""),copy=v=>structuredClone(v);
    let db,data,configuration,owner=false,fatal="",writing=Promise.resolve(),mutations=Promise.resolve(),workerRunning=false,releaseOwner;
    const ready=(async()=>{
        if(!window.isSecureContext)throw Error("请使用 HTTPS 地址或本机 localhost");
        db=await new Promise((resolve,reject)=>{const r=indexedDB.open("elink-web",1);r.onupgradeneeded=()=>r.result.createObjectStore("workspace");r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error("数据库正在升级，请关闭其他旧页面后重试"));});
        data=await read()||empty();configuration=await (await fetch("config.json?v=1.1.3")).json();
        if(navigator.locks){await new Promise((resolve,reject)=>{navigator.locks.request("elink-web-workspace",{ifAvailable:true},async lock=>{owner=!!lock;resolve();if(lock)await new Promise(r=>releaseOwner=r);}).catch(reject);});}
        else throw Error("此浏览器缺少安全的多标签页控制；安卓请使用最新版 Chrome");
        if(owner){data=await read()||empty();if(data.app_version!==configuration.version){for(const d of data.devices)d.state={...(d.state||{}),capabilities_stale:true};data.app_version=configuration.version;}for(const j of data.jobs)if(active.includes(j.status)){j.status="delivery_unknown";j.error="页面关闭时任务未取得完成回执，请连接屏幕后核对";j.updated=now();}await persist();}
        return data;
    })();
    function read(key="current"){return new Promise((resolve,reject)=>{const r=db.transaction("workspace").objectStore("workspace").get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
    function assertOwner(){if(!owner)throw Error("另一标签页正在管理此工作区，请关闭它后重新载入本页");if(fatal)throw Error(fatal);}
    async function persist(){
        assertOwner();const snapshot=copy(data);
        writing=writing.then(()=>new Promise((resolve,reject)=>{const t=db.transaction("workspace","readwrite");t.objectStore("workspace").put(snapshot,"current");t.oncomplete=resolve;t.onabort=t.onerror=()=>reject(t.error||Error("存储失败"));}));
        try{await writing;}catch(e){fatal="浏览器数据保存失败，已停止下发。请导出备份并检查存储空间："+e.message;throw Error(fatal);}
    }
    function device(address){const d=data.devices.find(d=>d.address===address);if(!d)throw Error("屏幕尚未登记");return d;}
    function busy(address){return data.jobs.some(j=>j.address===address&&unfinished.includes(j.status));}
    function operationState(){const jobs=data.jobs.filter(j=>unfinished.includes(j.status)).length,pending=data.reminders.filter(r=>r.status==="pending").length;return {busy:!!(jobs||pending),jobs,pending_reminders:pending};}
    function requireIdle(){if(operationState().busy)throw Error("屏幕操作尚未完成，请查看顶部执行进度；等待任务可先取消");}
    function job(ident){const j=data.jobs.find(j=>j.id===ident);if(!j)throw Error("任务不存在");return j;}
    function template(ident){const t=data.templates.find(t=>t.id===ident);if(!t)throw Error("图片不存在");return t;}
    function trim(){const protectedIds=new Set(data.reminders.map(r=>r.job_id));const complete=data.jobs.filter(j=>!unfinished.includes(j.status)&&!protectedIds.has(j.id)).sort((a,b)=>b.created-a.created);const keep=new Set(complete.slice(0,100).map(j=>j.id));data.jobs=data.jobs.filter(j=>unfinished.includes(j.status)||protectedIds.has(j.id)||keep.has(j.id));}
    function enqueue(address,action,payload={}){
        device(address);if(busy(address))throw Error("此屏幕已有未完成任务，请等待或取消");
        if(!["probe","sync","settings","default","resume","calendar","publish","photo_calendar","album","album_stop","overview","reminder","ota"].includes(action))throw Error("不支持此操作");
        const j={id:id(),address,action,payload:copy(payload),status:"queued",progress:0,error:null,receipt:{},created:now(),updated:now(),due:now(),attempts:0,phase:"等待连接屏幕",committed:false};data.jobs.push(j);trim();return j;
    }
    function snapshot(t){return {template_id:t.id,...ELinkSnapshot(t)};}
    async function queueRequest(address,action,payload){
        payload=payload||{};
        if(["publish","photo_calendar"].includes(action)){const t=template(payload.template_id),x=payload.photo_x??38;payload=snapshot(t);if(action==="photo_calendar"){if(payload.kind!=="image")throw Error("图片日历只能选择图片");const frame=P.photoFrame(P.decode64(payload.frame),x);payload={...payload,photo_x:x,frame:P.bytes64(frame),png:ELinkRenderer.png(frame),sha256:await P.sha256(frame)};}}
        if(action==="album"){
            if(Object.keys(payload).sort().join(",")!=="interval_minutes,items,mode"||!["image","calendar"].includes(payload.mode)||!Array.isArray(payload.items)||!payload.items.length||payload.items.length>Math.min(7,device(address).state?.album_capacity||4))throw Error("图库数量超出此固件上限，7张需1.5.11并读取状态");P.int(payload.interval_minutes,60,10080,"轮播间隔");const seen=new Set();
            payload={...payload,items:payload.items.map(item=>{if(!item||Object.keys(item).sort().join(",")!=="photo_x,template_id"||seen.has(item.template_id))throw Error("图库图片不能重复");seen.add(item.template_id);P.int(item.photo_x,0,76,"取景位置");const t=template(item.template_id),frame=snapshot(t);if(frame.kind!=="image")throw Error("图库仅接受图片");return {...frame,photo_x:item.photo_x};})};
        }
        if(action==="album_stop"&&Object.keys(payload).length)throw Error("停止轮播不接受额外设置");
        if(action==="ota")await ELinkOTA.validate(payload.package);
        if(action==="settings")payload=P.settings(payload);if(action==="resume"||action==="calendar")payload=P.settings({...device(address).settings,...payload});if(action==="reminder")throw Error("请通过日程页面创建提醒");return enqueue(address,action,payload);
    }
    function ELinkSnapshot(t){const s=JSON.parse(t.spec);return {kind:s.kind,frame:t.frame,png:t.png,sha256:t.sha256};}
    function reminder(ident){const r=data.reminders.find(r=>r.id===ident);if(!r)throw Error("日程不存在");return r;}
    function randomToken(){let token;do{token=crypto.getRandomValues(new Uint32Array(1))[0];}while(!token||data.reminders.some(r=>r.token===token));return token;}
    function summary(){
        const jobs=[...data.jobs.filter(j=>unfinished.includes(j.status)),...data.jobs.filter(j=>!unfinished.includes(j.status)).sort((a,b)=>b.created-a.created).slice(0,100)];
        return {devices:data.devices.map(d=>({...copy(d),browser_connected:typeof portable!=="undefined"&&portable.address===d.address&&!!portable.device?.gatt.connected,preview:preview(d)})),templates:data.templates.map(t=>{const s=JSON.parse(t.spec);delete s.image;return {...t,spec:JSON.stringify(s),frame:undefined,png:undefined};}),jobs:jobs.map(j=>({...copy(j),payload:undefined,sha256:j.payload.sha256,has_preview:!!(j.payload.display_png||j.payload.png)})),plans:copy(data.plans),reminders:data.reminders.map(r=>{const j=data.jobs.find(j=>j.id===r.job_id);return {...copy(r),job_status:j?.status,job_error:j?.error};}),operation:operationState(),worker_alive:owner&&!fatal,worker_error:fatal};
    }
    function preview(d){
        const s=d.state||{};if(s.busy||s.error||s.preview_error)return null;
        const j=[...data.jobs].sort((a,b)=>b.updated-a.updated).find(j=>j.address===d.address&&j.status==="succeeded"&&j.receipt.generation_after===s.display_generation&&j.receipt.firmware_id===s.firmware_id&&j.receipt.transfer_id===s.transfer_id&&(j.action!=="probe"||j.receipt.display_mode===s.display_mode&&j.receipt.result==="pixel_readback_verified")&&(j.payload.display_png||j.payload.png));
        return j?{url:"/api/jobs/"+j.id+"/preview.png",label:"已核对设备回执 · 实际画面以屏幕为准"}:null;
    }
    function resource(path){
        if(path.startsWith("blob:")||path.startsWith("data:image/png;base64,"))return path;
        const match=path.match(/^\/api\/(templates|jobs)\/([0-9a-f]{32})\/preview\.png/);
        if(match){const item=match[1]==="templates"?data.templates.find(t=>t.id===match[2]):data.jobs.find(j=>j.id===match[2])?.payload;return item?"data:image/png;base64,"+(item.display_png||item.png):"";}
        return new URL(path.replace(/^\//,""),new URL(".",location.href)).href;
    }
    function download(value,name){const link=document.createElement("a"),url=URL.createObjectURL(new Blob([JSON.stringify(value)],{type:"application/json"}));link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
    function backup(){download({...copy(data),exported_at:new Date().toISOString()},"elink-backup-"+new Date().toISOString().slice(0,10)+".json");}
    async function previousBackup(){await ready;const value=await read("before-import");if(!value)throw Error("尚无导入前备份");download(value,"elink-before-import.json");}
    async function validateImport(value){
        if(!value||value.format!=="elink-web"||value.schema!==1)throw Error("请选择 ELINK Web JSON 备份；旧版 SQLite 请先用转换工具导出");
        const limits={devices:100,templates:100,jobs:1000,plans:100,reminders:1000};for(const [k,n] of Object.entries(limits))if(!Array.isArray(value[k])||value[k].length>n)throw Error("备份列表不合法："+k);
        const addresses=new Set(),ids=new Set();for(const d of value.devices){if(!addressPattern.test(d.address)||addresses.has(d.address)||typeof d.name!=="string"||d.name.length>100)throw Error("备份屏幕地址或名称无效");addresses.add(d.address);d.settings=P.settings(d.settings);d.connection="browser";d.state={};d.preview=null;}
        for(const t of value.templates){if(!/^[0-9a-f]{32}$/.test(t.id)||ids.has(t.id)||typeof t.title!=="string"||t.title.length>80)throw Error("备份图片无效");ids.add(t.id);const s=JSON.parse(t.spec);if(!["image","notice","clock","meeting","calendar"].includes(s.kind))throw Error("备份模板类型无效");const b=P.decode64(t.frame);if(b.length!==8000||await P.sha256(b)!==t.sha256||(s.native_frame&&!P.equal(P.decode64(s.native_frame),b)))throw Error("备份原生像素校验失败");t.png=ELinkRenderer.png(b);}
        const jobIds=new Set();for(const j of value.jobs){if(!/^[0-9a-f]{32}$/.test(j.id)||jobIds.has(j.id)||!addressPattern.test(j.address)||typeof j.action!=="string"||!Number.isFinite(j.created))throw Error("备份任务无效");jobIds.add(j.id);if(j.payload?.frame){const b=P.decode64(j.payload.frame);if(b.length!==8000||await P.sha256(b)!==j.payload.sha256)throw Error("备份任务像素校验失败");j.payload.png=ELinkRenderer.png(b);}if(j.payload?.display_png)delete j.payload.display_png;if(unfinished.includes(j.status)){j.status="cancelled";j.error="导入备份后停止旧队列，请核对设备后重新下发";}j.receipt=j.receipt&&typeof j.receipt==="object"?j.receipt:{};j.payload=j.payload||{};}
        const tokens=new Set(),reminderIds=new Set();for(const r of value.reminders){if(!/^[0-9a-f]{32}$/.test(r.id)||reminderIds.has(r.id)||(!addresses.has(r.address)&&(!["completed","cancelled"].includes(r.status)||!addressPattern.test(r.address)))||typeof r.title!=="string"||r.title.length>80||typeof r.body!=="string"||r.body.length>240||!Number.isInteger(r.due)||r.due<0||r.due>2587680000||(r.job_id&&!jobIds.has(r.job_id)))throw Error("备份提醒无效");reminderIds.add(r.id);P.options(JSON.parse(r.options));P.int(r.token,1,0xffffffff,"提醒标识");if(tokens.has(r.token))throw Error("备份提醒标识重复");tokens.add(r.token);if(!["completed","cancelled"].includes(r.status))r.status="needs_sync";}
        for(const p of value.plans){if(!addresses.has(p.address)||!ids.has(p.template_id))throw Error("备份计划引用无效");P.int(p.interval_minutes,1,10080,"计划间隔");p.enabled=false;}
        return {format:"elink-web",schema:1,...Object.fromEntries(Object.keys(limits).map(k=>[k,value[k]]))};
    }
    function importBackup(value){const operation=mutations.then(()=>restoreBackup(value));mutations=operation.catch(()=>{});return operation;}
    async function restoreBackup(value){
        await ready;assertOwner();requireIdle();const next=await validateImport(copy(value));requireIdle();
        const t=db.transaction("workspace","readwrite");t.objectStore("workspace").put(copy(data),"before-import");t.objectStore("workspace").put(next,"current");await new Promise((resolve,reject)=>{t.oncomplete=resolve;t.onabort=t.onerror=()=>reject(t.error);});data=next;trim();await persist();
    }
    async function api(path,body){
        await ready;if(path==="/api/preview")return ELinkRenderer.render(body.spec);
        if(path==="/api/ota/validate"){const {raw,...meta}=await ELinkOTA.validate(body.package);return meta;}
        if(!body){if(!owner)data=await read()||empty();if(path==="/api/config")return {...configuration,token:"local",browser_only:true,has_previous_backup:!!await read("before-import")};if(path==="/api/state/summary")return summary();const m=path.match(/^\/api\/templates\/([0-9a-f]{32})$/);if(m)return copy(template(m[1]));throw Error("本地读取路径不支持");}
        const operation=mutations.then(async()=>{assertOwner();const result=await mutate(path,body);await persist();return result;});mutations=operation.catch(()=>{});return operation;
    }
    async function mutate(path,b){
        if(["/api/unregister","/api/jobs","/api/jobs/batch","/api/reminders","/api/reminders/retry","/api/plans"].includes(path))requireIdle();
        if(["/api/reminders/delete","/api/reminders/complete"].includes(path)){const r=reminder(b.id);if(r.status!=="pending"||r.previous_token||r.job_id)requireIdle();}
        if(path==="/api/register")return register(b.address,b.name);
        if(path==="/api/unregister"){
            device(b.address);if(data.jobs.some(j=>j.address===b.address&&active.includes(j.status)))throw Error("屏幕仍在执行任务");if(data.reminders.some(r=>r.address===b.address&&!["completed","cancelled"].includes(r.status)))throw Error("请先取消屏幕上的提醒并确认");for(const j of data.jobs)if(j.address===b.address&&unfinished.includes(j.status))j.status="cancelled";data.devices=data.devices.filter(d=>d.address!==b.address);data.plans=data.plans.filter(p=>p.address!==b.address);return {ok:true};
        }
        if(path==="/api/builtin"){
            const entry=configuration.gallery.find(e=>e.path===b.path);if(!entry)throw Error("内置图片不存在");const response=await fetch(entry.frame);if(!response.ok)throw Error("原生图读取失败");const frame=new Uint8Array(await response.arrayBuffer());if(frame.length!==8000||await P.sha256(frame)!==entry.sha256)throw Error("内置原生图校验失败");
            const existing=data.templates.find(t=>t.sha256===entry.sha256);if(existing){const spec=JSON.parse(existing.spec);if(spec.builtin){spec.builtin=entry.path;existing.spec=JSON.stringify(spec);}return {id:existing.id,title:existing.title};}
            if(data.templates.length>=100)throw Error("图片缓存已满，请先导出备份并删除旧图");const png=ELinkRenderer.png(frame),t={id:id(),title:entry.title,spec:JSON.stringify({kind:"image",image:png,crop:{mode:"stretch",zoom:1,x:0,y:0,rotation:0},builtin:entry.path}),png,frame:P.bytes64(frame),sha256:entry.sha256,created:now()};data.templates.push(t);return {id:t.id,title:t.title};
        }
        if(path==="/api/templates"){
            const title=String(b.title||"").trim();if(!title||title.length>80)throw Error("图片名称须为 1 至 80 字");const rendered=await ELinkRenderer.render(b.spec),t=b.id?template(b.id):{id:id(),created:now()};if(!b.id&&data.templates.length>=100)throw Error("图片缓存已满，请删除旧图");Object.assign(t,{title,spec:JSON.stringify(b.spec),...rendered});if(!b.id)data.templates.push(t);return {id:t.id};
        }
        if(path==="/api/templates/delete"){template(b.id);let stopped=0;for(const p of data.plans)if(p.template_id===b.id&&p.enabled){p.enabled=false;stopped++;}data.templates=data.templates.filter(t=>t.id!==b.id);return {ok:true,stopped_plans:stopped};}
        if(path==="/api/jobs"){
            return {id:(await queueRequest(b.address,b.action,b.payload)).id};
        }
        if(path==="/api/jobs/batch"){
            if(!Array.isArray(b.addresses)||!b.addresses.length||b.addresses.length>100||b.addresses.some(a=>typeof a!=="string"))throw Error("请选择 1..100 台屏幕");
            const results=[];for(const address of new Set(b.addresses)){try{results.push({address,id:(await queueRequest(address,b.action,b.payload)).id});}catch(e){results.push({address,error:e.message});}}return {results};
        }
        if(path==="/api/reminders/cancel-pending"){const r=reminder(b.id);if(r.status!=="pending"||r.previous_token||r.job_id)throw Error("只可立即取消尚未派发且不含旧设备记录的提醒");return finishReminder(b.id,true);}
        if(path==="/api/cancel"){const j=job(b.id);if(!["queued","waiting"].includes(j.status))throw Error("已开始的任务不能取消");j.status="cancelled";j.updated=now();return {ok:true};}
        if(path==="/api/reminders")return saveReminders(b);
        if(path==="/api/reminders/delete"||path==="/api/reminders/complete")return finishReminder(b.id,path.endsWith("delete"));
        if(path==="/api/reminders/retry"){const r=reminder(b.id),old=job(r.job_id);if(!["failed","cancelled","delivery_unknown"].includes(old.status))throw Error("日程尚未结束");const j=enqueue(r.address,"reminder",old.payload);r.job_id=j.id;r.status=old.payload.operation==="cancel"?"cancelling":"dispatched";return {id:j.id};}
        if(path==="/api/plans"){
            device(b.address);template(b.template_id);P.int(b.interval_minutes,1,10080,"计划间隔");const p={address:b.address,template_id:b.template_id,interval_minutes:b.interval_minutes,enabled:!!b.enabled,next_due:now()+b.interval_minutes*60};data.plans=data.plans.filter(p=>p.address!==b.address);data.plans.push(p);return {ok:true};
        }
        if(path==="/api/backup"){backup();return {ok:true};}
        throw Error("不支持此操作；此网页不访问服务器蓝牙，也不擦写固件");
    }
    function register(address,name){
        if(typeof address!=="string")throw Error("屏幕地址无效");if(!address.startsWith("web-"))address=address.toUpperCase();if(!addressPattern.test(address))throw Error("地址格式不正确");const old=data.devices.find(d=>d.address===address);if(old){if(name)old.name=String(name).slice(0,100);return {address,created:false};}
        if(data.devices.length>=100)throw Error("最多登记 100 台屏幕");data.devices.push({address,name:String(name||"ELINK-BWR-"+address.replaceAll(":","").slice(-6)).slice(0,100),settings:P.settings(),state:{},connection:"browser",last_seen:0,updated:now()});return {address,created:true};
    }
    async function saveReminders(b){
        const addresses=[...new Set(b.addresses||[])],title=String(b.title||"").trim(),body=String(b.body||"");if(!addresses.length||addresses.length>100||!title||title.length>80||body.length>240||!Number.isInteger(b.due)||b.due<=now()||b.due>2587680000)throw Error("提醒标题、时间或目标不合法");const config=P.options(b.options);
        let old;if(b.id){old=reminder(b.id);if(addresses.length!==1||addresses[0]!==old.address||!["pending","armed","needs_sync","displayed"].includes(old.status)||(old.job_id&&active.includes(job(old.job_id).status)))throw Error("请先等待日程任务完成");}
        for(const address of addresses){device(address);if(data.reminders.filter(r=>r.address===address&&r.id!==b.id&&!["completed","cancelled"].includes(r.status)).length>=7)throw Error("每台屏幕最多 7 项日程");}
        const ids=[];for(const address of addresses){const token=randomToken();if(old?.job_id){const j=job(old.job_id);if(["queued","waiting"].includes(j.status))j.status="cancelled";}
            const r=old||{id:id(),address,created:now()};Object.assign(r,{title,body,due:b.due,options:JSON.stringify(config),status:"pending",previous_token:old?.status!=="pending"?old?.token||0:old?.previous_token||0,token,job_id:"",delete_after:false,updated:now(),next_due:0,last_due:0});if(!old)data.reminders.push(r);ids.push(r.id);
        }return {ids};
    }
    function finishReminder(ident,remove){
        const r=reminder(ident),j=r.job_id?job(r.job_id):null;if(j&&active.includes(j.status))throw Error("日程正在写入，尚不能删除");if(j&&["queued","waiting"].includes(j.status))j.status="cancelled";
        if((r.status==="pending"&&!r.previous_token)||["completed","cancelled"].includes(r.status)){if(remove)data.reminders=data.reminders.filter(x=>x.id!==ident);else r.status="completed";return {ok:true};}
        const next=enqueue(r.address,"reminder",{reminder_id:r.id,operation:"cancel",token:r.token,previous_token:r.previous_token});r.job_id=next.id;r.status="cancelling";r.delete_after=remove;return {ok:true};
    }
    async function updateJob(j,changes){assertOwner();Object.assign(j,changes,{updated:now()});await persist();}
    async function updateState(address,state){assertOwner();const d=device(address);d.state=copy(state);d.updated=d.last_seen=now();await persist();}
    function albumMatches(album){const used=new Set();return album.crc32.map(crc=>{const id=data.templates.find(t=>!used.has(t.id)&&P.crc32(P.decode64(t.frame))===crc)?.id||null;if(id)used.add(id);return id;});}
    async function restoreAlbum(album,frames){
        const matches=albumMatches(album),items=[];
        for(let i=0;i<album.count;i++){
            let t=matches[i]?template(matches[i]):null;
            if(!t&&frames[i]){
                const frame=frames[i];if(frame.length!==8000||P.crc32(frame)!==album.crc32[i])throw Error("图库原图校验失败");if(data.templates.length>=100)throw Error("浏览器图片库已满，请导出备份并清理后读取图库");
                const digest=await P.sha256(frame),known=configuration.gallery.find(x=>x.sha256===digest),png=ELinkRenderer.png(frame);
                t={id:id(),title:known?.title||"屏幕图库 "+(i+1),spec:JSON.stringify({kind:"image",...(known?{builtin:known.path}:{}),native_frame:P.bytes64(frame),image:png}),frame:P.bytes64(frame),png,sha256:digest,created:now()};data.templates.push(t);
            }
            items.push({template_id:t?.id||null,title:t?.title||"屏幕第 "+(i+1)+" 张（需1.5.11读回原图）",photo_x:album.photo_x[i]});
        }
        await persist();return {...album,items,editable:items.every(x=>!!x.template_id)};
    }
    async function saveSettings(address,settings){device(address).settings=P.settings(settings);await persist();}
    async function reconcile(address,slots){
        for(const r of data.reminders.filter(r=>r.address===address&&!['completed','cancelling'].includes(r.status))){const s=slots.find(s=>s.token===r.token);if(!s)continue;r.next_due=s.next_due||0;r.last_due=s.last_due||0;r.status=s.state===248?"cancelled":!s.clock_ready?"needs_sync":s.state===252?"displayed":s.state===254?"armed":r.status;}await persist();
    }
    async function dispatch(){
        for(const r of data.reminders.filter(r=>r.status==="pending"&&!busy(r.address))){
            const source=copy(r),date=new Date(source.due*1000),footer=date.toLocaleString(),rendered=await ELinkRenderer.render({kind:"notice",title:source.title,body:source.body||source.title,footer,red:true});
            if(!data.reminders.includes(r)||r.status!=="pending"||r.token!==source.token||busy(r.address))continue;
            const j=enqueue(r.address,"reminder",{reminder_id:r.id,operation:"install",token:r.token,previous_token:r.previous_token,due:r.due,title:r.title,options:JSON.parse(r.options),...rendered});r.status="dispatched";r.job_id=j.id;await persist();
        }
        for(const p of data.plans.filter(p=>p.enabled&&p.next_due<=now())){if(!busy(p.address)){const last=[...data.jobs].reverse().find(j=>j.address===p.address&&j.action==="publish");if(last?.status==="delivery_unknown"||!data.templates.some(t=>t.id===p.template_id))p.enabled=false;else enqueue(p.address,"publish",{...snapshot(template(p.template_id)),scheduled:true});}p.next_due=now()+p.interval_minutes*60;await persist();}
    }
    async function tick(){
        await ready;if(!owner||workerRunning||fatal)return;workerRunning=true;
        try{
            await mutations;await dispatch();const j=data.jobs.filter(j=>["queued","waiting"].includes(j.status)&&j.due<=now()).sort((a,b)=>a.created-b.created).find(j=>typeof portable!=="undefined"&&portable.address===j.address&&portable.device?.gatt.connected);
            if(!j){for(const pending of data.jobs.filter(j=>j.status==="queued")){await updateJob(pending,{status:"waiting",phase:"等待此浏览器连接屏幕"});}return;}
            await updateJob(j,{status:"running",progress:2,error:null,phase:"读取设备状态与电压",attempts:j.attempts+1});
            try{const receipt=await ELinkBLE.execute(j);if(j.action==="reminder"){const r=data.reminders.find(r=>r.id===j.payload.reminder_id);if(r){if(j.payload.operation==="cancel"){if(r.delete_after)data.reminders=data.reminders.filter(x=>x.id!==r.id);else r.status="completed";}else{r.status=receipt.slot_state===252?"displayed":"armed";r.previous_token=0;r.next_due=receipt.next_due||0;r.last_due=receipt.last_due||0;}}}
                await updateJob(j,{status:"succeeded",progress:100,receipt,error:null,phase:"设备回执已核对"});
            }catch(e){const submitted=j.committed||e.submitted;await updateJob(j,{status:submitted?"delivery_unknown":e.connection?"waiting":"failed",due:now()+15,error:e.message,phase:submitted?"提交结果待核对，停止自动重发":"等待重连或检查参数"});}
        }catch(e){fatal="任务执行已停止："+e.message;console.error(fatal);}finally{workerRunning=false;}
    }
    function stopPlans(address){for(const p of data.plans)if(p.address===address)p.enabled=false;}
    window.addEventListener("pagehide",()=>releaseOwner?.());
    return {ready,api,resource,backup,previousBackup,importBackup,validateImport,assertOwner,tick,updateJob,updateState,saveSettings,reconcile,stopPlans,device,job,summary,persist,albumMatches,restoreAlbum};
})();
