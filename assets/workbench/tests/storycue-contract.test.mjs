import test from 'node:test';
import assert from 'node:assert/strict';
import {DESKTOP_COMMANDS,FRAMEWORKS,TEXT_MODEL_EXAMPLE,WIZARD_STEPS,formatInterview,publicSetup,safeMessage,startupCommands,stepCanTest} from '../src/storycueContract.js';

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
 assert.deepEqual(FRAMEWORKS.map(item=>item[0]),['北极星','四喜','抄近路','消费心理','情绪','业务传记','云参访','业务硬控']);
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
 const view=formatInterview({schema:'storycue.interview-export.v1',demo:true,framework:'北极星',plan:{focus:'只核对虚构稿',questions:[{label:'观点入口',question:'先核对什么？',notes:'不编故事'}]},entries:[{role:'嘉宾',text:'缺的材料继续留空',provisional:false},{role:'嘉宾',text:'未确认',provisional:true}],editingAdvice:{mainline:'只留核对',clips:[{title:'先核对'}],cautions:['虚构演练']}});
 assert.equal(view.demo,true);
 assert.equal(view.entries.length,1);
 assert.equal(view.entries[0].text,'缺的材料继续留空');
 assert.equal(view.mainline,'只留核对');
 assert.equal(formatInterview({schema:'other'}),null);
});
