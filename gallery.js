"use strict";
let albumSettings={};try{albumSettings=JSON.parse(localStorage.getItem("elink-album-settings")||"{}");if(!albumSettings||typeof albumSettings!=="object")albumSettings={};}catch(_){}
const albumSelection=Array.isArray(albumSettings.items)?[...new Set(albumSettings.items.filter(x=>typeof x==="string"))].slice(0,7):[];let albumListKey="";
const albumPageOpened=Math.floor(Date.now()/1000);let restoredAlbumKey="",albumDraftSlot=0;
function saveAlbumSettings(){try{localStorage.setItem("elink-album-settings",JSON.stringify({items:albumSelection,enabled:$("album-save").checked,interval:$("album-interval").value,hours:$("album-hours").value}));}catch(_){}}
function albumEnabled(){return $("album-save").checked&&["publish","photo_calendar"].includes(pageAction());}
let galleryPending=0,galleryQueue=Promise.resolve(),previewImage=null,previewDate=null,previewKey="",previewLoad=0,dragPhoto=null;
let photoPositions={};try{photoPositions=JSON.parse(localStorage.getItem("elink-photo-positions")||"{}");if(!photoPositions||typeof photoPositions!=="object"||Array.isArray(photoPositions))photoPositions={};}catch(_){photoPositions={};}
async function builtinTemplate(path){const old=state.templates.find(t=>JSON.parse(t.spec).builtin===path);return old?old.id:(await api("/api/builtin",{path})).id;}
function calendarArtwork(id=$("publish-template").value){const t=state.templates.find(t=>t.id===id);return !!t&&JSON.parse(t.spec).builtin_layout==="calendar";}
function chooseGallery(kind){document.querySelector('[name="page"][value="'+(kind==="calendar"?"calendar":"publish")+'"]').checked=true;if(kind==="calendar")$("calendar-theme").value="photo_calendar";pageControls();}
function initGallery(items){
    $("album-save").checked=false;
    $("album-auto").checked=false;$("album-interval").value="1440";$("album-hours").value="24";
    $("album-custom").hidden=$("album-interval").value!=="0";
    for(const host of document.querySelectorAll('[data-native-gallery]')){
        host.replaceChildren();
        for(const item of items.filter(i=>(i.layout||"fullscreen")===(host.dataset?.nativeGallery||"fullscreen"))){
            const button=document.createElement("button"),image=document.createElement("img"),title=document.createElement("span");
            button.type="button";button.className="image-choice";button.dataset.path=item.path;button.setAttribute("aria-pressed","false");button.setAttribute("aria-label","选择 "+item.title);
            image.src=resource(item.path);image.alt="";image.loading="lazy";title.textContent=item.title;button.append(image,title);
            button.onclick=()=>{galleryPending++;pageControls();return perform(button,()=>{const next=galleryQueue.then(async()=>{if(operationBusy())throw Error("请等待屏幕操作完成");const id=await builtinTemplate(item.path);await refresh();$("publish-template").value=id;showSaved();pageControls();});galleryQueue=next.catch(()=>{});return next.finally(()=>{galleryPending--;pageControls();});});};
            host.append(button);
        }
    }
    $("gallery-fullscreen").onclick=()=>chooseGallery("fullscreen");$("gallery-calendar").onclick=()=>chooseGallery("calendar");
    $("album-save").onchange=()=>{saveAlbumSettings();pageControls();};
    $("album-auto").onchange=pageControls;
    $("album-add").onclick=()=>perform($("album-add"),async()=>{const id=$("publish-template").value;if(!id)throw Error("请先选择图片");if(!albumSelection.includes(id))toggleAlbum(id);pageControls();});
    $("album-replace").onclick=()=>perform($("album-replace"),replaceAlbumImage);
    $("album-commit").onclick=()=>perform($("album-commit"),saveDeviceAlbum);
    $("album-rotation").onclick=()=>perform($("album-rotation"),async()=>{const d=singleDevice(),a=d.state?.album;if(!a?.count||a.writing)throw Error("请先读取设备图库");await queue("album_rotation",{sequence:a.sequence,auto_rotate:$("album-auto").checked,interval_minutes:albumMinutes()});});
    $("album-interval").onchange=()=>{$("album-custom").hidden=$("album-interval").value!=="0";saveAlbumSettings();};
    $("album-hours").oninput=saveAlbumSettings;
    $("album-stop").onclick=()=>perform($("album-stop"),()=>batch("album_stop"));
    $("photo-x").oninput=()=>positionPhoto(Number($("photo-x").value));
    for(const [id,x] of [["photo-left",0],["photo-center",38],["photo-right",76]])$(id).onclick=()=>positionPhoto(x);
    const canvas=$("photo-canvas");
    canvas.onpointerdown=e=>{if(!previewImage||calendarArtwork()||operationBusy()||e.offsetX/canvas.clientWidth>174/250)return;dragPhoto={id:e.pointerId,x:e.clientX,start:Number($("photo-x").value)};canvas.setPointerCapture(e.pointerId);};
    canvas.onpointermove=e=>{if(!dragPhoto||e.pointerId!==dragPhoto.id)return;positionPhoto(Math.round(dragPhoto.start-(e.clientX-dragPhoto.x)*250/canvas.getBoundingClientRect().width));};
    canvas.onpointerup=canvas.onpointercancel=()=>{dragPhoto=null;};
}
function positionPhoto(x){
    x=calendarArtwork()?0:Math.max(0,Math.min(76,x));$("photo-x").value=x;const id=$("publish-template").value;
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
    const photo=pageAction()==="photo_calendar",kind=photo?"calendar":"fullscreen",current=state.templates.find(t=>t.id===$("publish-template").value),layout=current&&JSON.parse(current.spec).builtin_layout;
    if(layout&&layout!==kind)$("publish-template").value="";
    for(const option of $("publish-template").options){const t=state.templates.find(t=>t.id===option.value),usage=t&&JSON.parse(t.spec).builtin_layout;option.hidden=option.disabled=!!usage&&usage!==kind;}
    for(const host of document.querySelectorAll('[data-native-gallery]'))host.hidden=(host.dataset?.nativeGallery||"fullscreen")!==kind;
    $("gallery-fullscreen").setAttribute("aria-pressed",String(!photo));$("gallery-calendar").setAttribute("aria-pressed",String(photo));
    $("photo-position").hidden=!photo||calendarArtwork();$("image-section-title").textContent=photo?"选择日历专用图":"选择全屏图";
    $("image-preview-note").textContent=photo?(calendarArtwork()?"日历图 174 × 122 · 原生 1:1 对齐，完整显示，无需拖动；日期由设备更新":"请选择下方日历专用图，完整显示无需裁切；旧图和自定义照片仍可调整取景") :"全屏图 250 × 122 · 点击显示后才发送到屏幕";
    renderSelection();renderAlbum();
}
function renderSelection(){
    const id=$("publish-template").value,photo=pageAction()==="photo_calendar",row=state.templates.find(t=>t.id===id),builtin=row?JSON.parse(row.spec).builtin:"";
    for(const card of document.querySelectorAll('[data-native-gallery] button'))card.setAttribute("aria-pressed",String(card.dataset.path===builtin));
    $("saved-preview").hidden=!id||photo;$("photo-canvas").hidden=!id||!photo;$("preview-empty").hidden=!!id;$("photo-x").disabled=!id||calendarArtwork(id);
    if(calendarArtwork(id))$("photo-x").value=0;
    if(!id){previewKey="";previewLoad++;previewImage=null;previewDate=null;return;}
    const zone=selected()?.settings?.clock_timezone||selected()?.state?.clock_timezone||"local",day=new Intl.DateTimeFormat("en-CA",{timeZone:zone==="local"?undefined:zone,year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date()),key=[id,row?.sha256,zone,day].join("|");
    if(key===previewKey){paintPhoto();return;}previewKey=key;previewImage=null;previewDate=null;paintPhoto();
    const position=photoPositions[id];$("photo-x").value=calendarArtwork(id)?0:Number.isInteger(position)&&position>=0?Math.min(position,76):38;
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
    $("album-options").hidden=!albumEnabled();$("album-count").textContent="浏览器草稿 · "+albumSelection.length+" / "+albumLimit()+" 张";
    $("album-commit").textContent="保存整组图库（"+albumSelection.length+" 张）";
    $("album-commit").disabled=batching||galleryPending>0||!albumSelection.length||targets.size!==1||!!pageIssue(selected()||{},"album");
    $("album-replace").disabled=!albumSelection.length||!$("publish-template").value;
    $("album-interval").disabled=$("album-hours").disabled=!$("album-auto").checked;
    const list=$("album-items"),key=JSON.stringify(albumSelection.map(id=>[id,state.templates.find(t=>t.id===id)?.title]));
    if(key!==albumListKey){albumListKey=key;list.replaceChildren();
    for(const [i,id] of albumSelection.entries()){
        const t=state.templates.find(t=>t.id===id),li=document.createElement("li"),focus=document.createElement("button"),remove=document.createElement("button");
        focus.type=remove.type="button";focus.textContent=(i+1)+". "+t.title;focus.setAttribute("aria-pressed",String(albumDraftSlot===i));focus.onclick=()=>{albumDraftSlot=i;$("publish-template").value=id;showSaved();pageControls();};
        remove.textContent="移除";remove.setAttribute("aria-label","从图库移除 "+t.title);remove.onclick=()=>{toggleAlbum(id);pageControls();};li.append(focus,remove);list.append(li);
    }
    }
    albumDraftSlot=Math.min(albumDraftSlot,Math.max(0,albumSelection.length-1));
    for(const [i,li] of [...list.children].entries())li.firstElementChild.setAttribute("aria-pressed",String(albumDraftSlot===i));
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
    $("album-rotation").disabled=batching||targets.size!==1||!selected()?.state?.album?.count||!!selected()?.state?.album?.writing||!!selected()?.state?.capabilities_stale;
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
function albumMinutes(){
    const hours=Number($("album-hours").value);
    if($("album-interval").value==="0"&&!Number.isInteger(hours))throw Error("请输入 1–168 的整数小时");
    const minutes=Number($("album-interval").value)||hours*60;
    if(!Number.isInteger(minutes)||minutes<60||minutes>10080)throw Error("换图间隔须为 1–168 个整小时");
    return minutes;
}
function albumPayload(){
    if(!albumSelection.length)throw Error("请选择图库图片");
    return {mode:pageAction()==="photo_calendar"?"calendar":"image",auto_rotate:$("album-auto").checked,interval_minutes:albumMinutes(),items:albumSelection.map(id=>({template_id:id,photo_x:calendarArtwork(id)?0:Math.min(photoPositions[id]??38,76)}))};
}
async function replaceAlbumImage(){
    const id=$("publish-template").value,index=albumDraftSlot,old=albumSelection[index];
    if(!id||!old)throw Error("请先选择草稿中要替换的位置，再选择新图片");
    if(id===old)return;if(albumSelection.includes(id))throw Error("此图已在草稿中，请选择其他图片");
    if(!await confirmAction("用当前预览替换草稿第 "+(index+1)+" 张“"+state.templates.find(t=>t.id===old)?.title+"”？这里只修改草稿；保存到设备前会另行确认整组写入数量。"))return;
    if(albumSelection[index]!==old||$("publish-template").value!==id)throw Error("选择已变化，请重新替换");
    albumSelection[index]=id;saveAlbumSettings();pageControls();
}
async function saveDeviceAlbum(){
    const d=singleDevice(),a=d.state?.album;if(!a||d.state.capabilities_stale||a.writing)throw Error("请先读取设备状态，再保存图库");
    const payload=albumPayload(),signature=JSON.stringify(payload),sequence=a.sequence;
    const same=a.count===payload.items.length&&payload.items.every((x,i)=>a.items?.[i]?.template_id===x.template_id&&a.items[i].sha256===state.templates.find(t=>t.id===x.template_id)?.sha256&&!!a.items[i].sha256&&a.photo_x[i]===x.photo_x);
    const count=same?0:payload.items.length;
    if(!await confirmAction(d.name+"："+(count?"将替换设备整组图库，写入 "+count+" 张（"+count*8000+" 字节）。现有固件修改一张也需保存整组。只想换当前画面，请取消后点“显示当前图片”。":"图片相同，复用设备图库，不上传图片。")+(payload.auto_rotate?" 保存后开启自动换图。":" 保存后关闭自动换图。")))return;
    if(singleDevice().address!==d.address||d.state.album.sequence!==sequence||JSON.stringify(albumPayload())!==signature)throw Error("设备或草稿已变化，请重新确认");
    await queue("album",{...payload,expected_sequence:sequence,max_image_writes:count});
}

function albumLimit(){const devices=state.devices.filter(d=>targets.has(d.address));return devices.length?Math.min(...devices.map(d=>d.state?.album_capacity||4)):7;}
function restoreDeviceAlbum(){
    if(targets.size!==1)return;const d=selected(),a=d?.state?.album;if(!d)return;
    const probe=state.jobs.filter(j=>j.address===d.address&&j.action==="probe"&&j.status==="succeeded").sort((a,b)=>b.updated-a.updated)[0];
    if(!a||!probe||probe.updated<albumPageOpened){$("album-readback-note").textContent="当前显示浏览器上次记录与草稿；请读取设备状态，核对实际卡槽和自动换图设置。";return;}
    const key=JSON.stringify([d.address,probe.id,a.sequence,a.items]);if(key===restoredAlbumKey)return;
    if(a.writing){$("album-readback-note").textContent="设备有未提交的上传；已保存播放列表保留，请核对后再修改。";return;}
    $("album-auto").checked=a.enabled;$("album-hours").value=String(a.interval_minutes/60||24);
    $("album-interval").value=String(a.interval_minutes||1440);if(!$("album-interval").value)$("album-interval").value="0";$("album-custom").hidden=$("album-interval").value!=="0";
    if(!a.count){restoredAlbumKey=key;albumSelection.splice(0);saveAlbumSettings();$("album-readback-note").textContent="设备当前没有已保存图库。";return;}
    if(!a.items||a.items.some(x=>!x.template_id||!state.templates.some(t=>t.id===x.template_id))){restoredAlbumKey=key;albumSelection.splice(0);saveAlbumSettings();$("album-readback-note").textContent="已从设备读取 "+a.count+" 个卡槽和自动换图设置；部分原图不在此浏览器，未沿用旧草稿。点击各槽“读取原图”可从设备读取并校验。调整自动换图无需下载原图。";return;}
    restoredAlbumKey=key;albumSelection.splice(0,albumSelection.length,...a.items.map(x=>x.template_id));
    for(const item of a.items)photoPositions[item.template_id]=Math.min(item.photo_x,76);
    albumDraftSlot=a.index<a.count?a.index:0;
    $("publish-template").value=a.items[albumDraftSlot].template_id;
    if([7,8].includes(d.state.display_mode)){document.querySelector('[name="page"][value="'+(a.mode?"calendar":"publish")+'"]').checked=true;if(a.mode)$("calendar-theme").value="photo_calendar";}
    $("album-readback-note").textContent="卡槽与自动换图设置已从设备读取；预览原图按设备 CRC32 匹配浏览器记录。需要核对设备原图，请点对应槽的“读取原图”。";
    try{localStorage.setItem("elink-photo-positions",JSON.stringify(photoPositions));}catch(_){}saveAlbumSettings();
}
