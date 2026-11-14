"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.join(__dirname,".."),source=fs.readFileSync(path.join(root,"app.js"),"utf8"),html=fs.readFileSync(path.join(root,"index.html"),"utf8"),config=JSON.parse(fs.readFileSync(path.join(root,"config.json"),"utf8"));
const line=name=>source.split(/\r?\n/).find(s=>s.startsWith("function "+name+"("));
function node(tag="div") {return {tag,children:[],dataset:{},hidden:false,value:"",textContent:"",classList:{toggle(){}},setAttribute(){},getAttribute(){},append(...items){this.children.push(...items);},querySelectorAll(selector){return selector==="[data-address]"?this.children.filter(c=>c.dataset.address):[];},scrollIntoView(){this.scrolled=true;}};}

test("upgrade notice compares the read firmware to the actual online OTA target",()=>{
    const ota=html.match(/id="ota-online"[^>]*data-package="([^"]+)"[^>]*data-version="([^"]+)"/);assert.ok(ota);
    const pack=JSON.parse(fs.readFileSync(path.join(root,ota[1]),"utf8"));assert.equal(ota[2],pack.version);assert.equal(config.firmware_versions[pack.firmware_id],pack.version);
    const c={$:()=>({dataset:{version:ota[2]}}),firmwareVersions:{...config.firmware_versions,future:"1.5.27"}};vm.createContext(c);vm.runInContext(line("firmwareUpgrade"),c);
    for(const id of ["feacec0e","9c096ccc","b826f754"])assert.match(c.firmwareUpgrade({protocol:1,firmware_id:id}),/旧固件.*1\.5\.26/);
    for(const s of [{protocol:1,firmware_id:pack.firmware_id},{protocol:1,firmware_id:"future"},{protocol:1,firmware_id:"unknown"},{protocol:1,firmware_id:"9c096ccc",capabilities_stale:true},{}])assert.equal(c.firmwareUpgrade(s),"");
});

test("settings select dark by default while preserving saved or read explicit choices",()=>{
    const elements=Object.fromEntries(["refresh-mode","full-every","refresh-minutes","clock-timezone","advertise-minutes","connection-mode","window-seconds"].map(id=>[id,node()]));elements["refresh-minutes"].options=[{value:"5"}];
    let device;const c={$:id=>elements[id],selected:()=>device,minuteWarning(){},connectionMode(){},showSaved(){},Math};vm.createContext(c);vm.runInContext(line("loadSettings"),c);
    for(const [settings,state,expected] of [[{},{},2],[{mode:0},{},2],[{mode:1},{mode:2},1],[{mode:2},{mode:1},2],[{},{mode:1},1],[{},{mode:2},2]]){
        device={settings,state};c.loadSettings();assert.equal(elements["refresh-mode"].value,expected);
    }
});

test("card upgrade link selects its device without queuing OTA and respects ongoing work",()=>{
    const elements={fleet:node(),device:node(),"fleet-count":node(),"ota-panel":node(),"ota-online":{dataset:{version:"1.5.26"}}},chosen=[];let busy=false;
    const c={$:id=>elements[id],firmwareVersions:config.firmware_versions,targets:new Set(),batching:false,state:{devices:[{address:"old",name:"Old",state:{protocol:1,firmware_id:"9c096ccc"},updated:1},{address:"current",name:"Current",state:{protocol:1,firmware_id:"31e9ff5f"},updated:1}],jobs:[]},document:{createElement:node},pageAction:()=>"default",pending:()=>false,modeLabel:()=>"默认界面",pageIssue:()=>"",pageControls(){},selectDevice:a=>chosen.push(a),operationBusy:()=>busy};
    vm.createContext(c);vm.runInContext(line("firmwareUpgrade")+"\n"+source.slice(source.indexOf("function fleet(){"),source.indexOf("function liveJobs(){")),c);c.fleet();
    const [old,current]=elements.fleet.children;assert.equal(old.view.upgrade.hidden,false);assert.match(old.view.upgrade.textContent,/旧固件.*1\.5\.26/);assert.equal(current.view.upgrade.hidden,true);
    let prevented=false;old.view.upgrade.onclick({preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.deepEqual(chosen,["old"]);assert.equal(elements["ota-panel"].scrolled,true);
    busy=true;old.view.upgrade.onclick({preventDefault(){}});assert.deepEqual(chosen,["old"]);assert.equal(c.state.jobs.length,0);
});
