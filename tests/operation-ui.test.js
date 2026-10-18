"use strict";
// Run the production admission/polling functions with controlled response order.
const test=require("node:test"),assert=require("node:assert/strict"),vm=require("node:vm"),fs=require("node:fs"),path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../app.js"),"utf8"),lines=source.split(/\r?\n/);
const empty=()=>({devices:[],templates:[],jobs:[],reminders:[],operation:{busy:false},worker_alive:true});
function harness(){
    const elements={},requests=[];for(const name of ["screens","reminders","content","operation-note","live-tasks","restore-file","portable-disconnect","portable-connect","device","health"]){elements[name]={value:"",classList:{toggle(){}},setAttribute(){}};}
    const c={state:empty(),unfinished:["queued","waiting","running","awaiting_display"],deviceRequests:0,operationAwaiting:false,operationEpoch:0,refreshSequence:0,portable:{device:null},ELinkBLE:{working:()=>false},$:id=>elements[id],ensurePortable:async()=>{},ELinkLocal:{api:(path,body)=>new Promise(resolve=>requests.push({path,body,resolve}))},selected:()=>null,liveJobs(){},selectOptions(){},displayDevice(){},loadSettings(){},showSaved(){},savedImages(){},jobsTable(){},clearQueuedMessage(){},batchProgress(){},settingsProgress(){},reminderChoices(){},remindersList(){},editLabel(){},message(){}};
    vm.createContext(c);vm.runInContext(["operationBusy","operationLocks","updateState"].map(name=>lines.find(line=>line.startsWith("function "+name+"(")||line.startsWith("async function "+name+"("))).join("\n")+"\n"+source.slice(source.indexOf("async function api("),source.indexOf("function selected()")),c);
    return {c,elements,requests};
}
const flush=()=>new Promise(setImmediate);

test("unfinished work blocks all device controls and duplicate requests",async()=>{
    const {c,elements,requests}=harness();for(const status of c.unfinished){c.state={...empty(),jobs:[{status,progress:100}]};c.operationLocks();for(const name of ["screens","reminders","content"])assert.equal(elements[name].inert,true);await assert.rejects(c.api("/api/jobs",{address:"test",action:"probe"}),/尚未完成/);}
    assert.equal(requests.length,0);assert.equal(elements["restore-file"].disabled,true);assert.equal(elements["portable-connect"].disabled,true);
});

test("old or in-flight snapshots never unlock an accepted command before completion",async()=>{
    const {c,elements,requests}=harness(),stale=c.updateState();await flush();const staleReply=requests.shift();
    const post=c.api("/api/jobs",{address:"test",action:"probe"});await flush();const postReply=requests.shift();
    const during=c.updateState();await flush();requests.shift().resolve(empty());await during;postReply.resolve({id:"queued"});await post;staleReply.resolve(empty());await stale;
    assert.equal(c.operationBusy(),true);assert.equal(elements.screens.inert,true);
    const busy=c.updateState();await flush();requests.shift().resolve({...empty(),jobs:[{status:"awaiting_display",progress:100}]});await busy;assert.equal(elements.screens.inert,true);
    const done=c.updateState();await flush();requests.shift().resolve({...empty(),jobs:[{status:"succeeded",progress:100}]});await done;assert.equal(elements.screens.inert,false);
    c.state={...empty(),operation:{busy:true,pending_reminders:1}};const cancel=c.api("/api/reminders/cancel-pending",{id:"waiting"});await flush();requests.shift().resolve({ok:true});await cancel;
});
