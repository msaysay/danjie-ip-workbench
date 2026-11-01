import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DESKTOP_COMMANDS,FRAMEWORKS,TEXT_MODEL_EXAMPLE,WIZARD_STEPS,formatInterview,frameworkLabel,publicSetup,safeMessage,startupCommands,stepCanTest} from '../src/storycueContract.js';

const OURS = ['观点破题','四维信任','方法直给','痛点解答','情绪共鸣','人物故事','现场探访','决策问答'];
const HIDDEN = ['北极星','四喜','抄近路','消费心理','业务传记','云参访','业务硬控'];

test('startup lines set the voice relay away from the workbench port',()=>{
 const lines=startupCommands('/Users/me/storycue');
 assert.match(lines.mac,/VOICE_RELAY_PORT=8866 npm run dev/);
 assert.match(lines.windows,/set VOICE_RELAY_PORT=8866&& npm run dev/);
 assert.equal(lines.voiceRelayPort,'8866');
 assert.doesNotMatch(lines.mac,/8766/);
 assert.equal(DESKTOP_COMMANDS.connectWorkbuddy,'npm run desktop:connect -- --host workbuddy');
 assert.equal(DESKTOP_COMMANDS.connectCodex,'npm run desktop:connect -- --host codex');
 assert.equal(DESKTOP_COMMANDS.login,'npm run desktop:login');
 assert.equal(DESKTOP_COMMANDS.doctor,'npm run desktop:doctor');
});

test('wizard keeps eight frameworks and does not echo keys from status',()=>{
 assert.deepEqual(FRAMEWORKS.map(item=>item[0]),OURS);
 assert.deepEqual(FRAMEWORKS.map(item=>item[1]),OURS);
 assert.equal(WIZARD_STEPS.map(item=>item.id).join(','),'desktop,speech,text,jev,done');
 assert.equal(TEXT_MODEL_EXAMPLE.llmBaseUrl,'https://ark.cn-beijing.volces.com/api/v3');
 const view=publicSetup({speechConfigured:true,speechKey:'vk-should-not-appear',llmBaseUrl:TEXT_MODEL_EXAMPLE.llmBaseUrl,llmModel:'demo-model',desktopBridge:{verified:true,host:'codex',token:'bridge-should-not-appear'}});
 assert.equal(view.speechConfigured,true);
 assert.equal(view.llmModel,'demo-model');
 assert.equal(JSON.stringify(view).includes('vk-should-not-appear'),false);
 assert.equal(JSON.stringify(view).includes('bridge-should-not-appear'),false);
});

test('each required step stays blocked until its own field is present',()=>{
 const status={tokenReady:true,setup:{speechConfigured:false,textConfigured:false,jevEnabled:false}};
 const empty={speechKey:'',textKey:'',llmBaseUrl:'',llmModel:'',enableJev:false,jevKey:''};
 assert.equal(stepCanTest('desktop',empty,status),true);
 assert.equal(stepCanTest('speech',empty,status),false);
 assert.equal(stepCanTest('speech',{...empty,speechKey:'x'},status),true);
 assert.equal(stepCanTest('text',{...empty,llmBaseUrl:'https://example.com/v1',llmModel:'m'},status),false);
 assert.equal(stepCanTest('text',{...empty,llmBaseUrl:'https://example.com/v1',llmModel:'m',textKey:'k'},status),true);
 assert.equal(stepCanTest('jev',empty,status),true);
 assert.equal(stepCanTest('jev',{...empty,enableJev:true},status),false);
 assert.equal(stepCanTest('speech',empty,{tokenReady:false}),false);
});

test('messages and interview view drop secrets and unconfirmed lines',()=>{
 assert.equal(safeMessage('拒绝保存：vk-storycue-test-key','vk-storycue-test-key'.length?['vk-storycue-test-key']:[]),'拒绝保存：[redacted]');
 const view=formatInterview({schema:'storycue.interview-export.v1',demo:true,framework:'观点破题',plan:{focus:'只核对虚构稿',questions:[{label:'观点入口',question:'先核对什么？',notes:'不编故事'}]},entries:[{role:'嘉宾',text:'缺的材料继续留空',provisional:false},{role:'嘉宾',text:'未确认',provisional:true}],editingAdvice:{mainline:'只留核对',clips:[{title:'先核对'}],cautions:['虚构演练']}});
 assert.equal(view.framework,'观点破题');
 assert.equal(formatInterview({schema:'storycue.interview-export.v1',framework:'北极星',plan:{questions:[]},entries:[]}).framework,'');
 assert.equal(frameworkLabel('四喜'),'');
 assert.equal(view.demo,true);
 assert.equal(view.entries.length,1);
 assert.equal(view.entries[0].text,'缺的材料继续留空');
 assert.equal(view.mainline,'只留核对');
 assert.equal(formatInterview({schema:'other'}),null);
 const handoff=readFileSync(new URL('../src/StoryCueHandoff.jsx',import.meta.url),'utf8');
 const contract=readFileSync(new URL('../src/storycueContract.js',import.meta.url),'utf8');
 assert.equal(handoff.includes('（{item.id}）'),false);
 for (const old of HIDDEN) {
  assert.equal(handoff.includes(old),false,old);
  assert.equal(contract.includes(old),false,old);
  assert.equal(JSON.stringify(FRAMEWORKS).includes(old),false,old);
 }
});
