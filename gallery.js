"use strict";
let albumSettings={};try{albumSettings=JSON.parse(localStorage.getItem("elink-album-settings")||"{}");if(!albumSettings||typeof albumSettings!=="object")albumSettings={};}catch(_){}
const albumSelection=Array.isArray(albumSettings.items)?[...new Set(albumSettings.items.filter(x=>typeof x==="string"))].slice(0,7):[];let albumListKey="";
function saveAlbumSettings(){try{localStorage.setItem("elink-album-settings",JSON.stringify({items:albumSelection,enabled:$("album-save").checked,interval:$("album-interval").value,hours:$("album-hours").value}));}catch(_){}}
function albumEnabled(){return $("album-save").checked&&["publish","photo_calendar"].includes(pageAction());}
let galleryPending=0,galleryQueue=Promise.resolve(),previewImage=null,previewDate=null,previewKey="",previewLoad=0,dragPhoto=null;
let photoPositions={};try{photoPositions=JSON.parse(localStorage.getItem("elink-photo-positions")||"{}");if(!photoPositions||typeof photoPositions!=="object"||Array.isArray(photoPositions))photoPositions={};}catch(_){photoPositions={};}
async function builtinTemplate(path){const old=state.templates.find(t=>JSON.parse(t.spec).builtin===path);return old?old.id:(await api("/api/builtin",{path})).id;}
function initGallery(items){
    $("album-save").checked=albumSettings.enabled===true;
    $("album-auto").checked=false;$("album-interval").value="1440";$("album-hours").value="24";
    $("album-custom").hidden=$("album-interval").value!=="0";
    for(const host of document.querySelectorAll('[data-native-gallery]')){
        host.replaceChildren();
        for(const item of items){
            const button=document.createElement("button"),image=document.createElement("img"),title=document.createElement("span");
            button.type="button";button.className="image-choice";button.dataset.path=item.path;button.setAttribute("aria-pressed","false");button.setAttribute("aria-label","选择 "+item.title);
            image.src=resource(item.path);image.alt="";image.loading="lazy";title.textContent=item.title;button.append(image,title);
            button.onclick=()=>{galleryPending++;pageControls();return perform(button,()=>{const next=galleryQueue.then(async()=>{if(operationBusy())throw Error("请等待屏幕操作完成");const id=await builtinTemplate(item.path);await refresh();$("publish-template").value=id;if(albumEnabled())toggleAlbum(id);showSaved();pageControls();});galleryQueue=next.catch(()=>{});return next.finally(()=>{galleryPending--;pageControls();});});};
            host.append(button);
        }
    }
    $("album-save").onchange=()=>{if(albumEnabled()&&!albumSelection.length&&$("publish-template").value)toggleAlbum($("publish-template").value);saveAlbumSettings();pageControls();};
    $("album-auto").onchange=pageControls;
    $("album-add").onclick=()=>perform($("album-add"),async()=>{const id=$("publish-template").value;if(!id)throw Error("请先选择图片");if(!albumSelection.includes(id))toggleAlbum(id);pageControls();});
    $("album-interval").onchange=()=>{$("album-custom").hidden=$("album-interval").value!=="0";saveAlbumSettings();};
    $("album-hours").oninput=saveAlbumSettings;
    $("album-stop").onclick=()=>perform($("album-stop"),()=>batch("album_stop"));
    $("photo-x").oninput=()=>positionPhoto(Number($("photo-x").value));
    for(const [id,x] of [["photo-left",0],["photo-center",38],["photo-right",76]])$(id).onclick=()=>positionPhoto(x);
    const canvas=$("photo-canvas");
    canvas.onpointerdown=e=>{if(!previewImage||operationBusy()||e.offsetX/canvas.clientWidth>174/250)return;dragPhoto={id:e.pointerId,x:e.clientX,start:Number($("photo-x").value)};canvas.setPointerCapture(e.pointerId);};
    canvas.onpointermove=e=>{if(!dragPhoto||e.pointerId!==dragPhoto.id)return;positionPhoto(Math.round(dragPhoto.start-(e.clientX-dragPhoto.x)*250/canvas.getBoundingClientRect().width));};
    canvas.onpointerup=canvas.onpointercancel=()=>{dragPhoto=null;};
}
function positionPhoto(x){
    x=Math.max(0,Math.min(76,x));$("photo-x").value=x;const id=$("publish-template").value;
    if(id){photoPositions[id]=x;try{localStorage.setItem("elink-photo-positions",JSON.stringify(photoPositions));}catch(_){}}
    paintPhoto();
}
function paintPhoto(){
    const x=Number($("photo-x").value);$("photo-x-label").textContent=x===38?"居中":x<38?"靠左 "+(38-x)+" 像素":"靠右 "+(x-38)+" 像素";
    const canvas=$("photo-canvas"),ctx=canvas.getContext("2d");ctx.imageSmoothingEnabled=false;ctx.fillStyle="white";ctx.fillRect(0,0,250,122);
    if(previewImage)ctx.drawImage(previewImage,x,0,174,122,0,0,174,122);
    if(previewDate)ctx.drawImage(previewDate,174,0,76,122,174,0,76,122);
}
function imageControls(){
    const photo=pageAction()==="photo_calendar";$("photo-position").hidden=!photo;$("image-section-title").textContent=photo?"选择日历图片":"选择图片";
    $("image-preview-note").textContent=photo?"日期预览采用当前查看屏幕的时区；屏幕独立跨天更新。新版宽图日历与离线轮播需1.5.9固件。":"250 × 122 · 点击应用后才发送到屏幕";
    renderSelection();renderAlbum();
}
function renderSelection(){
    const id=$("publish-template").value,photo=pageAction()==="photo_calendar",row=state.templates.find(t=>t.id===id),builtin=row?JSON.parse(row.spec).builtin:"";
    for(const card of document.querySelectorAll('[data-native-gallery] button'))card.setAttribute("aria-pressed",String(albumEnabled()?albumSelection.some(id=>{const t=state.templates.find(x=>x.id===id);return t&&JSON.parse(t.spec).builtin===card.dataset.path;}):card.dataset.path===builtin));
    $("saved-preview").hidden=!id||photo;$("photo-canvas").hidden=!id||!photo;$("preview-empty").hidden=!!id;$("photo-x").disabled=!id;
    if(!id){previewKey="";previewLoad++;previewImage=null;previewDate=null;return;}
    const zone=selected()?.settings?.clock_timezone||selected()?.state?.clock_timezone||"local",day=new Intl.DateTimeFormat("en-CA",{timeZone:zone==="local"?undefined:zone,year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date()),key=[id,row?.sha256,zone,day].join("|");
    if(key===previewKey){paintPhoto();return;}previewKey=key;previewImage=null;previewDate=null;paintPhoto();
    const position=photoPositions[id];$("photo-x").value=Number.isInteger(position)&&position>=0?Math.min(position,76):38;
    const seq=++previewLoad,src=resource("/api/templates/"+encodeURIComponent(id)+"/preview.png"),im=new Image(),date=new Image();
    $("saved-preview").src=src;
    im.onload=()=>{if(seq!==previewLoad)return;previewImage=im;paintPhoto();};date.onload=()=>{if(seq!==previewLoad)return;previewDate=date;paintPhoto();};
    im.onerror=date.onerror=()=>{if(seq===previewLoad){previewKey="";message("预览加载失败，请重新选择图片",true);}};
    im.src=src;ELinkRenderer.dateColumn(zone).then(frame=>{if(seq===previewLoad)date.src="data:image/png;base64,"+ELinkRenderer.png(frame);}).catch(e=>message(e.message,true));
}

function toggleAlbum(id){
    const at=albumSelection.indexOf(id);
    if(at>=0)albumSelection.splice(at,1);
    else {if(albumSelection.length>=albumLimit())throw Error("已达到此固件的图库上限，请先移除一张；7张需1.5.11");albumSelection.push(id);}
    saveAlbumSettings();
}
function renderAlbum(){
    for(let i=albumSelection.length-1;i>=0;i--)if(!state.templates.some(t=>t.id===albumSelection[i]))albumSelection.splice(i,1);
    $("album-options").hidden=!albumEnabled();$("album-count").textContent="已选 "+albumSelection.length+" / "+albumLimit()+" 张";
    $("album-interval").disabled=$("album-hours").disabled=!$("album-auto").checked;
    const list=$("album-items"),key=JSON.stringify(albumSelection.map(id=>[id,state.templates.find(t=>t.id===id)?.title]));
    if(key!==albumListKey){albumListKey=key;list.replaceChildren();
    for(const [i,id] of albumSelection.entries()){
        const t=state.templates.find(t=>t.id===id),li=document.createElement("li"),focus=document.createElement("button"),remove=document.createElement("button");
        focus.type=remove.type="button";focus.textContent=(i+1)+". "+t.title;focus.setAttribute("aria-pressed",String($("publish-template").value===id));focus.onclick=()=>{$("publish-template").value=id;showSaved();pageControls();};
        remove.textContent="移除";remove.setAttribute("aria-label","从图库移除 "+t.title);remove.onclick=()=>{toggleAlbum(id);pageControls();};li.append(focus,remove);list.append(li);
    }
    }
    for(const [i,li] of [...list.children].entries())li.firstElementChild.setAttribute("aria-pressed",String($("publish-template").value===albumSelection[i]));
    const devices=state.devices.filter(d=>targets.has(d.address));
    $("album-device-status").textContent=devices.map(d=>{const a=d.state?.album,index=displayedAlbumSlot(d);return d.name+"："+(!d.state?.offline_album?"需升级 1.5.9 并读取状态":!a?"读取状态可查看设备图库":a.protocol_version<2||!d.state?.album_minute_tick?"离线轮播需升级 1.5.9":!a.count?"尚未保存图片":a.count+" 张 · "+(a.enabled?(!a.running&&!a.writing?"已暂停，需核对":a.count===1?"保存显示":"每 "+a.interval_minutes/60+" 小时轮播"):"自动换图关闭")+(index>=0&&index<a.count?" · 当前第 "+(index+1)+" 张":""));}).join("；");
    const slots=$("album-device-slot-list");slots.replaceChildren();
    for(const d of devices){
        const a=d.state?.album;
        for(const [i,text] of deviceAlbumSlots(d,displayedAlbumSlot(d)).entries()){
            const li=document.createElement("li"),label=document.createElement("span");label.textContent=text;li.append(label);
            if(i<a.count){
                const actions=document.createElement("div");actions.className="actions";
                for(const [action,title] of [["album_show","显示此图"],["album_read","读取原图"]]){
                    const button=document.createElement("button");button.type="button";button.textContent=title;button.setAttribute("aria-label",title+" · "+d.name+" · 卡槽 "+(i+1));button.disabled=batching||pending(d.address)||a.writing||!!d.state.capabilities_stale;
                    button.onclick=()=>perform(button,async()=>{const result=await api("/api/jobs",{address:d.address,action,payload:{index:i,sequence:a.sequence,crc32:a.crc32[i]}});message(action==="album_show"?"已排队显示此卡槽；自动轮播会停止，其余卡槽保留。":"已排队读取此卡槽原图，完成后可在已保存图片中选择。",false,[result.id]);await refresh();});actions.append(button);
                }
                li.append(actions);
            }
            slots.append(li);
        }
    }
    $("album-device-slots").hidden=!slots.children.length;
    $("album-stop").disabled=batching||!devices.some(d=>d.state?.offline_album&&!pending(d.address));
}
function deviceAlbumSlots(d,current=d.state?.album?.index){
    const a=d.state?.album;if(!a)return [];
    const rows=Array.from({length:Math.min(d.state.album_capacity||4,7)},(_,i)=>d.name+" · 播放槽 "+(i+1)+" · "+(i<a.count?"已保存 · "+(a.items?.[i]?.title?a.items[i].title+" · ":"")+"CRC32 "+(Number.isInteger(a.crc32?.[i])?(a.crc32[i]>>>0).toString(16).padStart(8,"0"):"待读取")+(current===i?" · 当前槽位":""):"未加入已保存列表"));
    if(a.writing)rows.push(d.name+" · 新图库尚未提交 · 已校验 "+a.staged_count+" 张 · 当前图片 "+a.save_step+"/32 块；原播放列表保留");
    return rows;
}
function displayedAlbumSlot(d){
    const s=d.state||{};if([7,8].includes(s.display_mode))return s.album?.index??-1;
    const last=state.jobs.find(j=>j.address===d.address&&j.action==="album_show"&&j.status==="succeeded"&&j.receipt?.firmware_id===s.firmware_id&&j.receipt.generation_after===s.display_generation&&j.receipt.transfer_id===s.transfer_id);
    return last?.receipt.album_slot??-1;
}
function albumPayload(){
    if(!albumSelection.length)throw Error("请选择图库图片");
    const hours=Number($("album-hours").value);
    if($("album-interval").value==="0"&&!Number.isInteger(hours))throw Error("请输入 1–168 的整数小时");
    const minutes=Number($("album-interval").value)||hours*60;
    if(!Number.isInteger(minutes)||minutes<60||minutes>10080)throw Error("换图间隔须为 1–168 个整小时");
    return {mode:pageAction()==="photo_calendar"?"calendar":"image",auto_rotate:$("album-auto").checked,interval_minutes:minutes,items:albumSelection.map(id=>({template_id:id,photo_x:Math.min(photoPositions[id]??38,76)}))};
}

function albumLimit(){const devices=state.devices.filter(d=>targets.has(d.address));return devices.length?Math.min(...devices.map(d=>d.state?.album_capacity||4)):7;}
let restoredAlbumKey="";try{restoredAlbumKey=localStorage.getItem("elink-restored-album-key")||"";}catch(_){}
function restoreDeviceAlbum(){
    if(targets.size!==1)return;const d=selected(),a=d?.state?.album;if(!d)return;
    const probe=state.jobs.filter(j=>j.address===d.address&&j.action==="probe"&&j.status==="succeeded").sort((a,b)=>b.updated-a.updated)[0];
    if(!a||!probe)return;const key=d.address+"|"+probe.id;if(key===restoredAlbumKey)return;
    if(a.writing){$("album-readback-note").textContent="设备有未提交的上传；已保存播放列表保留，请核对后再修改。";return;}
    if(!a.count){restoredAlbumKey=key;$("album-readback-note").textContent="设备当前没有已保存图库。";return;}
    if(!a.items||a.items.some(x=>!x.template_id||!state.templates.some(t=>t.id===x.template_id))){$("album-readback-note").textContent="已读取 "+a.count+" 个卡槽和换图设置，未下载各槽原图。可直接显示某槽，或点“读取原图”载入单张；未知自定义图名未保存在旧固件中。";return;}
    restoredAlbumKey=key;albumSelection.splice(0,albumSelection.length,...a.items.map(x=>x.template_id));
    for(const item of a.items)photoPositions[item.template_id]=Math.min(item.photo_x,76);
    $("album-save").checked=true;
    $("publish-template").value=a.items[Math.min(a.index,a.count-1)]?.template_id||a.items[0].template_id;
    if([7,8].includes(d.state.display_mode)){document.querySelector('[name="page"][value="'+(a.mode?"calendar":"publish")+'"]').checked=true;if(a.mode)$("calendar-theme").value="photo_calendar";}
    $("album-readback-note").textContent="已读取 "+a.count+" 个卡槽，图片名称和原图复用此浏览器记录。新保存默认关闭自动换图；设备当前设置见下方状态，点击应用才更改。";
    try{localStorage.setItem("elink-photo-positions",JSON.stringify(photoPositions));localStorage.setItem("elink-restored-album-key",key);}catch(_){}saveAlbumSettings();
}
