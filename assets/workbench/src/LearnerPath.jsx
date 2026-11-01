import React from 'react';
const STEPS=[['methods','蛋解方法'],['student','选题脚本'],['external','外部剪好'],['publish','上传发布'],['connections','账号登录'],['metrics','数据复盘']];
export default function LearnerPath({current,onGo}){
 return <nav className="learner-path" aria-label="这次怎么做">
  <ol>{STEPS.map(([key,label],index)=>{
   const active=current===key;
   const body=<><span>{index+1}</span>{label}</>;
   if(key==='external') return <li key={key}><span className="learner-path-external" title="成片在外部剪好再上传">{body}<small>不在这里剪</small></span></li>;
   return <li key={key}><button type="button" className={active?'active':''} aria-current={active?'step':undefined} onClick={()=>onGo(key)}>{body}</button></li>;
  })}</ol>
  <p>成片在外部剪好再上传。工作台里没有剪辑。</p>
 </nav>;
}
