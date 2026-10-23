import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import vm from 'node:vm';
const require=createRequire(import.meta.url);
globalThis.ApixlyCreativeControlsV1=require('../web/creative-compiler.js');
const modulePath='../web/free_tools_v2.mjs';
const golden=JSON.parse(fs.readFileSync(new URL('./fixtures/free-tools-v2/golden.json',import.meta.url)));

class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.style={};this.attributes={};this.listeners={};this._text='';}
 set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(x=>x.textContent||'').join('');}
 set innerHTML(v){throw Error('Unsafe HTML');}
 append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
 setAttribute(n,v){this.attributes[n]=String(v);} getAttribute(n){return this.attributes[n];}
 addEventListener(n,fn){(this.listeners[n]??=[]).push(fn);}
 dispatch(n){for(const f of this.listeners[n]||[]) f({preventDefault(){},stopPropagation(){},currentTarget:this,target:this});}
}
const all=e=>[e,...e.children.flatMap(all)];
function setup(kind,values={}){
 globalThis.document={createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t)};
 globalThis.fetch=()=>{throw Error('A free panel must not request the network.');};
 const node={id:1,comfyClass:kind,size:[310,100],inputs:[],widgets:Object.entries(values).map(([name,value])=>({name,value})),
 addDOMWidget(n,t,element,options){this.panel=element;this.options=options;return{};},computeSize(){return[310,100];},setSize(s){this.size=s;}};
 const app={graph:{_nodes:[node],links:{},getNodeById(){return node;},setDirtyCanvas(){}},queuePrompt(){throw Error('No automatic execution.');}};
 node.graph=app.graph;return {node,app};
}

test('JS emotion and face geometry match the exact original Studixly functions',async()=>{
 const m=await import(modulePath);
 for(const c of golden.emotion) assert.equal(m.emotionPrompt(c.input),c.expected);
 for(const c of golden.face) assert.deepEqual(m.faceFeatures(...c.input),c.expected);
});

test('V2 frontend preserves every old valid prompt byte, and all character sheet outputs match TS',async()=>{
 const m=await import(modulePath);
 const v1=JSON.parse(fs.readFileSync(new URL('./fixtures/creative-golden-v1.json',import.meta.url)));
 for(const c of v1.valid){
  const original=m.composeV2(c.input);
  assert.equal(original.final_prompt,c.expected.final_prompt);
  assert.equal(m.composeV2({...c.input,tools:{...c.input.tools,emotion:{enabled:false,arousal:2,affinity:-2}}}).final_prompt,c.expected.final_prompt);
 }
 for(const c of golden.character)assert.deepEqual(m.characterShots(c.input),c.expected);
});

test('V2 frontend rejects explicit null and forged settings rather than quietly dropping them',async()=>{
 const m=await import(modulePath);
 for(const bad of [{arousal:null},{affinity:null},{targetLabel:null},{arousal:true},{affinity:3},{final_prompt:'forged'}])assert.throws(()=>m.emotionPrompt(bad));
 for(const bad of [{contract_version:null,prompt:'x'},{prompt:'x',mode:null},{prompt:'x',tools:null},{prompt:'x',tools:{emotion:null}}])assert.throws(()=>m.composeV2(bad));
 for(const bad of [{character:null},{style:null},{sheetIds:null},{character:'Ada',secret:'unexpected'}])assert.throws(()=>m.characterShots(bad));
});

test('expression grid has 25 original mapped cells, retained off choices and parameterized face',async()=>{
 const m=await import(modulePath);const {node,app}=setup('ApixlyPromptEmotion',{enabled:false,arousal:0,affinity:0,target_label:'the woman'});
 assert.equal(m.attachFreeV2Panel(node,app),true);
 const cells=all(node.panel).filter(e=>e.dataset.emotionCell);
 assert.equal(cells.length,25);
 all(node.panel).find(e=>e.dataset.emotionCell==='-2,2').dispatch('click');
 assert.equal(node.widgets.find(w=>w.name==='affinity').value,2);
 assert.equal(node.widgets.find(w=>w.name==='arousal').value,2);
 assert.equal(node.widgets.find(w=>w.name==='enabled').value,false);
 all(node.panel).find(e=>e.getAttribute('role')==='switch').dispatch('click');
 assert.match(all(node.panel).find(e=>e.tagName==='textarea').value,/the woman with elated/);
 assert.ok(all(node.panel).some(e=>e.getAttribute('aria-label')==='Original Studixly expression preview'));
 all(node.panel).find(e=>e.tagName==='button'&&e.textContent==='Reset').dispatch('click');
 assert.equal(node.widgets.find(w=>w.name==='arousal').value,0);
 assert.equal(node.widgets.find(w=>w.name==='affinity').value,0);
 assert.equal(node.options.serialize,false);
 for(const button of all(node.panel).filter(e=>e.tagName==='button'))assert.match(button.style.cssText,/min-height:44px/);
 assert.ok(node.size[0]<=340);
});

test('four other panels describe free outputs honestly and never show media receipt actions',async()=>{
 const m=await import(modulePath);
 for(const kind of ['ApixlyPromptComposeV2','ApixlyImageGridSplit','ApixlyEnhancementPrompt','ApixlyCharacterSheetPlan']){
  const {node,app}=setup(kind,{enabled:false,prompt:'literal </textarea><img onerror=bad>',rows:2,columns:3,model:'gemini-3.1-flash-image',width:1024,height:1024,character:'Ada',sheet_ids_json:'["seedance-pack"]',shot_index:1});
  assert.equal(m.attachFreeV2Panel(node,app),true);
  assert.doesNotMatch(node.panel.textContent,/Copy task ID|Copy result URL|Paid action/);
  assert.match(node.panel.textContent,/Free|Offline/);
  assert.equal(all(node.panel).some(e=>e.tagName==='img'),false);
 }
 const {node,app}=setup('ApixlyImageEdit',{});assert.equal(m.attachFreeV2Panel(node,app),false);
});

test('character plan selects exactly one existing shot and never emits a prompt list',async()=>{
 const m=await import(modulePath);const {node,app}=setup('ApixlyCharacterSheetPlan',{enabled:false,character:'Ada',style:'',sheet_ids_json:'["seedance-pack"]',custom:'',shot_index:0});
 m.attachFreeV2Panel(node,app);
 const select=all(node.panel).find(e=>e.tagName==='select');
 assert.equal(select.children.length,4);
 select.value='2';select.dispatch('change');
 assert.equal(node.widgets.find(w=>w.name==='shot_index').value,2);
 assert.equal(node.widgets.find(w=>w.name==='enabled').value,false);
});

test('character selection follows shot identity through reorder and saved reload; removal requires an explicit new choice',async()=>{
 const m=await import(modulePath);
 const start={enabled:false,character:'Ada',style:'',sheet_ids_json:'["key-visual","seedance-pack"]',custom:'',shot_index:1};
 const {node,app}=setup('ApixlyCharacterSheetPlan',start);m.attachFreeV2Panel(node,app);
 const value=n=>node.widgets.find(w=>w.name===n);
 // Remove the preceding key visual: front remains front at its new index.
 all(node.panel).find(e=>e.tagName==='button'&&e.textContent==='Key visual').dispatch('click');
 assert.equal(value('shot_index').value,0);
 assert.equal(node.properties.apixlyCharacterSelection.key,'seedance-pack:0');
 // Insert a preceding sheet through the real native widget callback.
 value('sheet_ids_json').callback('["costume","seedance-pack"]');
 assert.equal(value('shot_index').value,1);
 const saved=JSON.parse(JSON.stringify({properties:node.properties,widgets:Object.fromEntries(node.widgets.map(w=>[w.name,w.value]))}));
 const reloaded=setup('ApixlyCharacterSheetPlan',saved.widgets);reloaded.node.properties=saved.properties;m.attachFreeV2Panel(reloaded.node,reloaded.app);
 assert.equal(reloaded.node.properties.apixlyCharacterSelection.key,'seedance-pack:0');
 // Remove the selected sheet: index 1 remains valid for no other shot.
 all(node.panel).find(e=>e.tagName==='button'&&e.textContent==='Seedance · 3 separate shots').dispatch('click');
 assert.equal(value('shot_index').value,-1);
 all(node.panel).find(e=>e.getAttribute('role')==='switch').dispatch('click');
 assert.match(node.panel.textContent,/Choose one shot/);
 assert.equal(all(node.panel).find(e=>e.tagName==='textarea').value,'');
 // Native INT is a deliberate selection and must recover without a Key.
 value('shot_index').callback(0);
 assert.equal(node.properties.apixlyCharacterSelection.key,'costume:0');
 assert.match(all(node.panel).find(e=>e.tagName==='textarea').value,/Costume and accessory/);
 const selectedFirst=setup('ApixlyCharacterSheetPlan',{...start,shot_index:0});
 m.attachFreeV2Panel(selectedFirst.node,selectedFirst.app);
 all(selectedFirst.node.panel).find(e=>e.tagName==='button'&&e.textContent==='Key visual').dispatch('click');
 // Index zero is still in range for the remaining three-shot pack. It must
 // remain cleared rather than silently selecting its front view.
 assert.equal(selectedFirst.node.widgets.find(w=>w.name==='shot_index').value,-1);
});

test('grid layout follows the actual normalized custom cuts, with pixel rounding left to the host',async()=>{
 const m=await import(modulePath);
 const v={rows:2,columns:2,horizontal_lines_json:'[0.2]',vertical_lines_json:'[0.75,0.25]'};
 assert.deepEqual(m.gridPreviewCuts(v),{x:[0,0.25,0.75,1],y:[0,0.2,1]});
 const {node,app}=setup('ApixlyImageGridSplit',{enabled:true,...v});
 m.attachFreeV2Panel(node,app);
 const rects=all(node.panel).filter(e=>e.tagName==='rect'&&e.dataset.gridTile);
 assert.equal(rects.length,6);
 assert.equal(rects[0].getAttribute('width'),'25');
 assert.equal(rects[0].getAttribute('height'),'20');
 assert.equal(rects[1].getAttribute('x'),'25');
 assert.equal(rects[1].getAttribute('width'),'50');
 assert.match(node.panel.textContent,/rounding/);
 for(const bad of ['[0.5,0.5]','[0]','[1]','[null]'])assert.throws(()=>m.gridPreviewCuts({...v,vertical_lines_json:bad}));
});

test('Compose V2 has an explicit offline refresh for legacy-control changes',async()=>{
 const m=await import(modulePath);
 const {node,app}=setup('ApixlyPromptComposeV2',{prompt:'Same vase',mode:'generate'});
 const angle={id:2,comfyClass:'ApixlyPromptViewpoint',widgets:Object.entries({enabled:true,preset:'custom',yaw:0,pitch:0,shot:'none'}).map(([name,value])=>({name,value}))};
 app.graph._nodes.push(angle);app.graph.getNodeById=id=>id===2?angle:node;
 app.graph.links[7]={origin_id:2,origin_slot:0};node.inputs=[{name:'angle',link:7}];
 m.attachFreeV2Panel(node,app);
 angle.widgets.find(w=>w.name==='yaw').value=90;
 const refresh=all(node.panel).find(e=>e.tagName==='button'&&e.textContent==='Refresh preview');
 assert.ok(refresh);refresh.dispatch('click');
 assert.match(all(node.panel).find(e=>e.tagName==='textarea').value,/right side profile/);
 assert.match(node.panel.textContent,/Refresh|execute/);
});

test('character interpolation treats dollar sequences and inserted placeholders as literal user text',async()=>{
 const m=await import(modulePath);
 const regressions=JSON.parse(fs.readFileSync(new URL('./fixtures/free-tools-v2/literal-interpolation-regressions.json',import.meta.url)));
 for(const c of regressions.cases)assert.deepEqual(m.characterShots(c.input),c.expected);
});

test('literal interpolation is byte-identical to the real Python node builder across all nine sheets',async()=>{
 const m=await import(modulePath);
 const regressions=JSON.parse(fs.readFileSync(new URL('./fixtures/free-tools-v2/literal-interpolation-regressions.json',import.meta.url)));
 const cases=regressions.cases.flatMap(c=>golden.character_sheets.map(sheet=>({...c.input,sheetIds:[sheet.id]})));
 const result=spawnSync('python3',['-c','import json,sys; from apixly_media.free_tools_v2 import build_character_shots; print(json.dumps([build_character_shots(x) for x in json.load(sys.stdin)],ensure_ascii=False))'],{input:JSON.stringify(cases),encoding:'utf8',cwd:new URL('..',import.meta.url),maxBuffer:1024*1024});
 assert.equal(result.status,0,result.stderr);
 const python=JSON.parse(result.stdout);
 for(let i=0;i<cases.length;i++){
  const js=m.characterShots(cases[i]);assert.deepEqual(js,python[i]);
  for(let shot=0;shot<js.length;shot++)assert.deepEqual(Buffer.from(js[shot].prompt,'utf8'),Buffer.from(python[i][shot].prompt,'utf8'));
 }
});

test('public extension entry routes new free nodes before any account/model-picker path',async()=>{
 const m=await import(modulePath);let extension;
 const {node,app}=setup('ApixlyPromptEmotion',{enabled:false,arousal:0,affinity:0,target_label:''});
 app.registerExtension=value=>{extension=value;};
 const forbidden=()=>{throw Error('A free node must not enter the media/account path.');};
 const source=fs.readFileSync(new URL('../web/apixly.js',import.meta.url),'utf8').replace(/^import[^;]+;\n/gm,'');
 vm.runInNewContext(source,{app,api:{},nativeDownloadURL(){},safeResultURL(){},isCreativeNode:()=>false,attachCreativePanel:forbidden,accountBridge:forbidden,attachModelPicker:forbidden,attachFreeV2Panel:m.attachFreeV2Panel,scheduleInitialFreeTemplateView:m.scheduleInitialFreeTemplateView,document:globalThis.document});
 extension.nodeCreated(node);
 assert.equal(node.panel.dataset.apixlyFreeV2,'emotion');
 assert.equal(extension.afterLoadGraph(),undefined,'The native load hook must return immediately, without awaiting a frame.');
});

test('a newly created expression node fits native 375px usable bounds and preserves later user sizing',async()=>{
 const m=await import(modulePath);const {node,app}=setup('ApixlyPromptEmotion',{enabled:false,arousal:0,affinity:0,target_label:''});
 node.size=[440,900];
 const add=node.addDOMWidget;node.addDOMWidget=function(...args){this.domWidget=add.apply(this,args);return this.domWidget;};
 // 142px is the native pre-DOM widget region measured in the real red case.
 node.computeSize=function(){return [440,142+(this.domWidget?.computeSize?.()[1]??0)];};
 m.attachFreeV2Panel(node,app);
 assert.ok(70+node.size[0]<=375,'A newly created tool must fit beside the native sidebar at 1:1.');
 assert.ok(130+node.size[1]<=850,'The default node must fit above the bottom toolbar; its details can scroll.');
 node.setSize([520,820]);node.onConfigure();
 assert.deepEqual(node.size,[520,820],'Loading or resizing an existing node must preserve user dimensions.');
});

function markedTemplateApp(){
 const {node,app}=setup('ApixlyPromptEmotion',{});
 app.graph.extra={ds:{scale:1,offset:[0,0]},apixly_free_tools_v2:{primary_node_id:1,initial_view:{scale:1,offset:[0,0]}}};
 app.canvas={ds:{scale:0.4,offset:[-90,-80]},canvas:new Element('canvas')};
 return {node,app};
}

test('marked new-template view restores once after native fit without awaiting or modifying node sizes',async()=>{
 const m=await import(modulePath);const {node,app}=markedTemplateApp();const frames=[];const size=[...node.size];
 assert.equal(m.scheduleInitialFreeTemplateView(app,cb=>frames.push(cb)),true);
 assert.equal(app.canvas.ds.scale,0.4,'The loader is not blocked and the camera is not changed synchronously.');
 app.canvas.ds.scale=0.3;frames[0]();
 assert.equal(app.canvas.ds.scale,1);assert.deepEqual(app.canvas.ds.offset,[0,0]);assert.deepEqual(node.size,size);
 app.canvas.ds.scale=0.75;
 assert.equal(m.scheduleInitialFreeTemplateView(app,cb=>frames.push(cb)),false);
 assert.equal(app.canvas.ds.scale,0.75,'Later user zoom must remain untouched.');
});

test('unmarked graphs, saved custom views and disabled restore are never focused',async()=>{
 const m=await import(modulePath);
 for(const change of [app=>delete app.graph.extra.apixly_free_tools_v2,app=>app.graph.extra.ds.scale=0.8,app=>app.graph.extra.ds.offset=[10,0],app=>app.ui={settings:{getSettingValue:()=>false}}]){
  const {app}=markedTemplateApp();change(app);
  assert.equal(m.scheduleInitialFreeTemplateView(app,()=>{throw Error('No frame should be queued.');}),false);
  assert.equal(app.canvas.ds.scale,0.4);
 }
});

test('pointer/wheel intent or a replaced graph cancels pending initial-template focus',async()=>{
 const m=await import(modulePath);
 for(const interrupt of [app=>app.canvas.canvas.dispatch('pointerdown'),app=>app.canvas.canvas.dispatch('wheel'),app=>app.graph._nodes=[]]){
  const {app}=markedTemplateApp(),frames=[];
  assert.equal(m.scheduleInitialFreeTemplateView(app,cb=>frames.push(cb)),true);
  interrupt(app);frames[0]();assert.equal(app.canvas.ds.scale,0.4);
 }
});

test('default initial-template scheduling waits two native animation frames and then stops',async()=>{
 const m=await import(modulePath),{app}=markedTemplateApp(),frames=[];
 const previous=globalThis.requestAnimationFrame;globalThis.requestAnimationFrame=cb=>{frames.push(cb);return frames.length;};
 try{
  assert.equal(m.scheduleInitialFreeTemplateView(app),true);assert.equal(frames.length,1);
  frames[0]();assert.equal(frames.length,2);assert.equal(app.canvas.ds.scale,0.4);
  frames[1]();assert.equal(app.canvas.ds.scale,1);assert.equal(frames.length,2);
 }finally{if(previous)globalThis.requestAnimationFrame=previous;else delete globalThis.requestAnimationFrame;}
});
