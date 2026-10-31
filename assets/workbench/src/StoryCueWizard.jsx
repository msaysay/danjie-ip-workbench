import React,{useEffect,useState} from 'react';
import {DESKTOP_COMMANDS,TEXT_MODEL_EXAMPLE,WIZARD_STEPS,publicSetup,safeMessage,startupCommands,stepCanTest} from './storycueContract.js';

const EMPTY={speechKey:'',textKey:'',llmBaseUrl:TEXT_MODEL_EXAMPLE.llmBaseUrl,llmModel:TEXT_MODEL_EXAMPLE.llmModel,enableJev:false,jevKey:''};

export default function StoryCueWizard({api}){
 const [status,setStatus]=useState(null),[directory,setDirectory]=useState(''),[fields,setFields]=useState(EMPTY),[step,setStep]=useState(0),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[passed,setPassed]=useState({});
 const secrets=()=>[fields.speechKey,fields.textKey,fields.jevKey];
 async function refresh(){const next=await api('/storycue/status');setStatus(next);setDirectory(current=>current||next.directory||'');if(next.setup)setFields(current=>({...current,llmBaseUrl:current.llmBaseUrl||next.setup.llmBaseUrl||TEXT_MODEL_EXAMPLE.llmBaseUrl,llmModel:current.llmModel||next.setup.llmModel||TEXT_MODEL_EXAMPLE.llmModel,enableJev:next.setup.jevEnabled}));return next}
 useEffect(()=>{refresh().catch(e=>setMessage(e.message))},[]);
 function report(error){setMessage(safeMessage(error.message,secrets()))}
 async function act(fn){setBusy(true);setMessage('');try{return await fn()}catch(e){report(e);return null}finally{setBusy(false)}}
 async function readDirectory(){const saved=await act(async()=>{const next=await api('/storycue/directory','POST',{directory});setStatus(next);setMessage(next.message||'已读取目录。');return next});return saved}
 function payload(){return {speechKey:fields.speechKey,textKey:fields.textKey,llmBaseUrl:fields.llmBaseUrl.trim(),llmModel:fields.llmModel.trim(),enableJev:fields.enableJev,jevKey:fields.enableJev?fields.jevKey:''}}
 async function saveSetup(){const saved=await api('/storycue/setup','POST',payload());setFields(current=>({...current,speechKey:'',textKey:'',jevKey:''}));if(saved.setup)setStatus(current=>({...current,setup:publicSetup(saved.setup),reachable:true,tokenReady:true}));return saved}
 async function testStep(){
  const id=WIZARD_STEPS[step].id;
  if(!stepCanTest(id,fields,status)){setMessage(id==='desktop'?'请先读取含有 bridge-token 的 StoryCue 目录。':'这一步还缺必填项。Key 留在输入框里，不会写入工作台。');return}
  await act(async()=>{
   if(id!=='desktop')await saveSetup();
   const targets=id==='speech'?['doubao_tts','doubao_asr']:id==='text'?['text_llm']:id==='jev'?['jev']:['desktop'];
   const results=[];
   for(const target of targets){results.push(await api('/storycue/setup/test','POST',{target}))}
   const ok=results.every(item=>item.ok);
   setPassed(current=>({...current,[id]:ok}));
   setMessage(results.map(item=>item.message).filter(Boolean).join(' '));
   await refresh();
  });
 }
 const current=WIZARD_STEPS[step];
 const commands=startupCommands(status?.directory||directory);
 const setup=publicSetup(status?.setup);
 return <section className="experience-section storycue-wizard" aria-label="访谈（StoryCue）"><h2>访谈（StoryCue）</h2><p className="muted">分五步接上这台电脑里的 StoryCue。语音和文字模型的 Key 只交给 StoryCue，写进它自己的 .env.local。工作台不保存、不回显、也不写进日志。</p>
 <label>StoryCue 所在目录<input aria-label="StoryCue 所在目录" value={directory} onChange={e=>setDirectory(e.target.value)} placeholder="Windows 例 C:\Users\你\storycue ；Mac 例 /Users/你/storycue"/></label>
 <div className="row wrap"><button className="primary" disabled={busy||!directory.trim()} onClick={readDirectory}>读取 bridge-token</button>{status?.tokenReady&&<span className="connection-status connected">已读到令牌</span>}{status?.reachable&&<span className="connection-status connected">StoryCue 已连上</span>}</div>
 <div className="storycue-commands"><p className="setting-help">StoryCue 没启动时，在它的目录执行下面其中一条。语音中继固定 8866，避免和工作台 8766 冲突。</p><p>Windows</p><code className="storycue-command">{commands.windows}</code><p>Mac</p><code className="storycue-command">{commands.mac}</code></div>
 <div className="wizard-steps" role="tablist" aria-label="访谈设置步骤">{WIZARD_STEPS.map((item,index)=><button key={item.id} type="button" aria-current={index===step?'step':undefined} onClick={()=>setStep(index)}>{index+1}. {item.title}{passed[item.id]?' · 已测':''}</button>)}</div>
 {current.id==='desktop'&&<div className="storycue-panel"><h3>1. 连接电脑上的 WorkBuddy / Codex</h3><p>访谈主问题由这台电脑上的 WorkBuddy 或 Codex 生成，不用把主问题的模型 Key 填进来。请在 StoryCue 目录执行：</p><ul className="storycue-list"><li><code>{DESKTOP_COMMANDS.connectWorkbuddy}</code></li><li>Codex 用 <code>{DESKTOP_COMMANDS.connectCodex}</code></li><li>还没登录时执行 <code>{DESKTOP_COMMANDS.login}</code></li><li>然后必须执行 <code>{DESKTOP_COMMANDS.doctor}</code></li></ul><p className="setting-help">{setup?.desktopBridge?.verified?'最近的检查已通过。':'还没看到通过的检查时，测试会告诉你要补哪一条命令。'}</p><button disabled={busy||!stepCanTest('desktop',fields,status)} onClick={testStep}>测试</button></div>}
 {current.id==='speech'&&<div className="storycue-panel"><h3>2. 豆包语音 Key（必填）</h3><p>填写火山引擎控制台「语音技术」里的 API Key，并为它开通大模型流式语音识别和语音合成。这不是火山方舟的文本模型 Key，也不是只有 AppID 加 Access Token。识别和合成地址由 StoryCue 内置，这里不用填。</p><label>豆包语音 Key<input aria-label="豆包语音 Key" type="password" autoComplete="off" value={fields.speechKey} onChange={e=>setFields({...fields,speechKey:e.target.value})} placeholder={setup?.speechConfigured?'已配置，留空则保留':'必填'}/></label><button disabled={busy||!stepCanTest('speech',fields,status)} onClick={testStep}>测试</button></div>}
 {current.id==='text'&&<div className="storycue-panel"><h3>3. 文字模型（必填，追问用）</h3><p>访谈里的追问和剪辑建议走这套文字模型。下面的地址是示例方舟 <code>https://ark.cn-beijing.volces.com/api/v3</code>。换成别的服务时，Base URL、模型名和 Key 必须是同一家，不要在地址后再加 /chat/completions。</p><label>Base URL<input aria-label="文字模型 Base URL" value={fields.llmBaseUrl} onChange={e=>setFields({...fields,llmBaseUrl:e.target.value})}/></label><label>模型名<input aria-label="文字模型名" value={fields.llmModel} onChange={e=>setFields({...fields,llmModel:e.target.value})}/></label><label>文字模型 Key<input aria-label="文字模型 Key" type="password" autoComplete="off" value={fields.textKey} onChange={e=>setFields({...fields,textKey:e.target.value})} placeholder={setup?.textConfigured?'同一服务可留空':'必填'}/></label><button disabled={busy||!stepCanTest('text',fields,status)} onClick={testStep}>测试</button></div>}
 {current.id==='jev'&&<div className="storycue-panel"><h3>4. Jev（可选，默认关）</h3><p>Jev 用来增强“对方说完了没有”的判断，默认关闭。关闭时按停顿接话，不访问 Jev。国内网络访问 api.typesafe.ai 可能返回 451，打不开就保持关闭，不影响拍摄。</p><label className="checkbox"><input aria-label="启用 Jev" type="checkbox" checked={fields.enableJev} onChange={e=>setFields({...fields,enableJev:e.target.checked})}/>启用 Jev</label>{fields.enableJev&&<label>Jev Key<input aria-label="Jev Key" type="password" autoComplete="off" value={fields.jevKey} onChange={e=>setFields({...fields,jevKey:e.target.value})}/></label>}<button disabled={busy||!stepCanTest('jev',fields,status)} onClick={testStep}>测试</button></div>}
 {current.id==='done'&&<div className="storycue-panel"><h3>5. 完成</h3><ul className="storycue-list"><li>桌面 AI：{passed.desktop?'已测试':'还没在这一步测试'}</li><li>豆包语音：{passed.speech?'已测试':setup?.speechConfigured?'StoryCue 里已有配置':'还没测试'}</li><li>文字模型：{passed.text?'已测试':setup?.textConfigured?'StoryCue 里已有配置':'还没测试'}</li><li>Jev：{fields.enableJev?(passed.jev?'已测试':'还没测试'):'保持关闭'}</li></ul><p>回到选题脚本页。脚本确认后，点「交给 StoryCue 访谈」。原来的下载按钮仍然可以兜底。剪辑这次只保留建议，不把视频送去剪。</p></div>}
 <div className="row wrap"><button type="button" disabled={step===0} onClick={()=>setStep(step-1)}>上一步</button><button type="button" disabled={step===WIZARD_STEPS.length-1||(current.id!=='done'&&passed[current.id]!==true&&!(current.id==='jev'&&!fields.enableJev&&passed.jev===true))} onClick={()=>setStep(step+1)}>下一步</button></div>
 {message&&<p className="experience-message" role="status">{message}</p>}</section>
}
