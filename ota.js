"use strict";
const ELinkOTA=(()=>{
    const P=ELinkProtocol;
    async function validate(p){
        if(!p||p.board!=="da14585-5pad-bwr-250x122"||p.format!=="elink-update-1")throw Error("请选择此屏幕专用的 .elink-update.json 升级包");
        const raw=P.decode64(p.application),v=P.view(raw),state=0xe2d4;
        if(raw.length<state+32||raw.length>65472||v.getUint32(4,true)!==0x07fc0111||P.hex(raw.subarray(state,state+5))!=="454c4b3101")throw Error("升级包不是受支持的应用镜像，不能使用完整 SPI 镜像");
        if(await P.sha256(raw)!==p.sha256||P.hex(raw.subarray(state+28,state+32))!==p.firmware_id)throw Error("固件 SHA256 或版本标识不一致");
        const magic=[121,19,165,249,134,236,90,6];let pos=-1;for(let i=0;i<=raw.length-10;i++)if(magic.every((x,j)=>raw[i+j]===x)){pos=i;break;}if(pos<0)throw Error("缺少 HMCLOCK 版本标记");
        return {raw,version:p.version,firmware_id:p.firmware_id,sha256:p.sha256,bytes:raw.length,native_version:0xa50f0000+v.getUint16(pos+8,true)};
    }
    function image(meta){const size=Math.ceil((meta.raw.length+64)/256)*256,b=new Uint8Array(size),v=P.view(b);b.fill(255);v.setUint32(0,0x00aa5170,true);v.setUint32(4,meta.raw.length,true);v.setUint32(8,P.crc32(meta.raw),true);v.setUint32(28,meta.native_version,true);b[32]=0;b.set(meta.raw,64);return b;}
    return {validate,image};
})();
if(typeof module!=="undefined")module.exports=ELinkOTA;
