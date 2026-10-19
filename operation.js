"use strict";
let operationRun=null,operationCloseTimer=null;
function operationFailure(text){if(operationRun)operationRun.error=text;}
function updateOperationElapsed(){if(operationRun)$("operation-elapsed").textContent="本次已用时 "+Math.floor(((operationRun.end??Date.now())-operationRun.start)/1000)+" 秒 · "+(operationRun.end===undefined?"正在处理，请查看当前阶段":"操作已结束");}
function updateOperationDialog(busy){
    const dialog=$("operation-dialog");
    if(busy){
        clearTimeout(operationCloseTimer);operationCloseTimer=null;
        if(!operationRun||operationRun.end!==undefined){operationRun={start:Date.now(),previous:new Set(state.jobs.map(j=>j.id)),ids:new Set(),error:""};$("operation-elapsed").textContent="本次已用时 0 秒 · 正在准备操作";}
        delete operationRun.end;
        for(const j of state.jobs)if(unfinished.includes(j.status)||!operationRun.previous.has(j.id))operationRun.ids.add(j.id);
        const active=state.jobs.filter(j=>unfinished.includes(j.status));$("operation-title").textContent=active.length===1?(actions[active[0].action]||"正在处理"):active.length>1?"正在处理 "+active.length+" 项任务":"正在处理";$("operation-help").hidden=true;$("operation-close").hidden=true;$("operation-error").hidden=true;
        $("operation-help").textContent="正在处理，请稍候。排队任务可取消。";
        if(!dialog.open)dialog.showModal();
        return;
    }
    if(!operationRun)return;
    $("operation-help").hidden=false;
    operationRun.end??=Date.now();updateOperationElapsed();
    for(const j of state.jobs)if(!operationRun.previous.has(j.id))operationRun.ids.add(j.id);
    const jobs=state.jobs.filter(j=>operationRun.ids.has(j.id)),failures=jobs.filter(j=>["failed","delivery_unknown"].includes(j.status));
    const error=operationRun.error||failures.map(j=>j.address+"："+(j.error||labels[j.status])).join("\n");
    if(error){
        clearTimeout(operationCloseTimer);operationCloseTimer=null;$("operation-title").textContent="操作需要核对";$("operation-error").textContent=error;$("operation-error").hidden=false;$("operation-close").hidden=false;$("operation-help").textContent="请核对失败原因和设备画面，再决定后续操作。";$("operation-note").textContent="本次结果待核对，关闭后可查看任务记录。";return;
    }
    const cancelled=jobs.length&&jobs.every(j=>j.status==="cancelled");$("operation-title").textContent=cancelled?"等待任务已取消":"操作已完成";$("operation-help").textContent=cancelled?"已停止尚未执行的任务。":jobs.length?"已收到设备完成回执。":"请求处理完成。";
    if(!operationCloseTimer)operationCloseTimer=setTimeout(()=>{operationCloseTimer=null;if(operationBusy())return;dialog.close();operationRun=null;},650);
}
function initOperationDialog(){
    const dialog=$("operation-dialog");dialog.addEventListener("cancel",e=>{if(operationBusy())e.preventDefault();else operationRun=null;});
    $("operation-close").onclick=()=>{if(!operationBusy()){dialog.close();operationRun=null;}};
    setInterval(updateOperationElapsed,1000);
}
