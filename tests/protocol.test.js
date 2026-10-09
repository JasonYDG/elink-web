"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const P=require("../protocol.js"),fixtures=JSON.parse(fs.readFileSync(path.join(__dirname,"fixtures.json")));
test("native pixels and voltages match existing Python backend",()=>{
    for(const item of fixtures.battery)assert.deepEqual(P.battery(Uint8Array.of(item.mv&255,item.mv>>8)),item.expected);
    for(const item of fixtures.gallery){const rgba=Uint8Array.from(Buffer.from(item.rgba,"base64")),frame=Uint8Array.from(Buffer.from(item.frame,"base64"));assert.deepEqual(P.quantize(rgba).frame,frame,item.name);assert.deepEqual(P.quantize(P.pixels(frame)).frame,frame,item.name);}
});
test("lunar counters and Netherlands DST agree with existing firmware table",()=>{
    for(const item of fixtures.lunar)assert.deepEqual(P.lunar(...item.date),item.expected,item.date.join("-"));
    for(const item of fixtures.sync)assert.equal(P.hex(P.sync(item.zone,new Date(item.time))),item.hex);
    assert.equal(P.wall("Europe/Amsterdam",new Date("2026-03-29T00:59:00Z")).summer,false);
    assert.equal(P.wall("Europe/Amsterdam",new Date("2026-03-29T01:00:00Z")).summer,true);
    assert.equal(P.wall("Europe/Amsterdam",new Date("2026-10-25T01:30:00Z")).summer,false);
});
test("validation rejects malformed protocol and out-of-range settings",()=>{
    assert.throws(()=>P.battery(Uint8Array.of(1)));assert.throws(()=>P.status(new Uint8Array(32)));assert.throws(()=>P.slot(new Uint8Array(24)));assert.throws(()=>P.capabilities(Uint8Array.from([69,76,85,73,1,255,2,0])));
    assert.throws(()=>P.settings({full_every:500}));assert.throws(()=>P.settings({mode:1.5}));assert.throws(()=>P.options({repeat_mask:128}));assert.throws(()=>P.options({check_minutes:2}));assert.throws(()=>P.packet(0x96,[[2,0]],new Uint8Array(18)));
    assert.equal(P.settings().mode,1);assert.equal(P.settings().full_every,60);assert.equal(P.settings().window_seconds,0);assert.equal(P.crc32(new TextEncoder().encode("123456789")),0xcbf43926);
});
