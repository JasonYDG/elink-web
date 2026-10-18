const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const source=fs.readFileSync(path.join(__dirname,"../opendesign/mockups/elink-manager/operation.js"),"utf8");
const elements=Object.fromEntries(["operation-dialog","operation-title","operation-close","operation-error","operation-help","operation-elapsed","operation-note"].map(id=>[id,{hidden:false,open:false,textContent:"",addEventListener:(name,fn)=>elements[id][name]=fn,showModal(){this.open=true;},close(){this.open=false;}}]));
let busy=false,timerId=0,now=0,tick;const timers=new Map();const ctx={state:{jobs:[]},unfinished:["queued","running","awaiting_display","waiting"],labels:{failed:"失败",delivery_unknown:"待核对"},Date:{now:()=>now},$:id=>elements[id],operationBusy:()=>busy,setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),setInterval:fn=>tick=fn};
vm.createContext(ctx);vm.runInContext(source,ctx);ctx.initOperationDialog();const dialog=elements["operation-dialog"];
busy=true;ctx.updateOperationDialog(true);assert.equal(dialog.open,true);let cancelled=false;dialog.cancel({preventDefault(){cancelled=true;}});assert(cancelled);
ctx.state.jobs=[{id:"a",status:"awaiting_display",progress:100}];ctx.updateOperationDialog(true);assert(dialog.open);assert(elements["operation-close"].hidden);
busy=false;ctx.state.jobs[0].status="succeeded";ctx.updateOperationDialog(false);assert.equal(timers.size,1);
// A new operation cancels the pending close; it must still close after its own receipt.
busy=true;ctx.state.jobs.push({id:"b",status:"running"});ctx.updateOperationDialog(true);assert.equal(timers.size,0);
busy=false;ctx.state.jobs[1].status="delivery_unknown";ctx.state.jobs[1].error="连接中断";ctx.state.jobs[1].address="screen";ctx.updateOperationDialog(false);assert(dialog.open);assert.equal(elements["operation-close"].hidden,false);assert.match(elements["operation-error"].textContent,/连接中断/);assert.equal(timers.size,0);
elements["operation-close"].onclick();assert.equal(dialog.open,false);
// Historical failures must not poison the next successful operation.
busy=true;ctx.updateOperationDialog(true);ctx.state.jobs.push({id:"c",status:"succeeded"});busy=false;ctx.updateOperationDialog(false);assert.equal(timers.size,1);for(const fn of timers.values())fn();timers.clear();assert.equal(dialog.open,false);
// Request errors with no device job remain visible until acknowledged.
busy=true;ctx.updateOperationDialog(true);ctx.operationFailure("请求被拒绝");busy=false;ctx.updateOperationDialog(false);assert.equal(dialog.open,true);assert.match(elements["operation-error"].textContent,/请求被拒绝/);
const terminalElapsed=elements["operation-elapsed"].textContent;now+=60000;tick();ctx.updateOperationDialog(false);assert.equal(elements["operation-elapsed"].textContent,terminalElapsed);assert.match(terminalElapsed,/操作已结束/);
// A later successful operation starts a new result even when the old error was left open.
busy=true;ctx.state.jobs.push({id:"ota",status:"running"});ctx.updateOperationDialog(true);
assert.match(elements["operation-elapsed"].textContent,/0 秒/);
busy=false;ctx.state.jobs.at(-1).status="succeeded";ctx.updateOperationDialog(false);
assert.equal(elements["operation-title"].textContent,"操作已完成");assert.equal(timers.size,1);assert.equal(elements["operation-error"].hidden,true);
console.log("PASS: modal completion barrier, busy Escape guard, new-operation race, explicit failure and historical-error isolation");
