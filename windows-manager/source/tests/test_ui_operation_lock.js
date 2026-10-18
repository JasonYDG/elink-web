// Execute production admission and polling logic, including out-of-order responses.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../opendesign/mockups/elink-manager/app.js'),'utf8');
const lines=source.split(/\r?\n/),names=['operationBusy','operationLocks','api','refresh'];
const elements={screens:{},reminders:{},content:{},'operation-note':{},'live-tasks':{},device:{value:''},health:{}};
for(const element of Object.values(elements)){element.classList={toggle:()=>{}};element.setAttribute=()=>{};}
const empty=()=>({devices:[],templates:[],jobs:[],reminders:[],operation:{busy:false},worker_alive:true});
let respond,requests=0;
const context={state:empty(),deviceRequests:0,operationAwaiting:false,operationEpoch:0,refreshSequence:0,unfinished:['queued','waiting','running','awaiting_display'],
    $:id=>elements[id],token:'test',fetch:async()=>{requests++;return new Promise(resolve=>respond=data=>resolve({ok:true,json:async()=>data}));},
    liveJobs:()=>{},updateOperationDialog:()=>{},operationFailure:()=>{},selected:()=>null,selectOptions:()=>{},displayDevice:()=>{},loadSettings:()=>{},showSaved:()=>{},jobsTable:()=>{},clearQueuedMessage:()=>{},batchProgress:()=>{},settingsProgress:()=>{},reminderChoices:()=>{},remindersList:()=>{},editLabel:()=>{},message:()=>{}};
vm.createContext(context);vm.runInContext(names.map(name=>lines.find(line=>line.startsWith('function '+name+'(')||line.startsWith('async function '+name+'('))).join('\n'),context);
(async()=>{
    for(const status of context.unfinished){context.state={...empty(),jobs:[{status,progress:100}]};context.operationLocks();assert.equal(elements.screens.inert,true);assert.equal(elements.reminders.inert,true);assert.equal(elements.content.inert,true);await assert.rejects(context.api('/api/jobs',{action:'probe'}),/尚未完成/);}
    assert.equal(requests,0,'Blocked operations must never reach the API');
    context.state=empty();const post=context.api('/api/jobs',{action:'probe'});assert.equal(elements.screens.inert,true);respond({id:'accepted'});await post;
    assert.equal(context.operationBusy(),true,'POST completion is not hardware completion');
    const poll=context.refresh();respond({...empty(),jobs:[{status:'awaiting_display',progress:100}]});await poll;assert.equal(elements.screens.inert,true);
    const done=context.refresh();respond({...empty(),jobs:[{status:'succeeded',progress:100}]});await done;assert.equal(elements.screens.inert,false);
    const inflight=context.api('/api/jobs',{action:'probe'}),finishInflight=respond;
    const during=context.refresh();respond(empty());await during;finishInflight({id:'inflight'});await inflight;
    assert.equal(context.operationBusy(),true,'Polling during an unfinished POST must not clear the completion barrier');
    const settle=context.refresh();respond(empty());await settle;
    // A state request started before a command must not unlock it when it arrives late.
    const stale=context.refresh(),replyStale=respond;
    const second=context.api('/api/jobs',{action:'probe'}),replyPost=respond;replyPost({id:'second'});await second;replyStale(empty());await stale;
    assert.equal(context.operationBusy(),true,'A stale idle snapshot must be discarded');
    const current=context.refresh();respond(empty());await current;assert.equal(elements.screens.inert,false);
    context.state={...empty(),operation:{busy:true,pending_reminders:1}};context.operationLocks();assert.equal(elements.screens.inert,true);
    // Cancellation and read-only polling remain usable while device controls are locked.
    const cancel=context.api('/api/cancel',{id:'waiting'});respond({ok:true});await cancel;
    console.log('PASS: global lock through completion, no duplicate request, stale-poll protection, pending reminders and safe cancellation');
})().catch(error=>{console.error(error);process.exitCode=1;});
