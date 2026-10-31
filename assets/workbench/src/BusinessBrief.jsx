import React,{useEffect,useState} from 'react';
export default function BusinessBrief({api,open,onClose,onSettings,refreshSignal}){
 const [data,setData]=useState(null),[message,setMessage]=useState('');
 useEffect(()=>{if(open)api('/experience/business').then(setData).catch(e=>setMessage(e.message))},[open,refreshSignal]);
 if(!open)return null;
 function readable(a){if(!a.text)return '这份原件尚未提取文字，请在WorkBuddy里阅读。';if(!a.name.endsWith('.json'))return a.text;try{const value=JSON.parse(a.text.replace(/^\uFEFF/,''));if(Array.isArray(value.dimensions))return [value.business,value.group_name,...value.dimensions.map(d=>(d.title||d.label||d.id)+'：'+(d.main||d.detail||'尚不了解')),...(value.pairs||[]).map(p=>(p.need_title||'')+' / '+(p.concern_title||'')+(p.basis==='candidate'?'（推演，待核对）':''))].filter(Boolean).join('\n\n')}catch{}return a.text}
 return <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section className="modal business-brief large" role="dialog" aria-modal="true" aria-label="我的业务底稿" onKeyDown={e=>e.key==='Escape'&&onClose()}>
  <div className="row spread"><div><small>接着已经做过的成果用</small><h2>我的业务底稿</h2></div><button autoFocus onClick={onClose}>关闭</button></div>
  {data?.available?<><div className="brief-identity"><h3>{data.owner}</h3><p>{data.business}</p><span className="status">{data.mode==='fictional_demo'?'演练资料，待本人核对':'本次真实业务底稿'}</span></div>
  <p className="muted">客户卡、人设和长期要求在 WorkBuddy 聊天里维护。这里查看已保存的成果，写稿时接着它们用。</p>
  <div className="brief-grid">{['客群卡','人设卡','四行简介'].map(module=>{const a=data.assets.find(a=>a.module===module);return <article key={module}><h4>{module==='客群卡'?'我主要服务谁':module==='人设卡'?'我是谁、怎么表达':'我的账号简介'}</h4><p>{a?'已有底稿，写作时接着用':'还没读到这项底稿'}</p>{a&&<details><summary>展开看原文</summary><pre>{readable(a)}</pre></details>}</article>})}</div>
  <h4>以后写作要沿用的要求</h4>{data.notes.length?data.notes.map(n=><p className="brief-note" key={n.id}>{n.text}</p>):<p className="muted">在WorkBuddy聊天里说清你的表达习惯和不能公开的内容，保存后继续沿用。</p>}
  <div className="row wrap"><small className="muted">已接入{data.asset_count}份成果 · 最近保存{String(data.updated).slice(0,16).replace('T',' ')}</small><button onClick={()=>{onClose();onSettings?.('business')}}>查看WorkBuddy同步</button></div></>:<p>{message||'正在读取已有底稿…'}</p>}
 </section></div>
}
