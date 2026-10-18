const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),savedSettings=new Map();let replacements=0;
function element(){return {value:'',checked:false,children:[],attrs:{},setAttribute(k,v){this.attrs[k]=v;},append(...xs){this.children.push(...xs);this.firstElementChild=this.children[0];},replaceChildren(){this.children=[];replacements++;}};}
const context={$:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);},state:{templates:['a','b','c','d','e'].map(id=>({id,title:id})),devices:[]},targets:new Set(),batching:false,pending:()=>false,pageAction:()=> 'photo_calendar',document:{createElement:element,querySelectorAll:()=>[]},localStorage:{getItem:key=>savedSettings.get(key)||null,setItem:(key,value)=>savedSettings.set(key,value)}};
vm.createContext(context);vm.runInContext(fs.readFileSync('source/opendesign/mockups/elink-manager/gallery.js','utf8'),context);
context.$('album-save').checked=true;context.$('album-interval').value='1440';context.$('album-hours').value='24';
for(const id of ['a','b','c','d'])context.toggleAlbum(id);
assert.throws(()=>context.toggleAlbum('e'),/最多 4/);
let data=context.albumPayload();assert.equal(data.items.length,4);assert.equal(data.mode,'calendar');assert.equal(data.interval_minutes,1440);
assert.equal(data.items[0].photo_x,38);context.$('album-interval').value='0';context.$('album-hours').value='1.5';assert.throws(()=>context.albumPayload(),/整数/);
for(const v of ['0','169','','NaN']){context.$('album-hours').value=v;assert.throws(()=>context.albumPayload());}
context.$('album-hours').value='168';assert.equal(context.albumPayload().interval_minutes,10080);
context.renderAlbum();const count=replacements,button=context.$('album-items').children[0].firstElementChild;
context.renderAlbum();assert.equal(replacements,count,'Polling must not destroy focused buttons');
context.$('publish-template').value='a';context.renderAlbum();assert.equal(replacements,count);assert.equal(button.attrs['aria-pressed'],'true');
context.toggleAlbum('b');assert.deepEqual(JSON.parse(JSON.stringify(context.albumPayload().items.map(x=>x.template_id))),['a','c','d']);
const calendar=context.albumPayload();context.pageAction=()=> 'publish';const image=context.albumPayload();assert.equal(image.mode,'image');assert.deepEqual(JSON.parse(JSON.stringify(image.items)),JSON.parse(JSON.stringify(calendar.items)));assert.equal(image.interval_minutes,10080);
context.$('album-save').checked=false;context.$('album-interval').value='60';context.$('album-hours').value='1';const reload={...context};vm.createContext(reload);vm.runInContext(fs.readFileSync('source/opendesign/mockups/elink-manager/gallery.js','utf8'),reload);reload.initGallery([]);assert.deepEqual(JSON.parse(JSON.stringify(reload.albumPayload().items)),JSON.parse(JSON.stringify(image.items)));assert.equal(JSON.parse(savedSettings.get('elink-album-settings')).hours,'168');assert.equal(reload.albumPayload().interval_minutes,10080);assert.equal(context.$('album-save').checked,true);
console.log('PASS: album cap/order, image/calendar payload, integer-hour bounds and stable keyboard focus');
