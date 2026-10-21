"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const source=fs.readFileSync(path.join(__dirname,"../gallery.js"),"utf8"),context=vm.createContext({});
const crypto=require("node:crypto");
vm.runInContext(source.slice(source.indexOf("function deviceAlbumSlots("),source.indexOf("function albumPayload(")),context);
test("device slot inventory reflects the last committed playlist and keeps staging separate",()=>{
    const d={name:"Screen",state:{album_capacity:7,album:{count:2,crc32:[0x80000001,2],index:1,writing:true,staged_count:3,save_step:16}}};
    const rows=context.deviceAlbumSlots(d);assert.equal(rows.length,8);assert.match(rows[0],/播放槽 1 · 已保存 · CRC32 80000001$/);assert.match(rows[1],/00000002 · 当前槽位$/);
    assert.match(rows[2],/未加入已保存列表$/);assert.match(rows[7],/尚未提交.*已校验 3 张.*16\/32.*原播放列表保留/);
    d.state.album.writing=false;assert.equal(context.deviceAlbumSlots(d).length,7);assert.equal(context.deviceAlbumSlots({state:{}}).length,0);
    delete d.state.album.crc32;assert.match(context.deviceAlbumSlots(d)[0],/CRC32 待读取$/);
    d.address="test";Object.assign(d.state,{display_mode:2,display_generation:7,transfer_id:42,firmware_id:"f1ef98a7"});d.state.album.index=0;
    context.state={jobs:[{address:"test",action:"album_show",status:"succeeded",receipt:{album_slot:1,generation_after:7,transfer_id:42,firmware_id:"f1ef98a7"}}]};
    assert.equal(context.displayedAlbumSlot(d),1);assert.match(context.deviceAlbumSlots(d,context.displayedAlbumSlot(d))[1],/当前槽位$/);
    d.state.display_generation++;assert.equal(context.displayedAlbumSlot(d),-1);
});
test("every gallery entry has a unique native frame, valid hash and matching preview provenance",()=>{
    const root=path.join(__dirname,".."),config=JSON.parse(fs.readFileSync(path.join(root,"config.json"))),artwork=JSON.parse(fs.readFileSync(path.join(root,"ARTWORK.json"))),html=fs.readFileSync(path.join(root,"index.html"),"utf8"),titles=new Set(),paths=new Set(),hashes=new Set();
    assert.ok(html.includes("内置图库 · "+config.gallery.length+" 张"));
    assert.equal(config.gallery.length,35);assert.deepEqual(config.retired_gallery.map(i=>i.path),["image/03-sleeping-cat.png","image/07-mountain-train.png","image/13-space-rabbit.png","image/16-fox-garden.png","image/17-mountain-summit.png","image/24-rivers-and-mountains.png","image/20-plum-in-snow.png","image/27-scholar-sword.png"]);
    for(const item of config.gallery){assert.equal(titles.has(item.title),false);titles.add(item.title);}
    assert.equal(config.gallery.find(i=>i.path==="image/26-summit-overlook.png").title,"绝顶凌云");
    for(const item of [...config.gallery,...config.retired_gallery]){
        assert.match(item.path,/^image\/\d{2}-[a-z0-9-]+\.png$/);assert.equal(item.frame,item.path.replace(/\.png$/,".bin"));assert.equal(paths.has(item.path),false);
        const frame=fs.readFileSync(path.join(root,item.frame)),digest=crypto.createHash("sha256").update(frame).digest("hex");assert.equal(frame.length,8000);assert.equal(digest,item.sha256);assert.equal(item.crc32,require("../protocol.js").crc32(frame));assert.equal(hashes.has(digest),false);
        for(let col=0;col<250;col++){assert.equal(frame[col*16+15]&63,63);assert.equal(frame[4000+col*16+15]&63,0);}
        titles.add(item.title);paths.add(item.path);hashes.add(digest);
    }
    for(const item of artwork.imports||[]){const registered=[...config.gallery,...config.retired_gallery].find(g=>g.path===item.file);assert.ok(registered);assert.equal(registered.title,item.title);assert.equal(registered.sha256,item.native_frame_sha256);assert.equal(crypto.createHash("sha256").update(fs.readFileSync(path.join(root,item.file))).digest("hex"),item.png_sha256);}
});
