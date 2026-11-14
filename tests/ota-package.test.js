"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const P=require("../protocol.js");global.ELinkProtocol=P;const OTA=require("../ota.js");
const root=path.join(__dirname,".."),html=fs.readFileSync(path.join(root,"index.html"),"utf8"),source=fs.readFileSync(path.join(root,"app.js"),"utf8");
const packagePath=html.match(/id="ota-online"[^>]*data-package="([^"]+)"/)[1],raw=fs.readFileSync(path.join(root,packagePath)),packageData=JSON.parse(raw);
function harness(fetcher=async()=>new Response(raw)){
    const elements=Object.fromEntries(["ota-file","ota-online","ota-install","ota-package"].map(id=>[id,{id,disabled:false,textContent:""}]));
    elements["ota-file"].files=[];elements["ota-online"].dataset={package:packagePath};
    const calls=[],requests=[],messages=[],queued=[],confirmations=[],c={$:id=>elements[id],URL,location:{href:"https://example.test/elink-web/"},currentAddress:"AA:BB:CC:DD:EE:01",singleDevice:()=>({address:c.currentAddress,name:"Test screen"}),confirmAction:async(text,phrase)=>{confirmations.push({text,phrase});return false;},queue:async(action,payload)=>queued.push({action,payload}),fetch:async(...args)=>{requests.push(args);return fetcher(...args);},api:async(url,body)=>{calls.push(url);assert.equal(url,"/api/ota/validate");const {raw,...meta}=await OTA.validate(body.package);return meta;},message:(...args)=>messages.push(args),editLabel(){},operationLocks(){}};
    vm.createContext(c);c.displayDevice=()=>{elements["ota-install"].disabled=!vm.runInContext("otaPackage",c);};
    vm.runInContext('let otaPackage=null;\n'+source.split(/\r?\n/).find(line=>line.startsWith("async function perform("))+"\n"+source.slice(source.indexOf("async function loadOTAPackage("),source.indexOf('let cropImage=')),c);
    return {c,elements,calls,requests,messages,queued,confirmations,selected:()=>vm.runInContext("otaPackage",c)};
}

test("published firmware is the exact 1.5.17 application and produces a valid OTA image",async()=>{
    const meta=await OTA.validate(packageData),image=OTA.image(meta);
    assert.equal(meta.version,"1.5.17");assert.equal(meta.firmware_id,"03a79aaa");assert.equal(meta.bytes,60028);
    assert.equal(meta.sha256,"a51935648d73707f36ccda65f4662a96c450c6f5955bc14b6b42dfa2110710f6");
    assert.equal(await P.sha256(raw),"217ebc2e4a075ebeb5941f4fa91f3cdd63fd449302167677285048068a4300e4");
    assert.equal(P.view(image).getUint32(4,true),meta.bytes);assert.equal(P.view(image).getUint32(8,true),P.crc32(meta.raw));
    assert.deepEqual(image.subarray(64,64+meta.bytes),meta.raw);assert.ok(image.subarray(64+meta.bytes).every(b=>b===255));
});

test("online and local selection share validation, use the Pages subpath and never queue a device write",async()=>{
    assert.doesNotMatch(html,/id="ota-download"/);assert.doesNotMatch(html,/<a[^>]+href="firmware\//);
    const h=harness();await h.elements["ota-online"].onclick();
    assert.equal(h.requests[0][0],"https://example.test/elink-web/firmware/elink-bwr-1.5.17.elink-update.json");
    assert.equal(h.requests[0][1].cache,"no-store");assert.equal(h.selected().firmware_id,"03a79aaa");
    assert.match(h.elements["ota-package"].textContent,/版本 1.5.17.*60028 bytes/);assert.equal(h.elements["ota-install"].disabled,false);
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

test("OTA requires target/version confirmation and rejects a changed target or package",async()=>{
    const h=harness();await h.elements["ota-online"].onclick();await h.elements["ota-install"].onclick();
    assert.equal(h.confirmations[0].phrase,"UPDATE");assert.match(h.confirmations[0].text,/AA:BB:CC:DD:EE:01.*1\.5\.17/);assert.equal(h.queued.length,0);
    h.c.confirmAction=async()=>{h.c.currentAddress="AA:BB:CC:DD:EE:02";return true;};await h.elements["ota-install"].onclick();assert.equal(h.queued.length,0);assert.match(h.messages.at(-1)[0],/已变化/);
    h.c.confirmAction=async()=>{vm.runInContext("otaPackage=null",h.c);return true;};await h.elements["ota-install"].onclick();assert.equal(h.queued.length,0);
    await h.elements["ota-online"].onclick();h.c.confirmAction=async()=>true;await h.elements["ota-install"].onclick();
    assert.equal(h.queued.length,1);assert.equal(h.queued[0].action,"ota");assert.equal(h.queued[0].payload.package.firmware_id,"03a79aaa");
});
