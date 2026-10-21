"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const P=require("../protocol.js");global.ELinkProtocol=P;const OTA=require("../ota.js");
const root=path.join(__dirname,".."),html=fs.readFileSync(path.join(root,"index.html"),"utf8"),source=fs.readFileSync(path.join(root,"app.js"),"utf8");
const packagePath=html.match(/id="ota-download" href="([^"]+)"/)[1],raw=fs.readFileSync(path.join(root,packagePath)),packageData=JSON.parse(raw);
function harness(fetcher=async()=>new Response(raw)){
    const elements=Object.fromEntries(["ota-file","ota-online","ota-install","ota-package","ota-download"].map(id=>[id,{id,disabled:false,textContent:""}]));
    elements["ota-file"].files=[];elements["ota-download"].href=new URL(packagePath,"https://example.test/elink-web/").href;
    const calls=[],requests=[],messages=[],c={$:id=>elements[id],fetch:async(...args)=>{requests.push(args);return fetcher(...args);},api:async(url,body)=>{calls.push(url);assert.equal(url,"/api/ota/validate");const {raw,...meta}=await OTA.validate(body.package);return meta;},message:(...args)=>messages.push(args),editLabel(){},operationLocks(){}};
    vm.createContext(c);c.displayDevice=()=>{elements["ota-install"].disabled=!vm.runInContext("otaPackage",c);};
    vm.runInContext('let otaPackage=null;\n'+source.split(/\r?\n/).find(line=>line.startsWith("async function perform("))+"\n"+source.slice(source.indexOf("async function loadOTAPackage("),source.indexOf('$("ota-install").onclick=')),c);
    return {c,elements,calls,requests,messages,selected:()=>vm.runInContext("otaPackage",c)};
}

test("published firmware is the exact 1.5.12 application and produces a valid OTA image",async()=>{
    const meta=await OTA.validate(packageData),image=OTA.image(meta);
    assert.equal(meta.version,"1.5.12");assert.equal(meta.firmware_id,"50d9e83d");assert.equal(meta.bytes,60028);
    assert.equal(meta.sha256,"274e3c5830292c142e3d3e14d0c1a304f36f68cbbdc910acbed13fa6bd35519d");
    assert.equal(await P.sha256(raw),"34f6a5493e051832647b1c34da04afaab71431a416605501f42f9097d770f3ea");
    assert.equal(P.view(image).getUint32(4,true),meta.bytes);assert.equal(P.view(image).getUint32(8,true),P.crc32(meta.raw));
    assert.deepEqual(image.subarray(64,64+meta.bytes),meta.raw);assert.ok(image.subarray(64+meta.bytes).every(b=>b===255));
});

test("online and local selection share validation, use the Pages subpath and never queue a device write",async()=>{
    const h=harness();await h.elements["ota-online"].onclick();
    assert.equal(h.requests[0][0],"https://example.test/elink-web/firmware/elink-bwr-1.5.12.elink-update.json");
    assert.equal(h.requests[0][1].cache,"no-store");assert.equal(h.selected().firmware_id,"50d9e83d");
    assert.match(h.elements["ota-package"].textContent,/版本 1.5.12.*60028 bytes/);assert.equal(h.elements["ota-install"].disabled,false);
    h.elements["ota-file"].files=[new Blob([raw])];await h.elements["ota-file"].onchange();
    assert.deepEqual(h.calls,["/api/ota/validate","/api/ota/validate"]);assert.equal(h.requests.length,1);
});

test("loading disables selection/install and any download or validation failure clears a previous package",async()=>{
    let release;const waiting=new Promise(resolve=>release=resolve),h=harness(()=>waiting);
    const load=h.elements["ota-online"].onclick();for(const id of ["ota-file","ota-online","ota-install"])assert.equal(h.elements[id].disabled,true);
    assert.equal(h.selected(),null);release(new Response(raw));await load;assert.ok(h.selected());
    for(const file of [new Blob(['{']),new Blob([JSON.stringify({...packageData,sha256:"0".repeat(64)})]),new Blob([new Uint8Array(200001)])]){
        h.elements["ota-file"].files=[file];await h.elements["ota-file"].onchange();assert.equal(h.selected(),null);assert.equal(h.elements["ota-install"].disabled,true);assert.match(h.elements["ota-package"].textContent,/未就绪/);
    }
    h.elements["ota-file"].files=[];await h.elements["ota-file"].onchange();assert.match(h.elements["ota-package"].textContent,/尚未选择/);
    for(const fetcher of [async()=>new Response("missing",{status:404}),async()=>{throw Error("network offline");}]){
        const fail=harness(fetcher);fail.elements["ota-file"].files=[new Blob([raw])];await fail.elements["ota-file"].onchange();assert.ok(fail.selected());
        await fail.elements["ota-online"].onclick();assert.equal(fail.selected(),null);assert.equal(fail.elements["ota-install"].disabled,true);
        assert.equal(fail.elements["ota-file"].disabled,false);assert.equal(fail.elements["ota-online"].disabled,false);assert.equal(fail.messages.at(-1)[1],true);
    }
});
