/** Free tools v2. No credential, HTTP, queuePrompt or paid-client access. */
import './creative-compiler.js';
import { kindForNode, settingsForNode } from './creative-helpers.mjs';

export const CONTRACT_VERSION='2.0.0';
const CHARACTER_SHEETS=[{"id": "key-visual", "labelKey": "csheetKeyVisual", "hintKey": "csheetKeyVisualHint", "shots": [{"aspectRatio": "2:3", "promptTemplate": "Full-body character key visual of {character}. Style: {style}. Standing in a relaxed confident pose, front view, full figure from head to toe, detailed rendering, clean plain studio background, soft even lighting, high detail."}]}, {"id": "turnaround", "labelKey": "csheetTurnaround", "hintKey": "csheetTurnaroundHint", "shots": [{"aspectRatio": "16:9", "promptTemplate": "Character turnaround model sheet of {character}. Style: {style}. The SAME character shown in four orthographic views arranged left to right: front view, left side profile, right side profile, and back view. Consistent proportions, costume and colors across all four views, neutral A-pose, flat even lighting, plain light grey background, professional character design reference sheet."}]}, {"id": "head-closeups", "labelKey": "csheetHeadCloseups", "hintKey": "csheetHeadCloseupsHint", "shots": [{"aspectRatio": "16:9", "promptTemplate": "Character head study of {character}. Style: {style}. The same head shown from three angles side by side: front, side profile, and three-quarter view. Consistent facial features and hairstyle, neutral expression, clean plain background, character design reference."}]}, {"id": "expressions", "labelKey": "csheetExpressions", "hintKey": "csheetExpressionsHint", "shots": [{"aspectRatio": "4:3", "promptTemplate": "Expression sheet of {character}. Style: {style}. A neat grid of the same character's face showing distinct emotions: neutral, happy, angry, sad, surprised, and smirking. Consistent character design and features across every panel, clean plain background, model sheet."}]}, {"id": "poses", "labelKey": "csheetPoses", "hintKey": "csheetPosesHint", "shots": [{"aspectRatio": "16:9", "promptTemplate": "Character pose sheet of {character}. Style: {style}. The same character in several dynamic full-body action poses, anatomically correct, feet grounded, consistent proportions, costume and colors, plain background, character design reference."}]}, {"id": "costume", "labelKey": "csheetCostume", "hintKey": "csheetCostumeHint", "shots": [{"aspectRatio": "4:3", "promptTemplate": "Costume and accessory breakdown sheet of {character}. Style: {style}. A central full-body view with separate close-up callouts of clothing details, accessories and props arranged around it, each clearly separated, consistent design, clean background, character reference sheet."}]}, {"id": "color-material", "labelKey": "csheetColorMaterial", "hintKey": "csheetColorMaterialHint", "shots": [{"aspectRatio": "4:3", "promptTemplate": "Color and material board for {character}. Style: {style}. A palette of color swatch chips next to material texture close-ups (fabric, metal, skin, hair) beside a small character thumbnail for reference, clean organized layout, design board."}]}, {"id": "proportions", "labelKey": "csheetProportions", "hintKey": "csheetProportionsHint", "shots": [{"aspectRatio": "16:9", "promptTemplate": "Character proportion sheet of {character}. Style: {style}. The same full-body character aligned to a heads-tall measurement grid with horizontal guide lines marking head units, front view, neutral pose, plain background, character design reference."}]}, {"id": "seedance-pack", "labelKey": "csheetSeedancePack", "hintKey": "csheetSeedancePackHint", "shots": [{"aspectRatio": "2:3", "promptTemplate": "Clean reference photo of {character}. Style: {style}. Front view, full body, neutral standing pose, plain seamless background, even lighting, sharp focus, consistent character."}, {"aspectRatio": "2:3", "promptTemplate": "Clean reference photo of the SAME character {character}. Style: {style}. Three-quarter view, full body, neutral standing pose, plain seamless background, even lighting, consistent with the front-view reference."}, {"aspectRatio": "2:3", "promptTemplate": "Clean reference photo of the SAME character {character}. Style: {style}. Side profile view, full body, neutral standing pose, plain seamless background, even lighting, consistent with the front-view reference."}]}];
const ENHANCEMENT_PROMPT="Improve the visual clarity of this image: reduce compression artifacts and noise, recover natural fine detail, and keep edges clean without halos. Preserve the original composition, identity, text, colors, lighting and objects. Do not add or remove elements or change the artistic style.";
const AROUSAL={'-2':'deeply calm, still expression','-1':'relaxed, composed expression','1':'alert, animated expression','2':'intense, high-energy expression, wide eyes'};
const AFFINITY={'-2':'cold distant gaze, detached expression','-1':'reserved, aloof expression, averted gaze','1':'gentle smile, soft eyes','2':'warm beaming smile, smiling eyes, open and approachable'};
const QUADRANTS={
 '1:1':{2:'cheerful',3:'joyful, excited',4:'elated, beaming smile'},
 '1:-1':{2:'annoyed, raised eyebrow',3:'angry, furrowed brow',4:'furious, scowl, furrowed brow, clenched teeth'},
 '-1:-1':{2:'bored, indifferent',3:'gloomy, faint frown',4:'melancholic, downturned mouth, drooping eyelids'},
 '-1:1':{2:'content',3:'serene expression, at ease',4:'peaceful, serene expression'},
};
const KINDS={ApixlyPromptEmotion:'emotion',ApixlyPromptComposeV2:'compose',ApixlyImageGridSplit:'grid',ApixlyEnhancementPrompt:'enhancement',ApixlyCharacterSheetPlan:'character'};
const DEFAULTS={
 emotion:{enabled:false,arousal:0,affinity:0,target_label:''},
 compose:{prompt:'',mode:'generate'},
 grid:{enabled:false,rows:2,columns:2,horizontal_lines_json:'[]',vertical_lines_json:'[]'},
 enhancement:{enabled:false,model:'gemini-3.1-flash-image',width:1024,height:1024},
 character:{enabled:false,character:'',style:'',sheet_ids_json:'["key-visual"]',custom:'',shot_index:-1},
};
const TITLES={emotion:'Expression',compose:'Final prompt · V2',grid:'Image Grid Split',enhancement:'AI Redraw Enhancement',character:'Character Sheet Plan'};
const SHEET_LABELS={'key-visual':'Key visual',turnaround:'Turnaround','head-closeups':'Head closeups',expressions:'Expressions',poses:'Action poses',costume:'Costume & props','color-material':'Color & material',proportions:'Proportions','seedance-pack':'Seedance · 3 separate shots'};
const BUTTON='min-height:44px;min-width:44px;border:1px solid #2e8fff55;border-radius:9px;background:#1670f018;color:inherit;cursor:pointer;padding:7px 10px;font:inherit;white-space:normal';
const PANELS=new WeakMap();
let nextFaceId=0;
const text=(v,name,limit=20000)=>{if(typeof v!=='string'||v.length>limit)throw Error(`${name}: expected bounded text.`);return v;};
const level=(v,name)=>{if(!Number.isInteger(v)||v< -2||v>2)throw Error(`${name}: expected an integer from -2 to 2.`);return v;};
const optional=(object,key,fallback)=>Object.hasOwn(object,key)?object[key]:fallback;

export function emotionPrompt(setting={}){
 if(!setting||typeof setting!=='object'||Array.isArray(setting)||Object.keys(setting).some(k=>!['enabled','arousal','affinity','targetLabel'].includes(k)))throw Error('emotion: invalid setting.');
 if(setting.enabled!==undefined&&typeof setting.enabled!=='boolean')throw Error('emotion.enabled: expected boolean.');
 const a=level(optional(setting,'arousal',0),'arousal'),f=level(optional(setting,'affinity',0),'affinity'),target=text(optional(setting,'targetLabel',''),'targetLabel',1000).trim();
 if(setting.enabled===false||(!a&&!f))return '';
 const anchor=a&&f?QUADRANTS[`${Math.sign(a)}:${Math.sign(f)}`][Math.abs(a)+Math.abs(f)]:'';
 const fragment=[...new Set([anchor,AROUSAL[a],AFFINITY[f]].filter(Boolean).flatMap(s=>s.split(', ')))].join(', ');
 return target?`${target} with ${fragment}`:fragment;
}

export function faceFeatures(arousal,affinity){
 const clamp=(n,lo,hi)=>Math.max(lo,Math.min(hi,n));
 const an=clamp(arousal/2,-1,1),fn=clamp(affinity/2,-1,1);
 return {mouthCurve:clamp(fn*0.85+an*0.15,-1,1),mouthOpen:clamp(Math.max(0,an),0,1),eyeOpen:clamp(0.55+0.45*an,0.15,1),browRaise:an,browAngle:fn};
}

export function composeV2(payload){
 if(!payload||typeof payload!=='object'||Array.isArray(payload)||Object.keys(payload).some(k=>!['contract_version','prompt','mode','tools'].includes(k)))throw Error('Invalid V2 payload.');
 if(optional(payload,'contract_version',CONTRACT_VERSION)!==CONTRACT_VERSION)throw Error('Expected V2 contract.');
 const tools=optional(payload,'tools',{});
 if(!tools||typeof tools!=='object'||Array.isArray(tools)||Object.keys(tools).some(k=>!['angle','lighting','emotion','camera'].includes(k)))throw Error('Unknown V2 tool.');
 const expression=emotionPrompt(optional(tools,'emotion',{})),legacyTools=Object.fromEntries(Object.entries(tools).filter(([k])=>k!=='emotion'));
 const old=globalThis.ApixlyCreativeControlsV1.composeCreativePrompt({prompt:payload.prompt,mode:optional(payload,'mode','generate'),tools:legacyTools});
 if(!expression)return {contract_version:CONTRACT_VERSION,...old};
 const edit=payload.mode==='edit';
 const sections=[...old.sections];
 const index=sections.findIndex(s=>s.tool==='camera');
 sections.splice(index<0?sections.length:index,0,{tool:'emotion',label:'Expression',text:edit?`Change the subject's expression: ${expression}.`:`Expression: ${expression}`});
 const lines=sections.map(s=>s.text);
 if(edit)lines.push('Preserve all subject and scene details that are not explicitly requested to change.');
 const final=(payload.prompt?payload.prompt+'\n\n':'')+lines.join('\n');
 text(final,'final_prompt');
 return {contract_version:CONTRACT_VERSION,final_prompt:final,sections,applied_tools:sections.map(s=>s.tool),changed:final!==payload.prompt};
}

export function characterShots(input){
 if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).some(k=>!['character','style','sheetIds','custom'].includes(k)))throw Error('Character plan: unknown or invalid fields.');
 const character=text(optional(input,'character',''),'character',4000).trim()||'a character';
 const style=text(optional(input,'style',''),'style',2000).trim()||'detailed, high quality';
 const custom=text(optional(input,'custom',''),'custom',4000).trim();
 const ids=optional(input,'sheetIds',[]);
 if(!Array.isArray(ids)||ids.length>32||ids.some(id=>typeof id!=='string'))throw Error('Invalid sheet IDs.');
 // One pass over original template tokens: dollar sequences and inserted
 // placeholders are literal user text, not replacement syntax or recursion.
 const shots=ids.flatMap(id=>(CHARACTER_SHEETS.find(s=>s.id===id)?.shots??[]).map(s=>({tag:id,prompt:s.promptTemplate.replaceAll(/\{(character|style)\}/g,(_match,key)=>({character,style})[key]),aspectRatio:s.aspectRatio})));
 if(custom)shots.push({tag:'custom',prompt:`${character}. ${custom}. Style: ${style}. Full body, clean plain background, consistent character, high detail.`,aspectRatio:'2:3'});
 if(shots.length>32)throw Error('Plan exceeds 32 preview shots.');
 return shots;
}
export function gridPreviewCuts(v){
 function cuts(raw,count){
  if(!Number.isInteger(count)||count<1||count>12)throw Error('Grid counts must be integers from 1 to 12.');
  const lines=JSON.parse(raw);
  if(!Array.isArray(lines)||lines.length>11||lines.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<=0||x>=1))throw Error('Use up to 11 normalized cuts strictly inside (0,1).');
  const result=lines.length?[0,...lines.slice().sort((a,b)=>a-b),1]:Array.from({length:count+1},(_,i)=>i/count);
  if(result.some((x,i)=>i>0&&x<=result[i-1]))throw Error('Duplicate cut positions are not allowed.');
  return result;
 }
 return {x:cuts(v.vertical_lines_json,v.columns),y:cuts(v.horizontal_lines_json,v.rows)};
}
function reconcileCharacterSelection(node,v,shots){
 const ordinals=new Map();
 const entries=shots.map(shot=>{
  const length=CHARACTER_SHEETS.find(sheet=>sheet.id===shot.tag)?.shots.length??1;
  const ordinal=(ordinals.get(shot.tag)??0)%length;ordinals.set(shot.tag,ordinal+1);
  return {shot,key:`${shot.tag}:${ordinal}`};
 });
 node.properties??={};
 const previous=node.properties.apixlyCharacterSelection;
 let index=v.shot_index,key=null;
 const manual=!previous||index!==previous.index;
 if(manual){
  if(Number.isInteger(index)&&index>=0&&index<entries.length)key=entries[index].key;
  else index=-1;
 }else if(previous.sheetIds!==v.sheet_ids_json){
  index=previous.key?entries.findIndex(entry=>entry.key===previous.key):-1;
  key=index>=0?entries[index].key:null;
 }else{
  key=previous.key??null;
  if(index<0||index>=entries.length||!key){index=-1;key=null;}
 }
 const native=node.widgets?.find(widget=>widget.name==='shot_index');if(native)native.value=index;
 v.shot_index=index;
 node.properties.apixlyCharacterSelection={key,index,sheetIds:v.sheet_ids_json};
 return entries;
}
function values(node){return {...DEFAULTS[KINDS[node.comfyClass]],...Object.fromEntries((node.widgets??[]).map(w=>[w.name,w.value]))};}
function element(tag,label,style){const e=document.createElement(tag);if(label!==undefined)e.textContent=label;if(style)e.style.cssText=style;return e;}
function svg(tag,attrs){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,v]of Object.entries(attrs))e.setAttribute(key,v);return e;}
function button(label,action){const e=element('button',label,BUTTON);e.type='button';e.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();action();});return e;}
function refreshAll(app){for(const n of app.graph?._nodes??[])PANELS.get(n)?.();app.graph?.setDirtyCanvas(true,true);}
function set(node,app,name,value){const widget=node.widgets?.find(w=>w.name===name);if(widget)widget.value=value;refreshAll(app);}
function emotionSettings(node){const v=values(node);return {enabled:v.enabled,arousal:v.arousal,affinity:v.affinity,targetLabel:v.target_label};}
function composePayload(node,app){
 const v=values(node),tools={};
 for(const input of node.inputs??[]){
  if(input.link==null)continue;
  if(input.name==='prompt')throw Error('Upstream text is shown after free host execution; local preview uses the prompt field.');
  if(!['angle','lighting','emotion','camera'].includes(input.name))continue;
  const link=app.graph?.links?.[input.link],origin=link&&app.graph?.getNodeById(link.origin_id);
  if(!origin||link.origin_slot!==0)throw Error('Connect a matching free Apixly setting output.');
  if(input.name==='emotion'&&origin.comfyClass==='ApixlyPromptEmotion')tools.emotion=emotionSettings(origin);
  else if(kindForNode(origin)===input.name)tools[input.name]=settingsForNode(origin);
  else throw Error('Connected settings are available after free host execution.');
 }
 return {contract_version:CONTRACT_VERSION,prompt:v.prompt,mode:v.mode,tools};
}
function faceDrawing(a,f,id){
 const shape=faceFeatures(a,f),eyeRy=1.8+shape.eyeOpen*5.2,brow=37-shape.browRaise*4,inner=-shape.browAngle*3.5,corner=71-shape.mouthCurve*3,ctrl=71+shape.mouthCurve*11,half=shape.mouthOpen*6;
 const drawing=svg('svg',{viewBox:'0 0 100 100',width:'132',height:'132','aria-label':'Original Studixly expression preview',role:'img',fill:'none'});
 const defs=svg('defs',{}),gradient=svg('radialGradient',{id,cx:'50%',cy:'34%',r:'72%'});
 gradient.append(svg('stop',{offset:'0%','stop-color':'rgba(46,143,255,0.20)'}),svg('stop',{offset:'100%','stop-color':'rgba(9,12,20,0.35)'}));defs.append(gradient);drawing.append(defs);
 drawing.append(svg('ellipse',{cx:50,cy:52,rx:31,ry:37,fill:`url(#${id})`,stroke:'rgba(46,143,255,0.55)','stroke-width':1.4}));
 for(const d of [`M31 ${brow} L46 ${brow+inner}`,`M69 ${brow} L54 ${brow+inner}`])drawing.append(svg('path',{d,stroke:'rgba(226,232,240,0.92)','stroke-linecap':'round','stroke-width':2.4}));
 for(const cx of [38.5,61.5])drawing.append(svg('ellipse',{cx,cy:48,rx:5.6,ry:eyeRy,fill:'rgba(226,232,240,0.95)'}),svg('circle',{cx,cy:48,r:Math.min(2.5,eyeRy),fill:'#0b1220'}));
 drawing.append(svg('path',{d:`M40 ${corner} Q50 ${ctrl-half} 60 ${corner} Q50 ${ctrl+half} 40 ${corner} Z`,fill:half>0.6?'rgba(11,18,32,0.85)':'none',stroke:'rgba(125,192,255,0.95)','stroke-linejoin':'round','stroke-width':2.2}));
 return drawing;
}

export function attachFreeV2Panel(node,app){
 const kind=KINDS[node.comfyClass];if(!kind)return false;
 if(PANELS.has(node))return true;
 const root=element('section',undefined,'box-sizing:border-box;display:flex;flex-direction:column;gap:10px;min-width:0;padding:12px;border:1px solid #2e8fff44;border-radius:14px;background:linear-gradient(145deg,#2e8fff12,#06070ae6);color:#e2e8f0;font:12px/1.5 system-ui;overflow:auto;pointer-events:auto');
 root.dataset.apixlyFreeV2=kind;
 root.addEventListener('pointerdown',e=>e.stopPropagation());
 const header=element('div',undefined,'display:flex;align-items:center;gap:10px;flex-wrap:wrap');
 header.append(element('strong',TITLES[kind],'flex:1;font-size:15px'));
 let toggle;
 if(kind!=='compose'){toggle=button('Off',()=>set(node,app,'enabled',!values(node).enabled));toggle.setAttribute('role','switch');toggle.setAttribute('aria-label',`Enable ${TITLES[kind]}`);header.append(toggle);}
 root.append(header,element('div','Free · Offline · Your settings stay in this workflow.','font-size:11px;color:#7cc0ff'));
 const status=element('div','','color:#94a3b8;overflow-wrap:anywhere');root.append(status);
 let drawEmotion,drawGrid,drawCharacter;
 if(kind==='emotion'){
  const face=element('div',undefined,'display:flex;justify-content:center;border:1px solid #2e8fff33;border-radius:12px;background:radial-gradient(circle at 50% 20%,#1e293b99,#090c14aa)');
  const id=`apixly-expression-${++nextFaceId}`;
  root.append(face,element('div','High energy ↑ · Calm ↓','text-align:center;color:#94a3b8;font-size:11px'),element('div','Warm ← Affinity → Aloof','text-align:center;color:#94a3b8;font-size:11px'));
  const grid=element('div',undefined,'display:grid;grid-template-columns:repeat(5,minmax(44px,1fr));gap:3px;align-self:stretch');grid.setAttribute('role','grid');grid.setAttribute('aria-label','Original Studixly 5 by 5 emotion grid');
  const cells=[];
  for(let y=2;y>=-2;y--)for(let x=-2;x<=2;x++){
   const cell=button('·',()=>{const va=node.widgets.find(w=>w.name==='arousal'),vf=node.widgets.find(w=>w.name==='affinity');if(va)va.value=y;if(vf)vf.value=-x;refreshAll(app);});
   cell.dataset.emotionCell=`${x},${y}`;cell.setAttribute('aria-label',`Arousal ${y}, affinity ${-x}`);cell.setAttribute('role','gridcell');grid.append(cell);cells.push({cell,x,y});
  }
  root.append(grid);
  drawEmotion=v=>{face.replaceChildren(faceDrawing(v.arousal,v.affinity,id));for(const {cell,x,y}of cells){const selected=v.arousal===y&&v.affinity===-x;cell.setAttribute('aria-selected',String(selected));cell.setAttribute('aria-pressed',String(selected));cell.style.cssText=BUTTON+`;padding:0;font-size:22px;border-color:${selected?'#7cc0ff':'#2e8fff44'};background:${selected?'#1670f055':'#1670f012'}`;}};
 }
 if(kind==='grid'){
  const diagram=element('div',undefined,'aspect-ratio:1.5;min-height:120px;border:1px solid #2e8fff55;border-radius:10px;background:#06070a88;overflow:hidden');root.append(diagram);
  root.append(element('p','Lossless tiles + row/column coordinates. Uneven pixel sizes remain separate images. Downstream nodes execute per tile: use Preview/Save unless you intend multiple paid requests.','margin:0;color:#94a3b8'));
  root.append(element('p','Preview uses normalized cut proportions. Exact source-pixel rounding and empty-pixel checks happen on free host execution. Off passes the whole original IMAGE batch through once.','margin:0;color:#94a3b8;font-size:11px'));
  drawGrid=v=>{
   const {x,y}=gridPreviewCuts(v),drawing=svg('svg',{viewBox:'0 0 100 100',width:'100%',height:'100%',preserveAspectRatio:'none','aria-label':'Normalized grid split layout',role:'img'});
   for(let row=0;row<y.length-1;row++)for(let column=0;column<x.length-1;column++){
    const left=x[column]*100,top=y[row]*100,width=(x[column+1]-x[column])*100,height=(y[row+1]-y[row])*100;
    const tile=svg('rect',{x:left,y:top,width,height,fill:'#1670f018',stroke:'#2e8fff77','stroke-width':0.35});tile.dataset.gridTile=`${row},${column}`;drawing.append(tile);
    if(width>8&&height>8){const label=svg('text',{x:left+width/2,y:top+height/2,fill:'#7cc0ff','text-anchor':'middle','dominant-baseline':'middle','font-size':5});label.textContent=`${row+1}·${column+1}`;drawing.append(label);}
   }
   diagram.replaceChildren(drawing);
  };
 }
 let shotSelect,sheetButtons=[];
 if(kind==='character'){
  const choices=element('div',undefined,'display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px');
  for(const sheet of CHARACTER_SHEETS){const choice=button(SHEET_LABELS[sheet.id],()=>{try{const ids=JSON.parse(values(node).sheet_ids_json);if(!Array.isArray(ids))throw Error();const next=ids.includes(sheet.id)?ids.filter(id=>id!==sheet.id):[...ids,sheet.id];set(node,app,'sheet_ids_json',JSON.stringify(next));}catch{status.textContent='Use a JSON list of sheet IDs.';}});choices.append(choice);sheetButtons.push([sheet.id,choice]);}
  root.append(choices,element('label','Select ONE output shot · no automatic batch','color:#94a3b8'));
  shotSelect=element('select',undefined,'min-height:44px;min-width:44px;max-width:100%;padding:8px;border:1px solid #2e8fff55;border-radius:9px;background:#0f172a;color:inherit');shotSelect.setAttribute('aria-label','Selected single character shot');shotSelect.addEventListener('change',()=>set(node,app,'shot_index',Number(shotSelect.value)));root.append(shotSelect);
  drawCharacter=v=>{
   const ids=JSON.parse(v.sheet_ids_json),shots=characterShots({character:v.character,style:v.style,sheetIds:ids,custom:v.custom});
   reconcileCharacterSelection(node,v,shots);
   for(const [id,item]of sheetButtons){const chosen=ids.includes(id);item.setAttribute('aria-pressed',String(chosen));item.style.cssText=BUTTON+`;text-align:left;background:${chosen?'#1670f044':'#1670f012'}`;}
   const placeholder=element('option','Choose one shot…');placeholder.value='-1';placeholder.disabled=true;
   shotSelect.replaceChildren(placeholder,...shots.map((s,i)=>{const option=element('option',`${i+1}. ${SHEET_LABELS[s.tag]??'Custom'} · ${s.aspectRatio}`);option.value=String(i);return option;}));
   shotSelect.value=String(v.shot_index);
   if((v.shot_index<0||v.shot_index>=shots.length)&&v.enabled)throw Error('Choose one shot explicitly; the previous shot was removed or none was selected.');
   return shots;
  };
  root.append(element('p','Seedance pack = front, three-quarter, side: three independent plans. Only the selected prompt is output. Generated identity consistency still depends on your model.','margin:0;color:#94a3b8'));
 }
 if(kind==='enhancement')root.append(element('p','AI redraw guidance. It may change fine details and text; it is not pixel-preserving super-resolution. Connect your source image and this prompt/parameters explicitly to Image: Edit.','margin:0;color:#94a3b8'));
 const preview=element('textarea',undefined,'box-sizing:border-box;width:100%;min-height:140px;resize:vertical;border:1px solid #2e8fff33;border-radius:10px;background:#06070aaa;color:#cce7ff;padding:10px;font:11px/1.5 ui-monospace,monospace');preview.readOnly=true;preview.setAttribute('aria-label','Free tool output preview');root.append(preview);
 const actions=element('div',undefined,'display:flex;gap:7px;flex-wrap:wrap');
 const copy=button('Copy preview',async()=>{try{await navigator.clipboard.writeText(preview.value);}catch{status.textContent='Clipboard unavailable. Select and copy the preview text.';}});
 const reset=button('Reset',()=>{for(const [name,value]of Object.entries(DEFAULTS[kind])){const widget=node.widgets?.find(w=>w.name===name);if(widget)widget.value=value;}refreshAll(app);});actions.append(copy,reset);root.append(actions);
 if(kind==='compose'){
  actions.append(button('Refresh preview',()=>refreshAll(app)));
  root.append(element('p','After changing older Viewpoint, Lighting or Lens controls, click Refresh preview or execute this free node. Host execution always recomputes the connected settings.','margin:0;color:#94a3b8;font-size:11px'));
 }
 function refresh(){
  try{
   const v=values(node);if(toggle){toggle.textContent=v.enabled?'On':'Off';toggle.setAttribute('aria-checked',String(v.enabled));}
   drawEmotion?.(v);drawGrid?.(v);
   if(kind==='emotion')preview.value=emotionPrompt(emotionSettings(node));
   if(kind==='compose')preview.value=composeV2(composePayload(node,app)).final_prompt;
   if(kind==='grid')preview.value=JSON.stringify({enabled:v.enabled,rows:v.rows,columns:v.columns,horizontalLines:JSON.parse(v.horizontal_lines_json),verticalLines:JSON.parse(v.vertical_lines_json),note:'Layout diagram only; execute free node for exact source-pixel coordinates.'},null,2);
   if(kind==='enhancement')preview.value=v.enabled?ENHANCEMENT_PROMPT:'';
   if(kind==='character'){const shots=drawCharacter(v);preview.value=v.enabled?(shots[v.shot_index]?.prompt??''):'';}
   copy.disabled=!preview.value;
   status.textContent=kind==='compose'?'Free V2 preview · Recomputed from connected settings':v.enabled?'On · Free outputs only; no generation submitted':kind==='grid'?'Off · Original IMAGE batch passes through as one output':'Off · Settings retained; prompt outputs are blank';
  }catch(error){preview.value='';copy.disabled=true;status.textContent=error.message;}
 }
 PANELS.set(node,refresh);
 let updating=false;
 for(const native of node.widgets??[]){if(native.name==='apixly_free_v2')continue;const old=native.callback;native.callback=function(value,...args){if(updating)return;updating=true;try{old?.call(this,value,...args);native.value=value;}finally{updating=false;}refreshAll(app);};}
 for(const hook of ['onConnectionsChange','onConfigure','onAdded']){const old=node[hook];node[hook]=function(...args){old?.apply(this,args);refreshAll(app);};}
 const executed=node.onExecuted;
 node.onExecuted=function(message){executed?.apply(this,arguments);const actual=message?.apixly_free_v2?.[0];if(!actual)return;preview.value=actual.final_prompt??actual.prompt??actual.selected_prompt??JSON.stringify(actual,null,2);copy.disabled=!preview.value;status.textContent='Executed offline output · No generation submitted';};
 const widget=node.addDOMWidget('apixly_free_v2','div',root,{serialize:false,hideOnZoom:false});widget.computeSize=()=>[280,kind==='emotion'?650:kind==='character'?670:420];
 refresh();node.setSize([Math.max(300,node.size[0]),Math.max(node.computeSize()[1],node.size[1])]);return true;
}
