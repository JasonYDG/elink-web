"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),crypto=require("node:crypto");
const P=require("../protocol.js"),root=path.join(__dirname,".."),source=fs.readFileSync(path.join(root,"render.js"),"utf8"),fixtures=require("./text-font-fixtures.json");

function harness(changeResponse){
    const requests=[],colors={black:[0,0,0,255],white:[255,255,255,255],"#be0000":[190,0,0,255]};
    function canvas(){
        const c={width:250,height:122};let pixels;
        const ctx={fillStyle:"black",fillRect(x,y,w,h){pixels??=new Uint8ClampedArray(c.width*c.height*4);const color=colors[this.fillStyle];assert.ok(color);for(let yy=Math.max(0,y);yy<Math.min(c.height,y+h);yy++)for(let xx=Math.max(0,x);xx<Math.min(c.width,x+w);xx++)pixels.set(color,(yy*c.width+xx)*4);},getImageData(){return {data:pixels};},putImageData(im){pixels=im.data.slice();},drawImage(im){pixels=im.data.slice();},fillText(){throw Error("Browser text must not be used");},measureText(){throw Error("Browser text must not be measured");}};
        c.getContext=()=>ctx;c.toDataURL=()=>"data:image/png;base64,"+Buffer.from(pixels).toString("base64");return c;
    }
    const context=vm.createContext({ELinkProtocol:P,Uint8Array,Uint8ClampedArray,DataView,ImageData:class{constructor(data){this.data=data;}},Image:class{set src(value){this.data=Uint8ClampedArray.from(Buffer.from(value.split(",")[1],"base64"));this.naturalWidth=this.width=250;this.naturalHeight=this.height=122;queueMicrotask(()=>this.onload());}},document:{createElement:canvas},fetch:async url=>{requests.push(url);const file=path.join(root,url.split("?")[0]),data=fs.readFileSync(file),response={ok:true,json:async()=>JSON.parse(data),arrayBuffer:async()=>Uint8Array.from(data).buffer};return changeResponse?.(url,response,requests)||response;}});
    return {renderer:vm.runInContext(source+"\nELinkRenderer;",context),requests};
}

test("frozen pixel glyphs match the host, including baseline, punctuation and rare CJK",async()=>{
    const {renderer}=harness();
    for(const item of fixtures.glyphs){const f=await renderer.font(item.size),g=f.glyphs.get(item.char.codePointAt(0));assert.ok(g,item.char);assert.equal(g.width,item.width);assert.equal(Buffer.from(f.bytes.subarray(g.offset,g.offset+g.stride*item.size)).toString("hex"),item.hex,item.size+" "+item.char);}
});

test("all dynamic templates render the exact host frame without a browser font API",async()=>{
    const {renderer}=harness();for(const item of fixtures.frames){const actual=await renderer.render(item.spec,item.percent),a=P.decode64(actual.frame),b=Uint8Array.from(Buffer.from(item.frame,"hex")),ap=P.pixels(a),bp=P.pixels(b),diff=[];for(let i=0;i<ap.length;i+=4)if(ap[i]!==bp[i]||ap[i+1]!==bp[i+1])diff.push([i/4%250,Math.floor(i/1000)]);assert.equal(Buffer.compare(a,b),0,item.spec.kind+" "+item.spec.title+"; differing pixels: "+JSON.stringify(diff.slice(0,16))+"; total: "+diff.length);assert.equal(actual.sha256,await P.sha256(a));}
});

test("legacy and large reminder metadata agree with the host, including truncation and CRC",async()=>{
    const {renderer}=harness();for(const item of fixtures.metadata)assert.equal(Buffer.from(await renderer.metadata(item.title,item.options,item.large)).toString("hex"),item.hex,item.title+" "+item.large);
});

test("photo-calendar glyphs match the device host for term days, leap dates and year changes",async()=>{
    const {renderer}=harness();for(const item of fixtures.date_columns){const [y,m,d]=item.date.split("-").map(Number),actual=await renderer.dateColumn("local",new Date(y,m-1,d,12));assert.equal(Buffer.compare(actual,Buffer.from(item.frame,"hex")),0,item.date);}
});

test("battery refresh changes only its reserved rectangle and uses the fixed 12px glyphs",async()=>{
    const {renderer}=harness(),item=fixtures.frames[0],before=await renderer.render(item.spec),after=await renderer.noticeBattery(before.png,51),direct=await renderer.render(item.spec,51);
    assert.equal(after.frame,direct.frame);const a=P.pixels(P.decode64(before.frame)),b=P.pixels(P.decode64(after.frame));for(let y=0;y<122;y++)for(let x=0;x<250;x++)if(x<176||y<8||y>=23){const offset=(y*250+x)*4;assert.deepEqual(a.subarray(offset,offset+4),b.subarray(offset,offset+4));}
    for(const percent of [null,100]){const pixels=P.pixels(P.decode64((await renderer.render(item.spec,percent)).frame)),ys=[];
        for(let y=8;y<23;y++)for(let x=218;x<250;x++)if(pixels[(y*250+x)*4]===0)ys.push(y);
        assert.deepEqual([Math.min(...ys),Math.max(...ys)],[10,20],"Label ink must share the battery body's top and bottom");}
});

test("fonts are cached across concurrent requests and failed loads can be retried",async()=>{
    const {renderer,requests}=harness();const [a,b]=await Promise.all([renderer.font(16),renderer.font(16)]);assert.equal(a,b);assert.equal(requests.filter(u=>u.includes("text-16.bin")).length,1);
    let failed=false;const retry=harness((url)=>{if(url.includes("text-12.bin")&&!failed){failed=true;return {ok:false};}});await assert.rejects(retry.renderer.font(12),/加载失败/);await retry.renderer.font(12);assert.equal(retry.requests.filter(u=>u.includes("text-12.bin")).length,2);
});

test("missing glyphs, unsupported sizes and corrupt files fail explicitly without font fallback",async()=>{
    const {renderer}=harness();await assert.rejects(renderer.metadata("\u{10ffff}",{}),/缺字/);await assert.rejects(renderer.font(13),/不支持字号/);
    const corrupt=harness(url=>url.includes("text-16.bin")?{ok:true,arrayBuffer:async()=>new ArrayBuffer(12)}:null);await assert.rejects(corrupt.renderer.font(16),/校验失败/);
    const malformed=harness((url,response)=>{if(url.includes("text-fonts.json"))return {...response,json:async()=>{const m=await response.json();m.sizes[16].bytes=12;m.sizes[16].sha256=crypto.createHash("sha256").update(Buffer.alloc(12)).digest("hex");return m;}};if(url.includes("text-16.bin"))return {ok:true,arrayBuffer:async()=>new ArrayBuffer(12)};});await assert.rejects(malformed.renderer.font(16),/格式无效/);
});

test("original image frames do not load or depend on text fonts",async()=>{
    const {renderer,requests}=harness(),frame=Uint8Array.from(Buffer.from(fixtures.frames[0].frame,"hex")),actual=await renderer.render({kind:"image",native_frame:P.bytes64(frame)});assert.equal(actual.frame,P.bytes64(frame));assert.equal(requests.length,0);
});
