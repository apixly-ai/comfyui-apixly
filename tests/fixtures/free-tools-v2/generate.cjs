/* Fixture oracle: execute pinned Studixly TypeScript, never the Python port. */
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const crypto = require('node:crypto');
const vm = require('node:vm');
const root = process.env.STUDIXLY_REPO;
if (!root) throw Error('Set STUDIXLY_REPO to a local Studixly checkout containing the pinned commit.');
const ts = require(path.join(root, 'node_modules/typescript'));
const sha = '381eaaa437870b43e2a791b14d8bad52dcb5caef';
const sources = {};
function source(file) {
 const text = cp.execFileSync('git', ['show', `${sha}:${file}`], {cwd:root, encoding:'utf8'});
 sources[file] = crypto.createHash('sha256').update(text).digest('hex');
 return text;
}
function run(text, globals={}) {
 const exports = {};
 vm.runInNewContext(ts.transpileModule(text, {compilerOptions:{module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2020}}).outputText, {exports, ...globals});
 return exports;
}
const emotion = run(source('lib/canvas/tools/emotion.ts'));
const face = run(source('components/media/spatial/face-math.ts'));
const character = run(source('lib/canvas/character-sheets.ts').split('// 每行几张')[0].replace(/^import[\s\S]*?;\n/gm, ''));
const media = run(source('components/infinity-canvas/vendor/lib/media-size.ts'));
const params = run(source('lib/ai/media-params.ts'));
const enhancementSource = source('components/infinity-canvas/image-enhancement.ts');
const enhancementPrompt = /prompt:\s*\n\s*"([^"]+)"/.exec(enhancementSource)[1];
const emotionCases=[];
for(let arousal=-2; arousal<=2; arousal++) for(let affinity=-2; affinity<=2; affinity++) {
 for(const targetLabel of ['', '  the woman on the left  ', '\ufeff角色🌠\u3000']) {
  const input={arousal,affinity,targetLabel};
  emotionCases.push({input,expected:emotion.buildEmotionPrompt(input)});
 }
 emotionCases.push({input:{enabled:false,arousal,affinity,targetLabel:'retained'},expected:''});
}
emotionCases.push({input:{},expected:emotion.buildEmotionPrompt({})});
const characterCases=[];
for(const entry of character.CHARACTER_SHEETS) {
 const input={character:'  Astronaut Ada  ',style:' cinematic clay ',sheetIds:[entry.id]};
 characterCases.push({input,expected:character.buildCharacterShots(input)});
}
for(const input of [
 {character:'',style:'',sheetIds:['unknown','seedance-pack','turnaround'],custom:'  new outfit  '},
 {character:'\ufeff角色🌠\u3000',style:'\t',sheetIds:['expressions','key-visual','expressions'],custom:''},
 {character:'Ada',style:'',sheetIds:[],custom:'  custom study  '},
]) characterCases.push({input,expected:character.buildCharacterShots(input)});
const enhancementCases=[];
for(const model of ['grok-imagine-image','grok-imagine-image-quality','gemini-3.1-flash-image-preview','gemini-3-pro-image-preview','gemini-nano-banana-2.1','gpt-image-2','gpt-image-2.5-flare','gpt-image-2.5-sunburst']) {
 for(const [width,height] of [[1024,1024],[1536,1024],[1001,777],[900,2100]]) {
  const aspect=media.inferMediaRatio(`${width}x${height}`);
  const requestParams=params.buildImageRequestParams(model,{...params.defaultImageParams(model),aspect});
  enhancementCases.push({input:{model,width,height},expected:{prompt:enhancementPrompt,aspect,parameters:requestParams,count:1,tools:{}}});
 }
}
const faceCases=[];
for(let a=-2;a<=2;a++) for(let f=-2;f<=2;f++) faceCases.push({input:[a,f],expected:face.faceFeatures(a,f)});
fs.writeFileSync(path.join(__dirname,'golden.json'), JSON.stringify({source_sha:sha,source_hashes:sources,emotion:emotionCases,character:characterCases,enhancement:enhancementCases,face:faceCases,character_sheets:character.CHARACTER_SHEETS},null,2)+'\n');
console.log(JSON.stringify({emotion:emotionCases.length,character:characterCases.length,enhancement:enhancementCases.length,face:faceCases.length,source_sha:sha}));
