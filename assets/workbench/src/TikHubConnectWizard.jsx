import React,{useState} from 'react';
import {OUTSIDE_NOTE,TRY_NOTE,WIZARD_STEPS,linksFrom} from './tikhubConnect.js';
import './tikhub-wizard.css';

export function TikHubOutsideNote({research}){
 const links=linksFrom(research);
 return <aside className="tikhub-outside" aria-label="TikHub 也可以在站外使用"><strong>同一个密钥，TikHub 官网也能用</strong><p>{OUTSIDE_NOTE}</p><div className="row wrap"><a href={links.site} target="_blank" rel="noreferrer">打开 TikHub 官网</a><a href={links.docs} target="_blank" rel="noreferrer">打开 TikHub 文档</a><a href={links.guide} target="_blank" rel="noreferrer">看快速上手</a></div></aside>;
}

export default function TikHubConnectWizard({api,research,onConnected,onTry,tryLabel='去灵感更新一小批'}){
 const links=linksFrom(research);
 const [step,setStep]=useState(research?.needs_reconnect?2:0);
 const [key,setKey]=useState('');
 const [suffix,setSuffix]=useState(research?.suffix||'');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState(research?.needs_reconnect?'这台电脑读不到之前保存的密钥。请重新粘贴，再测一次。':'');
 const [editing,setEditing]=useState(!research?.configured);
 async function testKey(){
  setBusy(true);setError('');
  try{
   const status=await api('/classroom/tikhub/connect','POST',{key});
   setKey('');
   setSuffix(status.suffix||'');
   setStep(3);
   await onConnected?.(status);
  }catch(e){setError(e.message||'没测通。请看原因后改一改，再点一次。')}
  finally{setBusy(false)}
 }
 if(research?.configured&&!editing){
  return <section className="tikhub-wizard" id="tikhub-wizard" aria-label="TikHub 连接"><p className="tikhub-connected"><span className="connection-status connected">已连接</span>密钥尾号 {research.suffix||suffix||'已保存'}。可以去灵感页更新内容。</p><div className="row wrap"><button type="button" onClick={()=>{setEditing(true);setStep(2);setError('');}}>更换密钥</button>{onTry&&<button className="primary" type="button" onClick={onTry}>{tryLabel}</button>}</div><TikHubOutsideNote research={research}/></section>;
 }
 const current=WIZARD_STEPS[step];
 return <section className="tikhub-wizard" id="tikhub-wizard" aria-label="连接 TikHub"><h3>先连上你自己的 TikHub</h3><p className="muted">四步就能测通。工作台只帮你找选题灵感，不会编造平台数据。</p><ol className="tikhub-steps">{WIZARD_STEPS.map((item,index)=><li key={item.id} aria-current={index===step?'step':undefined}><span>{index+1}</span>{item.title}</li>)}</ol>
 {current.id==='connect'&&<div className="tikhub-panel"><h4>1. 连接</h4><p>灵感页要查各平台公开内容，用的是你自己的 TikHub。这一步只是开始，不会扣查询额度。</p><button className="primary" type="button" onClick={()=>setStep(1)}>去连接</button></div>}
 {current.id==='register'&&<div className="tikhub-panel"><h4>2. 注册</h4><p>没有账号就注册，有账号就登录。到控制台复制 API 密钥。工作台不代你注册，也不代充值。</p><div className="row wrap"><a className="button primary" href={links.register} target="_blank" rel="noreferrer">打开 TikHub 注册或登录</a><a className="button" href={links.console} target="_blank" rel="noreferrer">打开控制台复制密钥</a></div><p className="setting-help">也可以先看<a href={links.docs} target="_blank" rel="noreferrer">TikHub 文档</a>或<a href={links.guide} target="_blank" rel="noreferrer">快速上手</a>，确认密钥在控制台的 API 设置里。</p><div className="row wrap"><button type="button" onClick={()=>setStep(0)}>上一步</button><button className="primary" type="button" onClick={()=>setStep(2)}>密钥准备好了</button></div></div>}
 {current.id==='key'&&<div className="tikhub-panel"><h4>3. 配置 Key</h4><p>{research?.storage_note||'密钥只留在这台电脑。Windows 用系统账户保护，Mac 用钥匙串。'}</p><label>粘贴 API 密钥<input aria-label="TikHub API 密钥" type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} placeholder="从 TikHub 控制台复制的完整密钥"/></label><div className="row wrap"><button type="button" onClick={()=>setStep(1)}>上一步</button><button className="primary" type="button" disabled={busy||!key.trim()} onClick={testKey}>{busy?'正在测…':'测一下'}</button></div><p className="setting-help">测一下会向 TikHub 核对这个密钥。密钥不对、网络不通或额度不够，都会把原因写在下面。改完可以再测，不会自动重试。</p></div>}
 {current.id==='done'&&<div className="tikhub-panel"><h4>4. 完成连接</h4><p className="tikhub-connected"><span className="connection-status connected">已测通</span>密钥尾号 {suffix||'已保存'}。</p><p>{TRY_NOTE}</p><button className="primary" type="button" onClick={onTry}>{tryLabel}</button></div>}
 {error&&<p className="tikhub-error" role="alert">{error}</p>}<TikHubOutsideNote research={research}/></section>;
}
