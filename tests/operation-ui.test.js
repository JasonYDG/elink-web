"use strict";
// Run the production admission/polling functions with controlled response order.
const test=require("node:test"),assert=require("node:assert/strict"),vm=require("node:vm"),fs=require("node:fs"),path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../app.js"),"utf8"),lines=source.split(/\r?\n/);
const empty=()=>({devices:[],templates:[],jobs:[],reminders:[],operation:{busy:false},worker_alive:true});
function harness(){
    const elements={},requests=[];for(const name of ["display-controls","scan","register","manual-address","portable-address","fleet","reminders","content","operation-note","live-tasks","restore-file","device","health"]){elements[name]={value:"",classList:{toggle(){}},setAttribute(){},querySelectorAll:()=>[]};}
    const c={state:empty(),batching:false,unfinished:["queued","waiting","running","awaiting_display"],deviceRequests:0,operationAwaiting:false,operationEpoch:0,refreshSequence:0,portable:{device:null},ELinkBLE:{working:()=>false},$:id=>elements[id],ensurePortable:async()=>{},ELinkLocal:{api:(path,body)=>new Promise(resolve=>requests.push({path,body,resolve}))},selected:()=>null,liveJobs(){},selectOptions(){},displayDevice(){},loadSettings(){},showSaved(){},savedImages(){},jobsTable(){},clearQueuedMessage(){},batchProgress(){},settingsProgress(){},reminderChoices(){},remindersList(){},editLabel(){},message(){}};
    vm.createContext(c);vm.runInContext(["operationBusy","connectionLocks","operationLocks","updateState"].map(name=>lines.find(line=>line.startsWith("function "+name+"(")||line.startsWith("async function "+name+"("))).join("\n")+"\n"+source.slice(source.indexOf("async function api("),source.indexOf("function selected()")),c);
    return {c,elements,requests};
}
const flush=()=>new Promise(setImmediate);

test("slow transport script loading leaves connection controls disabled without aborting startup",()=>{
    const {c,elements}=harness();delete c.portable;delete c.ELinkBLE;assert.doesNotThrow(()=>c.operationLocks());assert.equal(elements.scan.disabled,true);
});

test("unfinished work blocks all device controls and duplicate requests",async()=>{
    const {c,elements,requests}=harness();for(const status of c.unfinished){c.state={...empty(),jobs:[{status,progress:100}]};c.operationLocks();for(const name of ["display-controls","reminders","content"])assert.equal(elements[name].inert,true);await assert.rejects(c.api("/api/jobs",{address:"test",action:"probe"}),/尚未完成/);}
    assert.equal(requests.length,0);assert.equal(elements["restore-file"].disabled,true);assert.equal(elements.scan.disabled,true);
});

test("old or in-flight snapshots never unlock an accepted command before completion",async()=>{
    const {c,elements,requests}=harness(),stale=c.updateState();await flush();const staleReply=requests.shift();
    const post=c.api("/api/jobs",{address:"test",action:"probe"});await flush();const postReply=requests.shift();
    const during=c.updateState();await flush();requests.shift().resolve(empty());await during;postReply.resolve({id:"queued"});await post;staleReply.resolve(empty());await stale;
    assert.equal(c.operationBusy(),true);assert.equal(elements["display-controls"].inert,true);
    const busy=c.updateState();await flush();requests.shift().resolve({...empty(),jobs:[{status:"awaiting_display",progress:100}]});await busy;assert.equal(elements["display-controls"].inert,true);
    const done=c.updateState();await flush();requests.shift().resolve({...empty(),jobs:[{status:"succeeded",progress:100}]});await done;assert.equal(elements["display-controls"].inert,false);
    c.state={...empty(),operation:{busy:true,pending_reminders:1}};const cancel=c.api("/api/reminders/cancel-pending",{id:"waiting"});await flush();requests.shift().resolve({ok:true});await cancel;
});

test("idle screen cards allow switching, while waiting work only admits its target reconnect",()=>{
    const {c,elements}=harness(),cards=["A","B"].map(address=>({dataset:{address},view:Object.fromEntries(["connect","disconnect","check","inspect","remove"].map(k=>[k,{}]))}));elements.fleet.querySelectorAll=()=>cards;
    c.portable={address:"A",device:{gatt:{connected:true}}};c.operationLocks();
    assert.equal(elements.scan.disabled,false);assert.equal(cards[0].view.connect.hidden,true);assert.equal(cards[0].view.disconnect.disabled,false);assert.equal(cards[1].view.connect.disabled,false);
    c.portable.device.gatt.connected=false;c.state.jobs=[{address:"A",status:"waiting"}];c.operationLocks();assert.equal(elements.scan.disabled,true);assert.equal(cards[0].view.connect.disabled,false);assert.equal(cards[1].view.connect.disabled,true);
    c.state.jobs[0].status="running";c.operationLocks();assert.equal(cards[0].view.connect.disabled,true);assert.equal(cards[1].view.connect.disabled,true);
});

test("waiting progress can return to the screen cards, while running work reopens the protected dialog",()=>{
    const {c,elements}=harness();for(const name of ["operation-dialog","operation-title","operation-help","operation-close","operation-error","operation-elapsed"])elements[name]={addEventListener(){},showModal(){this.open=true;},close(){this.open=false;}};
    Object.assign(c,{Date,Set,actions:{probe:"读取状态"},clearTimeout(){},setTimeout(){},setInterval(){}});vm.runInContext(fs.readFileSync(path.join(__dirname,"../operation.js"),"utf8"),c);c.initOperationDialog();
    c.state.jobs=[{id:"job",address:"A",action:"probe",status:"waiting"}];c.updateOperationDialog(true);assert.equal(elements["operation-dialog"].open,true);assert.equal(elements["operation-close"].hidden,false);
    elements["operation-close"].onclick();c.updateOperationDialog(true);assert.equal(elements["operation-dialog"].open,false);
    c.state.jobs[0].status="running";c.updateOperationDialog(true);assert.equal(elements["operation-dialog"].open,true);assert.equal(elements["operation-close"].hidden,true);elements["operation-close"].onclick();assert.equal(elements["operation-dialog"].open,true);
    c.state.jobs[0].status="waiting";c.updateOperationDialog(true);elements["operation-close"].onclick();c.state.jobs[0].status="failed";c.state.jobs[0].error="connection failed";c.updateOperationDialog(false);assert.equal(elements["operation-dialog"].open,true);assert.equal(elements["operation-error"].hidden,false);
});
