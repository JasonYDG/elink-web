"use strict";
const ELinkRenderer = (() => {
    const P=ELinkProtocol;
    let fontReady;
    function canvas(w=250,h=122){const c=document.createElement("canvas");c.width=w;c.height=h;return c;}
    function font(){if(!fontReady)fontReady=(async()=>{const f=new FontFace("ELinkNoto","url(fonts/NotoSansSC-Black.otf)");document.fonts.add(await f.load());})();return fontReady;}
    function mask(text,size){
        const cells=[];for(const ch of Array.from(String(text))){
            const c=canvas(size*4,size),ctx=c.getContext("2d");ctx.font=size+'px ELinkNoto';const advance=Math.round(ctx.measureText(ch).width),pad=size;
            ctx.fillStyle="white";ctx.fillRect(0,0,c.width,size);ctx.fillStyle="black";ctx.fillText(ch,pad,Math.round(size*.88));
            const data=ctx.getImageData(0,0,c.width,size).data;let left=pad,right=pad+advance;
            for(let y=0;y<size;y++)for(let x=0;x<c.width;x++)if(data[(y*c.width+x)*4]<128){left=Math.min(left,x);right=Math.max(right,x+1);}
            const width=right-left,bits=new Uint8Array(width*size);for(let y=0;y<size;y++)for(let x=0;x<width;x++)bits[y*width+x]=Number(data[(y*c.width+x+left)*4]<128);cells.push({width,bits});
        }
        const width=cells.reduce((n,c)=>n+c.width,0),bits=new Uint8Array(width*size);let off=0;
        for(const c of cells){for(let y=0;y<size;y++)bits.set(c.bits.subarray(y*c.width,(y+1)*c.width),y*width+off);off+=c.width;}
        return {width,height:size,bits};
    }
    function paint(ctx,text,x,y,size,color="black",limit=24,right=244,bottom=122){
        let s=Array.from(String(text)).slice(0,limit).join(""),m=mask(s,size);
        for(const next of [32,28,24,20,18,16,14,12])if(next<size&&(m.width>right-x||y+m.height>bottom)){size=next;m=mask(s,size);}
        while(s&&m.width>right-x){s=Array.from(s).slice(0,-1).join("");m=mask(s+"…",size);}if(!s)return;
        let left=m.width,top=m.height;for(let yy=0;yy<m.height;yy++)for(let xx=0;xx<m.width;xx++)if(m.bits[yy*m.width+xx]){left=Math.min(left,xx);top=Math.min(top,yy);}
        ctx.fillStyle=color==="#be0000"&&size<18?"black":color;
        for(let yy=top;yy<m.height;yy++)for(let xx=left;xx<m.width;xx++)if(m.bits[yy*m.width+xx])ctx.fillRect(x+xx-left,y+yy-top,1,1);
    }
    function statusIcon(ctx,percent){
        ctx.fillStyle="black";const rows=[48,56,60,567,1843,1023,252,120,252,1023,1843,567,60,56,48];
        rows.forEach((row,y)=>{for(let x=0;x<11;x++)if(row&(1<<(10-x)))ctx.fillRect(176+x,8+y,1,1);});
        ctx.fillRect(194,10,17,11);ctx.fillStyle="white";ctx.fillRect(196,12,13,7);ctx.fillStyle="black";ctx.fillRect(211,13,2,5);
        if(Number.isFinite(percent))ctx.fillRect(197,13,Math.round(percent*11/100),5);
        paint(ctx,Number.isFinite(percent)?percent+"%":"--%",218,8,12,"black",5,250,22);
    }
    function png(frame){const c=canvas();c.getContext("2d").putImageData(new ImageData(P.pixels(frame),250,122),0,0);return c.toDataURL("image/png").split(",")[1];}
    async function result(c){const r=P.quantize(c.getContext("2d").getImageData(0,0,250,122).data);return {png:png(r.frame),frame:P.bytes64(r.frame),sha256:await P.sha256(r.frame),red_pixels:r.red_pixels};}
    function image(encoded){return new Promise((resolve,reject)=>{if(typeof encoded!=="string"||encoded.length>2666668)throw Error("图片过大（限 2MB）");const im=new Image();im.onload=()=>{if(im.naturalWidth*im.naturalHeight>12000000)reject(Error("图片超过 1200 万像素"));else resolve(im);};im.onerror=()=>reject(Error("图片无法解码，请使用 PNG、JPEG、WebP 或 BMP"));im.src="data:image/png;base64,"+encoded;});}
    async function render(spec,percent=null){
        if(!spec||typeof spec!=="object")throw Error("模板必须是对象");const c=canvas(),ctx=c.getContext("2d");ctx.fillStyle="white";ctx.fillRect(0,0,250,122);
        if(spec.kind==="image"){
            const im=await image(spec.image),crop=spec.crop||{mode:"stretch",rotation:0,zoom:1,x:0,y:0},rotation=crop.rotation??0,zoom=crop.zoom??1,x=crop.x??0,y=crop.y??0;
            if(!["cover","contain","stretch"].includes(crop.mode)||![0,90,180,270].includes(rotation)||![zoom,x,y].every(Number.isFinite)||zoom<1||zoom>4||Math.abs(x)>1||Math.abs(y)>1)throw Error("裁切参数不合法");
            const rotated=canvas(rotation%180?im.height:im.width,rotation%180?im.width:im.height),rc=rotated.getContext("2d");rc.translate(rotated.width/2,rotated.height/2);rc.rotate(rotation*Math.PI/180);rc.drawImage(im,-im.width/2,-im.height/2);
            if(crop.mode==="stretch")ctx.drawImage(rotated,0,0,250,122);else{const scale=(crop.mode==="cover"?Math.max:Math.min)(250/rotated.width,122/rotated.height)*zoom,w=rotated.width*scale,h=rotated.height*scale;ctx.drawImage(rotated,(250-w)/2+x*Math.max(0,(w-250)/2),(122-h)/2+y*Math.max(0,(h-122)/2),w,h);}
            return result(c);
        }
        await font();const now=new Date(),date=[now.getFullYear(),String(now.getMonth()+1).padStart(2,"0"),String(now.getDate()).padStart(2,"0")].join("-"),time=[now.getHours(),now.getMinutes()].map(n=>String(n).padStart(2,"0")).join(":"),fields={"{date}":date,"{time}":time,"{weekday}":"星期"+"日一二三四五六"[now.getDay()]};
        const value=key=>Object.entries(fields).reduce((s,[a,b])=>s.replaceAll(a,b),String(spec[key]??"")),red=spec.red===false?"black":"#be0000",kind=spec.kind||"notice";
        if(kind==="notice"){
            paint(ctx,value("title")||"电子标签",8,7,24,red,18,168,34);statusIcon(ctx,percent);ctx.fillStyle="black";ctx.fillRect(8,35,234,1);
            const lines=(value("body")||"欢迎使用").split(/\r?\n/).slice(0,2);lines.forEach((line,i)=>paint(ctx,line,8,45+i*26,lines.length>1?24:32,"black",18));paint(ctx,value("footer"),8,104,18,"black",26);
        }else if(kind==="meeting"){
            paint(ctx,value("title")||"会议室",6,3,16,"black",18);ctx.fillStyle=spec.occupied?red:"black";ctx.fillRect(6,29,239,38);paint(ctx,spec.occupied?"使用中":"可使用",14,33,24,"white");paint(ctx,value("body").split(/\r?\n/)[0],6,69,16,"black",26);paint(ctx,value("footer"),6,104,16,"black",26);
        }else if(kind==="calendar"){
            paint(ctx,value("title")||"今日安排",6,1,24,red,18);value("body").split(/\r?\n/).slice(0,3).forEach((line,i)=>paint(ctx,line,6,29+i*22,18,"black",22));paint(ctx,value("footer"),6,105,16,"black",26);
        }else if(kind==="clock"){
            const text=value("body");if(!/^\d{1,2}:\d{2}$/.test(text)||+text.split(":")[0]>23||+text.split(":")[1]>59)throw Error("时钟时间须为 HH:MM");paint(ctx,value("title")||"日期",6,0,17,"black",28);paint(ctx,text,8,19,64,"black",5);paint(ctx,value("footer"),6,99,16,"black",30);
        }else throw Error("未知模板类型");return result(c);
    }
    async function metadata(title,options,large=false){
        await font();const o=P.options(options),height=large?16:12,width=large?72:96,stride=large?9:12;let m=mask(title,height);
        if(large&&m.width>width){while(title&&mask(title+"…",height).width>width)title=Array.from(title).slice(0,-1).join("");m=mask(title+"…",height);}
        const b=new Uint8Array(156);b.set([large?166:165,o.repeat_mask,o.check_minutes,o.duration_minutes]);P.view(b).setInt32(4,o.utc_offset,true);
        for(let y=0;y<height;y++)for(let x=0;x<Math.min(width,m.width);x++)if(m.bits[y*m.width+x])b[8+y*stride+(x>>3)]|=128>>(x&7);P.view(b).setUint32(152,P.crc32(b.subarray(0,152)),true);return b;
    }
    async function noticeBattery(encoded,percent){await font();const c=canvas(),ctx=c.getContext("2d");ctx.drawImage(await image(encoded),0,0);ctx.fillStyle="white";ctx.fillRect(176,8,74,15);statusIcon(ctx,percent);return result(c);}
    return {render,png,metadata,noticeBattery,font};
})();
