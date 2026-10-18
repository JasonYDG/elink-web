// Run the production queue, message and polling functions; no BLE requests.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const file=process.argv[2]||path.join(__dirname,'../opendesign/mockups/elink-manager/app.js');
const lines=fs.readFileSync(file,'utf8').split(/\r?\n/);
const code=['message','clearQueuedMessage','queue','refresh'].map(name=>lines.find(line=>line.startsWith('function '+name+'(')||line.startsWith('async function '+name+'('))).filter(Boolean).join('\n')+'\n'+lines.slice(lines.findIndex(line=>line.startsWith('async function batch(')),lines.findIndex(line=>line.startsWith('function confirmAction('))).join('\n');
const elements={message:{hidden:true},device:{value:'pilot'},health:{},'batch-result':{}};
let poll={devices:[],templates:[],jobs:[{id:'ours',status:'queued'}],worker_alive:true};
const context={deviceRequests:0,refreshSequence:0,operationEpoch:0,operationAwaiting:false,operationLocks:()=>{},state:poll,noticeJobIds:[],batchResults:[],labels:{queued:'排队中',running:'执行中',succeeded:'已完成',cancelled:'已取消'},unfinished:['queued','waiting','running','awaiting_display'],
    $:id=>elements[id],selected:()=>({state:{protocol:1}}),singleDevice:()=>({address:'pilot'}),actions:{probe:'读取状态'},
    api:async(route)=>route==='/api/state'?poll:{id:'ours'},selectOptions:()=>{},displayDevice:()=>{},loadSettings:()=>{},
    showSaved:()=>{},jobsTable:()=>{},liveJobs:()=>{},settingsProgress:()=>{},reminderChoices:()=>{},remindersList:()=>{},editLabel:()=>{},targets:new Set(['one','two','failed']),batching:false,pageControls:()=>{},pending:()=>false};
vm.createContext(context);vm.runInContext(code,context);
(async()=>{
    await context.queue('probe');assert.equal(elements.message.hidden,false);
    for(const status of context.unfinished){poll.jobs=[{id:'ours',status}];await context.refresh();assert.equal(elements.message.hidden,false);}
    poll.jobs=[{id:'ours',status:'succeeded'},{id:'unrelated',status:'running'}];await context.refresh();
    assert.equal(elements.message.hidden,true,'Finished queue notice must disappear without page reload, even if unrelated jobs remain');
    for(const status of ['failed','cancelled','delivery_unknown']){
        context.message('排队提示',false,['ours']);poll.jobs=[{id:'ours',status}];await context.refresh();assert.equal(elements.message.hidden,true);
    }
    context.message('批量提示',false,['one','two']);poll.jobs=[{id:'one',status:'succeeded'},{id:'two',status:'waiting'}];await context.refresh();
    assert.equal(elements.message.hidden,false,'A partial batch must retain its notice');
    poll.jobs[1].status='failed';await context.refresh();assert.equal(elements.message.hidden,true);
    poll.devices=[{address:'one'},{address:'two'},{address:'failed'}];poll.jobs=[{id:'one',status:'running'},{id:'two',status:'queued'}];
    context.state=poll;context.api=async(route,body)=>{if(route==='/api/state')return poll;return {results:body.addresses.map(address=>address==='failed'?{address,error:'提交失败'}:{address,id:address})};};
    await context.batch('probe');assert.deepEqual(Array.from(context.noticeJobIds),['one','two']);assert.match(elements.message.textContent,/已排队 2 台/);
    poll.jobs[0].status='succeeded';await context.refresh();assert.equal(elements.message.hidden,false);
    poll.jobs[1].status='cancelled';await context.refresh();assert.equal(elements.message.hidden,true);
    assert.match(elements['batch-result'].textContent,/one：已完成/);assert.match(elements['batch-result'].textContent,/two：已取消/);assert.match(elements['batch-result'].textContent,/提交失败/);assert.doesNotMatch(elements['batch-result'].textContent,/已排队/);
    context.message('排队提示',false,['ours']);context.message('新的错误需要保留',true);poll.jobs=[];await context.refresh();
    assert.equal(elements.message.hidden,false);assert.equal(elements.message.textContent,'新的错误需要保留');
    assert.equal(elements.message.className,'error','Old task completion must not clear a newer error');
    context.api=async(route)=>{if(route==='/api/state')return poll;throw Error('提交失败');};await context.batch('probe');assert.match(elements.message.textContent,/任务未提交/);assert.equal(elements.message.className,'error');
    console.log('PASS: production polling clears completed single/batch notices; waiting and newer errors retained');
})().catch(error=>{console.error(error);process.exitCode=1;});
