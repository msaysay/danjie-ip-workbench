/** Read-only helpers for the inspiration feed. They only use fields already on each item. */

export function engagement(row){
 const keys=['likes','comments','shares','saves'];
 if(!keys.some(key=>typeof row?.[key]==='number'))return null;
 return keys.reduce((sum,key)=>sum+(typeof row[key]==='number'?row[key]:0),0);
}

export function whyRecommend(row){
 if(row?.selection_reason)return row.selection_reason;
 if(row?.kind==='account')return '来自你关注的作者。先看它回答了客户什么问题。';
 if(row?.kind==='hot')return '来自这次热榜返回的顺序。热度不跟别的平台比。';
 return '按你保存的关键词查回。先看标题是否贴着客户的问题。';
}

export function scanSummary(feed){
 const items=[...(feed?.keyword_items||[]),...(feed?.account_items||[]),...(feed?.boards||[]).flatMap(board=>board.items||[])];
 const seen=new Set();
 const unique=[];
 for(const item of items){
  const id=item?.id||`${item?.platform||''}:${item?.title||''}`;
  if(seen.has(id))continue;
  seen.add(id);
  unique.push(item);
 }
 const platforms=[...new Set(unique.map(item=>item.platform).filter(Boolean))];
 const topics=[...new Set(unique.map(item=>item.query).filter(Boolean))];
 const positive=unique.map(item=>engagement(item)).filter(value=>typeof value==='number'&&value>0).sort((a,b)=>a-b);
 let highEngagement=0;
 let engagementNote='这次没有返回互动数字';
 if(positive.length){
  const mid=positive[Math.floor((positive.length-1)/2)];
  highEngagement=positive.filter(value=>value>=mid).length;
  engagementNote='按本次查回的赞、评、藏、转发合计，不低于这批的中位数。不跨平台比播放。';
 }else if(unique.some(item=>engagement(item)===0)){
  engagementNote='返回的互动数字都是 0';
 }
 return {items:unique.length,platformCount:platforms.length,platforms,topicCount:topics.length,highEngagement,engagementNote};
}
