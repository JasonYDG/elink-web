const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
for(const file of ['web/app.js','opendesign/mockups/elink-manager/app.js']){
    const code=fs.readFileSync(path.join(__dirname,'..',file),'utf8').split('\n').find(l=>l.startsWith('function modeLabel('));
    const context={};vm.runInNewContext(code,context);
    assert.equal(context.modeLabel({display_mode:0,time_initialized:false}),'画面待确认');
    assert.equal(context.modeLabel({display_mode:0,time_initialized:true,bold_clock:true}),'新版时钟');
    assert.equal(context.modeLabel({display_mode:4,time_initialized:false}),'默认界面');
    assert.equal(context.modeLabel({display_mode:7,time_initialized:false}),'离线图片图库');
    context.pending=()=>false;context.albumEnabled=()=>true;context.albumSelection=[];
    const pageIssue=fs.readFileSync(path.join(__dirname,'..',file),'utf8').split('\n').find(l=>l.startsWith('function pageIssue('));
    vm.runInNewContext(pageIssue,context);
    const device={address:'test',state:{protocol:1,offline_album:true,album_minute_tick:true}};
    assert.equal(context.pageIssue(device,'album'),'请读取状态，确认图库设置');
    device.state.album={protocol_version:1};assert.match(context.pageIssue(device,'album'),/升级/);
    device.state.album={protocol_version:3};assert.equal(context.pageIssue(device,'album'),'');
}
console.log('Native and web status labels passed');
