"use strict";
// FF01 commands and rotated BWR planes shared with the existing ELK1 firmware.
const ELinkProtocol = (() => {
    const service="0000ff00-0000-1000-8000-00805f9b34fb", control="0000ff01-0000-1000-8000-00805f9b34fb", volts="0000ff02-0000-1000-8000-00805f9b34fb";
    const bytes64=b=>btoa(String.fromCharCode(...b)), decode64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
    const hex=b=>Array.from(b,v=>v.toString(16).padStart(2,"0")).join("");
    const equal=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
    const view=b=>new DataView(b.buffer,b.byteOffset,b.byteLength);
    const starts=(b,s)=>s.split("").every((v,i)=>b[i]===v.charCodeAt(0));
    function int(value,min,max,label){if(!Number.isInteger(value)||value<min||value>max)throw Error(label+"不合法");return value;}
    function packet(command,fields=[],tail=new Uint8Array()){
        const b=new Uint8Array(1+fields.reduce((n,f)=>n+f[0],0)+tail.length),v=view(b);b[0]=command;let off=1;
        for(const [size,value,signed] of fields){if(size===1)b[off]=value;else if(size===2)v.setUint16(off,value,true);else if(signed)v.setInt32(off,value,true);else v.setUint32(off,value,true);off+=size;}
        b.set(tail,off);if(b.length>20)throw Error("蓝牙命令超过 20 字节");return b;
    }
    function status(b){
        if(b.length!==32||!starts(b,"ELK1")||b[4]!==1)throw Error("当前固件未返回 ELK1 状态；原版仅支持校时");const v=view(b);
        const firmware=hex(b.slice(28,32)),photo=["d78aa415","6c3279f4","14271ec2"].includes(firmware);
        return {protocol:1,photo_calendar:photo,photo_calendar_commit:["6c3279f4","14271ec2"].includes(firmware),photo_calendar_native_digits:firmware==="14271ec2",max_image_payload:photo?128:17,mode:b[5],full_every:b[6],display_mode:b[7],busy:!!b[8],error:b[9],received:v.getUint16(10,true),transfer_id:v.getUint16(12,true),sum16:v.getUint16(14,true),expected_sum16:v.getUint16(16,true),display_generation:v.getUint16(18,true),advertise_window_seconds:b[21],advertise_every_minutes:b[22],clock_refresh_minutes:b[24],time_initialized:!!(b[27]&1),clock_timezone:b[27]&2?"Europe/Amsterdam":"local",clock_summer_time:!!(b[27]&4),firmware_id:firmware};
    }
    function capabilities(b){
        if(b.length===32&&starts(b,"ELK1")&&b[4]===1)return {};
        if(b.length!==8||!starts(b,"ELUI")||b[4]!==1||(b[6]&224)||((b[6]&2)&&!(b[6]&1))||((b[6]&8)&&!(b[6]&4))||((b[6]&16)&&!(b[6]&8))||b[7])throw Error("显示能力返回无效");
        const names=["embedded_calendar","minute_region_refresh","bold_clock","global_clock_refresh","quiet_sync","default_page","timezone_clock","offline_reminders"];
        return {...Object.fromEntries(names.map((n,i)=>[n,!!(b[5]&(1<<i))])),reminder_summary:!!(b[6]&1),reminder_large_text:!!(b[6]&2),...(b[6]&4?{offline_album:true,photo_calendar:true,photo_calendar_commit:true,photo_calendar_native_digits:true,max_image_payload:128}:{}),...(b[6]&8?{photo_calendar_wide:true,album_minute_tick:true}:{}),...(b[6]&16?{album_capacity:7,album_readback:true}:{})};
    }
    function albumPreflight(b){if(b.length!==8||!starts(b,"ELAP")||b[4]<1||b[4]>120||b[5]!==120||b[6]||b[7])throw Error("设备未返回分段图库检查回执");return b[4];}
    function album(b){
        if(b.length===64&&starts(b,"ELA1")&&b[4]===3){
            const v=view(b),progress=v.getUint16(10,true),c=b.subarray(12),cv=view(c),count=c[14],flags=c[15],minutes=cv.getUint16(12,true),check=Uint8Array.from([...c.subarray(0,8),...c.subarray(12,51)]);
            if(b[5]>1||b[6]>1||b[8]>1||b[9]>7||![0,1,2,3,4,5,6,255].includes(b[7])||b[8]&&progress>32||!b[5]&&c.some(x=>x))throw Error("设备未返回有效图库状态");
            if(b[5]&&(!starts(c,"ELG2")||c[51]!==254||count>7||flags>7||minutes<60||minutes>10080||c.subarray(44,51).some(x=>x>84)||flags&4&&!count||crc32(check)!==cv.getUint32(8,true)))throw Error("图库配置校验失败");
            return {protocol_version:3,capacity:7,save_step:b[8]?progress:0,has_config:!!b[5],running:!!b[6],index:b[7],writing:!!b[8],staged_count:b[9],elapsed_minutes:b[8]?0:progress,sequence:cv.getUint32(4,true),count,mode:flags&1,interval_minutes:minutes,crc32:Array.from({length:count},(_,i)=>cv.getUint32(16+i*4,true)),photo_x:Array.from(c.subarray(44,44+count)),enabled:!!(flags&4)};
        }
        if(b.length!==52||!starts(b,"ELA1")||![1,2].includes(b[4])||b[5]>1||b[6]>1||b[8]>1||b[9]>4||![0,1,2,3,255].includes(b[7]))throw Error("设备未返回有效图库状态");
        const v=view(b),progress=v.getUint16(10,true),c=b.subarray(12),cv=view(c),count=c[14],minutes=cv.getUint16(12,true);
        if(b[4]===2&&b[8]&&progress>32)throw Error("图库写入进度无效");
        if(!b[5]&&c.some(x=>x))throw Error("空图库状态不一致");
        const check=Uint8Array.from([...c.subarray(0,8),...c.subarray(12,38)]);
        if(b[5]&&(!starts(c,"ELG1")||c[38]!==254||count>4||c[15]>1||c[36]>1||c[37]>1||minutes<60||minutes>10080||c.subarray(32,36).some(x=>x>84)||(c[37]&&!count)||crc32(check)!==cv.getUint32(8,true)))throw Error("图库配置校验失败");
        return {protocol_version:b[4],capacity:4,save_step:b[4]===2&&b[8]?progress:0,has_config:!!b[5],running:!!b[6],index:b[7],writing:!!b[8],staged_count:b[9],elapsed_minutes:b[4]===2&&b[8]?0:progress,sequence:cv.getUint32(4,true),count,mode:c[15],interval_minutes:minutes,crc32:Array.from({length:count},(_,i)=>cv.getUint32(16+i*4,true)),photo_x:Array.from(c.subarray(32,32+count)),enabled:!!c[37]};
    }
    function photoFrame(frame,x=38){
        int(x,0,76,"图片取景位置");if(frame.length!==8000)throw Error("图片必须为 8000 字节");
        const out=new Uint8Array(8000);out.fill(255,0,4000);
        for(const plane of [0,4000])for(let col=0;col<174;col++){const source=plane+(249-x-col)*16;out.set(frame.subarray(source,source+16),plane+(249-col)*16);}return out;
    }
    function battery(b){
        if(b.length!==2)throw Error("电压特征应为 2 字节");const mv=int(view(b).getUint16(0,true),1500,3600,"电压"),a=Math.floor((mv*128+224)/225);
        const percent=a>1705?100:a>1584?28+Math.floor((a-1584)*72/121):a>1360?4+Math.floor((a-1360)*24/224):a>1136?Math.floor((a-1136)*4/224):0;
        return {battery_mv:mv,battery_percent:percent,battery_source:"FF02_voltage_estimate"};
    }
    function slot(b){
        if(b.length!==24||!starts(b,"ERM1")||b[4]!==1||b[5]>=8||![255,254,252,248].includes(b[6])||(b[7]&14)||(b[7]>>4)>8||b[22]>=8||b[23]>1||view(b).getUint16(20,true)>8000)throw Error("提醒存储返回无效");const v=view(b);
        return {slot:b[5],state:b[6],writing:!!(b[7]&1),last_slot:(b[7]>>4)-1,token:v.getUint32(8,true),due:v.getUint32(12,true),crc32:v.getUint32(16,true),received:v.getUint16(20,true),active_slot:b[22],clock_ready:!!b[23]};
    }
    function runtime(b){
        if(b.length!==20||!starts(b,"ERM2")||b[4]>127||![1,5,15,60].includes(b[5])||b[6]>120||![165,166,255].includes(b[7]))throw Error("提醒运行策略返回无效");const v=view(b);
        return {repeat_mask:b[4],check_minutes:b[5],duration_minutes:b[6],metadata_ready:b[7]!==255,next_due:v.getUint32(8,true),last_due:v.getUint32(12,true),utc_offset:v.getInt32(16,true)};
    }
    function settings(changes={}){
        const defaults={mode:1,full_every:60,refresh_minutes:5,advertise_minutes:1,window_seconds:0,clock_timezone:"local"};
        if(!changes||typeof changes!=="object"||Object.keys(changes).some(k=>!Object.hasOwn(defaults,k)))throw Error("设置字段不合法");const c={...defaults,...changes};
        int(c.mode,0,2,"刷新模式");int(c.full_every,1,60,"全刷间隔");int(c.refresh_minutes,1,60,"刷新分钟");int(c.advertise_minutes,1,240,"广播间隔");int(c.window_seconds,0,120,"连接窗口");if(c.window_seconds&&c.window_seconds<10)throw Error("窗口至少 10 秒");if(!["local","Europe/Amsterdam"].includes(c.clock_timezone))throw Error("时区不合法");return c;
    }
    function options(value={}){
        const d={repeat_mask:0,check_minutes:1,duration_minutes:5,utc_offset:-new Date().getTimezoneOffset()*60};
        if(!value||typeof value!=="object"||Object.keys(value).some(k=>!Object.hasOwn(d,k)))throw Error("提醒策略不合法");const o={...d,...value};
        int(o.repeat_mask,0,127,"重复日期");int(o.duration_minutes,0,120,"持续时间");int(o.utc_offset,-50400,50400,"UTC 偏移");if(![1,5,15,60].includes(o.check_minutes))throw Error("提醒检查间隔不合法");return o;
    }
    const years=[0x7954,0x6aa0,0xad50,0x5b52,0x4b60,0xa6e6,0xa4e0,0xd260,0xea65,0xd530,0x5aa0,0x76a3,0x96d0,0x4afb,0x4ad0,0xa4d0,0xd0b6,0xd250,0xd520,0xdd45,0xb5a0,0x56d0,0x55b2,0x49b0,0xa577,0xa4b0,0xaa50,0xb255,0x6d20,0xada0,0x4b63,0x9370];
    function lunar(year,month,day){
        let n=Math.floor((Date.UTC(year,month-1,day)-Date.UTC(2020,0,25))/86400000);if(n<0)throw Error("农历支持 2020-01-25 至 2051 年");
        for(let y=0;y<years.length;y++)for(let m=0;m<12;m++){
            const days=29+!!(years[y]&(0x8000>>m));if(n<days)return [y,m,n+1];n-=days;
            if((years[y]&15)===m+1){const leap=29+!!(0x48010000&(1<<y));if(n<leap)return [y,m|128,n+1];n-=leap;}
        }throw Error("日期超出固件农历范围");
    }
    function wall(zone,now=new Date()){
        if(zone==="local")return {year:now.getFullYear(),month:now.getMonth()+1,day:now.getDate(),hour:now.getHours(),minute:now.getMinutes(),second:now.getSeconds(),weekday:now.getDay(),summer:false};
        if(zone!=="Europe/Amsterdam")throw Error("时区不合法");
        const p=Object.fromEntries(new Intl.DateTimeFormat("en-GB",{timeZone:zone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).formatToParts(now).map(p=>[p.type,p.value]));
        const t={year:+p.year,month:+p.month,day:+p.day,hour:+p.hour,minute:+p.minute,second:+p.second};t.weekday=new Date(Date.UTC(t.year,t.month-1,t.day)).getUTCDay();t.summer=Math.round((Date.UTC(t.year,t.month-1,t.day,t.hour,t.minute,t.second)-now.getTime())/3600000)===2;return t;
    }
    function sync(zone="local",now=new Date(),quiet=false){const t=wall(zone,now);int(t.year,2020,2051,"时钟年份");return Uint8Array.from([quiet?0x9e:0x91,t.year&255,t.year>>8,t.month-1,t.day,t.hour,t.minute,t.second,t.weekday,...lunar(t.year,t.month,t.day)]);}
    function timezone(zone,now=new Date()){return Uint8Array.of(0x9f,Number(zone==="Europe/Amsterdam"),Number(wall(zone,now).summer));}
    function crc32(b){let n=0xffffffff;for(const v of b){n^=v;for(let i=0;i<8;i++)n=(n>>>1)^((n&1)?0xedb88320:0);}return (n^0xffffffff)>>>0;}
    async function sha256(b){return hex(new Uint8Array(await crypto.subtle.digest("SHA-256",b)));}
    function quantize(rgba){
        if(rgba.length!==250*122*4)throw Error("图片须为 250 × 122");const b=new Uint8Array(8000);b.fill(255,0,4000);let red=0;
        for(let y=0;y<122;y++)for(let x=0;x<250;x++){const i=(y*250+x)*4,r=rgba[i],g=rgba[i+1],bl=rgba[i+2],isRed=r>100&&r>g*1.4&&r>bl*1.4,pos=(249-x)*16+(y>>3),mask=128>>(y&7);if(isRed||299*r+587*g+114*bl<155000)b[pos]&=~mask;if(isRed){b[pos+4000]|=mask;red++;}}
        return {frame:b,red_pixels:red};
    }
    function pixels(b){
        if(b.length!==8000)throw Error("原生画面须为 8000 字节");const a=new Uint8ClampedArray(250*122*4);
        for(let y=0;y<122;y++)for(let x=0;x<250;x++){const pos=(249-x)*16+(y>>3),mask=128>>(y&7),i=(y*250+x)*4,r=b[pos+4000]&mask,w=b[pos]&mask;a[i]=r?190:w?255:0;a[i+1]=a[i+2]=r?0:w?255:0;a[i+3]=255;}return a;
    }
    return {service,control,volts,bytes64,decode64,hex,equal,view,int,packet,status,capabilities,album,albumPreflight,photoFrame,battery,slot,runtime,settings,options,lunar,wall,sync,timezone,crc32,sha256,quantize,pixels};
})();
if(typeof module!=="undefined")module.exports=ELinkProtocol;
