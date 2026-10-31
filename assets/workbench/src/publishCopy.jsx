import React from 'react';

export const PF={douyin:'抖音',tencent:'视频号'};

export function chars(value){return [...String(value??'')].length}

export function accountState(status){
 return {已验证:'已登录',未验证:'还没登录',需重新验证:'需要重新登录'}[status]||status||'还没登录';
}

export function titleProblem(title){
 const text=String(title||'').trim();
 if(!text)return '还没写';
 if(chars(text)>30)return '超过 30 个字，请改短';
 return '';
}

export function shortTitleProblem(value){
 const text=String(value||'').trim();
 if(!text)return '';
 const count=chars(text);
 if(count<7||count>15)return '要写 7 到 15 个字；不想自己写就清空';
 return '';
}

export function scheduleProblem(schedule){
 if(!schedule)return '';
 const when=new Date(String(schedule).replace(' ','T')+'+08:00');
 if(Number.isNaN(when.getTime()))return '看不懂，请重新选';
 if(when.getTime()<=Date.now()+2*3600*1000)return '要比现在晚至少 2 小时';
 return '';
}

export function publishGaps({hasVideo,selectedIds,accounts,copyFor}){
 const gaps=[];
 if(!hasVideo)gaps.push({id:'video',text:'先上传剪好的视频'});
 if(!selectedIds.length)gaps.push({id:'account',text:'至少选一个要发的账号'});
 const chosen=selectedIds.map(id=>accounts.find(account=>account.id===id)).filter(Boolean);
 for(const account of chosen){
  if(account.status!=='已验证')gaps.push({id:'login:'+account.id,text:'「'+account.label+'」还没登录成功，先扫码再发布'});
 }
 for(const platform of [...new Set(chosen.map(account=>account.platform).filter(key=>PF[key]))]){
  const copy=copyFor(platform)||{};
  const title=titleProblem(copy.title);
  if(title)gaps.push({id:platform+':title',text:PF[platform]+'标题'+title});
  if(platform==='tencent'){
   const short=shortTitleProblem(copy.short_title);
   if(short)gaps.push({id:'short',text:'视频号短标题'+short});
  }
  const when=scheduleProblem(copy.schedule);
  if(when)gaps.push({id:platform+':when',text:PF[platform]+'的发布时间'+when});
 }
 return gaps;
}

function shortHelp(value){
 const text=String(value||'').trim();
 const count=chars(text);
 if(!text)return '留空也能发。发布时会用标题自动做成 7 到 15 个字；标题太短时，会补上「精彩内容分享」里的字。想自己决定，就在这里写满。';
 if(count<7)return '还差 '+(7-count)+' 个字。也可以删空，改用标题自动生成。';
 if(count>15)return '请删到 15 个字以内，或整段清空。';
 return '字数合适，会按你写的发出。';
}

export function PlatformFields({platform,copy,onChange,disabled}){
 const title=copy.title||'';
 const short=copy.short_title||'';
 const titleState=titleProblem(title);
 const shortState=shortTitleProblem(short);
 return <div className="publish-fields-block">
  <ul className="publish-checklist">
   <li className={titleState?'missing':'done'}><span className="need">必填</span><span>标题：观众先看到的一句话，最多 30 个字。抖音和视频号分开写。</span></li>
   {platform==='tencent'&&<li className={shortState?'missing':'optional'}><span className="need optional">可不填</span><span>短标题：视频号上另外一行更短的字。要写就写 7 到 15 个字，留空会用标题自动生成。</span></li>}
   <li className="optional"><span className="need optional">可不填</span><span>视频说明：补充给观众看的话。不写也能发。</span></li>
   <li className="optional"><span className="need optional">可不填</span><span>话题：方便别人搜到。几个词用逗号分开，不写也能发。</span></li>
   <li className={scheduleProblem(copy.schedule)?'missing':'optional'}><span className="need optional">可不填</span><span>发布时间：不选就是确认后马上发。要预约就选北京时间，并且至少比现在晚 2 小时。</span></li>
   <li className="optional"><span className="need optional">可不填</span><span>封面：竖图和横图。没有也能发，有的话列表里更好看。</span></li>
  </ul>
  <fieldset className="publish-copy-fields" disabled={disabled}>
   <label>
    <span className="field-name">标题 <em className="need">必填</em> <small>{chars(title.trim())}/30 字</small></span>
    <input aria-label={PF[platform]+'标题'} aria-required="true" maxLength={30} value={title} onChange={e=>onChange('title',e.target.value)} placeholder="用一句话说明这条视频讲什么"/>
    <small className="field-help">{titleState==='还没写'?'这条还不能发，先写标题。':titleState?titleState:'写给这个平台的观众看。换到另一个平台要再写一遍。'}</small>
   </label>
   {platform==='tencent'&&<label>
    <span className="field-name">短标题 <em className="need optional">可不填</em> <small>{short.trim()?chars(short.trim())+' 字':'留空也可以'}</small></span>
    <input aria-label="视频号短标题" maxLength={15} value={short} onChange={e=>onChange('short_title',e.target.value)} placeholder="7 到 15 个字，不填就用标题自动生成"/>
    <small className="field-help">{shortHelp(short)}</small>
   </label>}
   <label>
    <span className="field-name">视频说明 <em className="need optional">可不填</em></span>
    <textarea aria-label={PF[platform]+'视频说明'} rows={4} value={copy.desc||''} onChange={e=>onChange('desc',e.target.value)} placeholder="想补充的话写在这里，没有就留空"/>
    <small className="field-help">显示在视频下面。不写也能发。</small>
   </label>
   <label>
    <span className="field-name">话题 <em className="need optional">可不填</em></span>
    <input aria-label={PF[platform]+'话题'} value={copy.tags||''} onChange={e=>onChange('tags',e.target.value)} placeholder="例如：老房翻新，报价"/>
    <small className="field-help">别人搜索时能对上的词。多个用逗号分开。不写也能发。</small>
   </label>
  </fieldset>
 </div>;
}

export function PublishReadiness({gaps}){
 if(!gaps.length)return <p className="publish-ready">必填都齐了。下一步只是再看一遍将要发出的内容，输入「确认发布」后才会提交。</p>;
 return <div className="publish-gaps" role="status"><strong>还差这些，才能进入确认发布</strong><ul>{gaps.map(gap=><li key={gap.id}>{gap.text}</li>)}</ul></div>;
}

function coverLine(item){
 const portrait=!!item.cover_files?.cover,landscape=!!item.cover_files?.cover_landscape;
 if(portrait&&landscape)return '带了竖图和横图封面。';
 if(portrait)return '带了竖图封面，没有横图。';
 if(landscape)return '带了横图封面，没有竖图。';
 return '没有带封面。没有封面也会按你确认的文字提交。';
}

export function ConfirmPublishSummary({plan,accounts,projects,fileURL}){
 const project=projects.find(item=>item.id===plan.project);
 return <>
  <p>下面是这次真的会提交给平台的内容。看完后输入「确认发布」，才会发出。</p>
  <p className="muted small">视频文件：{project?.title||'已选成片'}</p>
  {plan.items.map((item,index)=>{
   const account=accounts.find(row=>row.id===item.account_id);
   const name=account?.label||PF[item.platform]+'账号';
   return <div className="batch final-publish-review publish-submit-list" key={index}>
    <strong>发到{PF[item.platform]} · {name}</strong>
    <small className="final-publish-time">{item.schedule?'北京时间 '+item.schedule+' 发出':'你确认后马上发出'}</small>
    <h3>{item.title}</h3>
    {item.platform==='tencent'&&<p>{item.short_title?'短标题：'+item.short_title:'短标题：你没填。发出时会用标题自动做成 7 到 15 个字；标题太短时，会补上「精彩内容分享」里的字。'}</p>}
    <p>{item.desc?.trim()?item.desc:'没有写视频说明。'}</p>
    <p className="muted small">{item.tags?.trim()?'话题：'+item.tags:'没有写话题。'}</p>
    <p className="muted small">{coverLine(item)}</p>
    <div className="final-cover-check">{[['cover','竖封面'],['cover_landscape','横封面']].map(([key,label])=>item.cover_files?.[key]&&<figure key={key}><img src={fileURL(item.cover_files[key])} alt={PF[item.platform]+label}/><figcaption>{label}</figcaption></figure>)}</div>
   </div>;
  })}
 </>;
}
