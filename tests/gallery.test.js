"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const source=fs.readFileSync(path.join(__dirname,"../gallery.js"),"utf8"),context=vm.createContext({});
vm.runInContext(source.slice(source.indexOf("function deviceAlbumSlots("),source.indexOf("function albumPayload(")),context);
test("device slot inventory reflects the last committed playlist and keeps staging separate",()=>{
    const d={name:"Screen",state:{album_capacity:7,album:{count:2,crc32:[0x80000001,2],index:1,writing:true,staged_count:3,save_step:16}}};
    const rows=context.deviceAlbumSlots(d);assert.equal(rows.length,8);assert.match(rows[0],/播放槽 1 · 已保存 · CRC32 80000001$/);assert.match(rows[1],/00000002 · 当前槽位$/);
    assert.match(rows[2],/未加入已保存列表$/);assert.match(rows[7],/尚未提交.*已校验 3 张.*16\/32.*原播放列表保留/);
    d.state.album.writing=false;assert.equal(context.deviceAlbumSlots(d).length,7);assert.equal(context.deviceAlbumSlots({state:{}}).length,0);
    delete d.state.album.crc32;assert.match(context.deviceAlbumSlots(d)[0],/CRC32 待读取$/);
});
