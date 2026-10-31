import React,{useEffect,useRef} from 'react';

/** One glance at what to do next. The optional action is the only primary on that strip. */
export function NextStep({title,detail,children}){
 return <aside className="next-step" aria-label="下一步"><div><strong>{title}</strong>{detail?<p>{detail}</p>:null}</div>{children}</aside>
}

/** Feedback stays in view after a click, without covering the form. */
export function ActionNote({text}){
 const ref=useRef(null);
 useEffect(()=>{if(text)ref.current?.scrollIntoView({block:'nearest',behavior:'smooth'})},[text]);
 if(!text)return null;
 return <p ref={ref} className="experience-message" role="status">{text}</p>
}

export const PUBLISH_DECLARATIONS=[
 {id:'douyin',name:'抖音',marks:['内容由AI生成','原创']},
 {id:'tencent',name:'视频号',marks:['含AI生成内容']},
];

/** Locked-on, read-only. The uploader already applies these; students only need to see them. */
export function LockedDeclarations({highlight}){
 return <section className="locked-declarations" aria-label="发布时自动带上的声明">
  <div className="section-title"><h3>发布时会自动标明</h3><span className="lock-tag">已锁定，不用再选</span></div>
  <p className="muted">成片里用了 AI，平台要求如实标明。下面这些会在发布时自动勾上，这里不能关掉。</p>
  <div className="locked-decl-list">{PUBLISH_DECLARATIONS.map(row=><article key={row.id} className={'locked-decl'+(highlight===row.id?' current':'')}>
   <header><strong>{row.name}</strong><span className="lock-tag">自动勾上</span></header>
   {row.marks.map(mark=><label key={mark}><input type="checkbox" checked disabled readOnly tabIndex={-1} aria-label={row.name+'：'+mark} onChange={()=>{}}/><span>{mark}</span></label>)}
  </article>)}</div>
 </section>
}
