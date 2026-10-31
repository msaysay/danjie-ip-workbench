export const HANDOFF_SCHEMA='danjie-content-handoff/1';
const text=(v,label,max=20000)=>{if(typeof v!=='string'||!v.trim()||v.length>max)throw Error(`${label}需填写文字，且不超过 ${max} 字`);return v.trim()};
export function parseHandoff(raw){
 if(typeof raw!=='string'||new TextEncoder().encode(raw).length>2*1024*1024)throw Error('交接文件需小于 2 MB');
 let x;try{x=JSON.parse(raw)}catch{throw Error('无法读取 JSON，请上传 WorkBuddy 生成的交接.json，不是原始 Skill ZIP')}
 if(x?.schema!==HANDOFF_SCHEMA)throw Error('交接格式不符，请让 WorkBuddy 按随包交接模板生成');
 if(!['real','fictional_demo'].includes(x.mode))throw Error('请明确真实材料或虚构演示');
 const delivery_id=text(x.delivery_id,'交接编号',80);
 if(!/^[a-zA-Z0-9_-]+$/.test(delivery_id))throw Error('交接编号请使用字母、数字、短横线');
 const title=text(x.title,'标题',200),audience=text(x.audience,'目标客群',3000),topic=text(x.topic,'已选题目',1000),script=text(x.script,'脚本');
 if(!Array.isArray(x.gaps)||x.gaps.some(v=>typeof v!=='string'))throw Error('gaps 请填写缺证项数组，没有则为 []');
 if(!Array.isArray(x.sources)||!x.sources.length)throw Error('至少保留一个本次材料来源');
 const sources=x.sources.map(v=>({file:text(v.file,'来源文件',500),role:text(v.role,'来源用途',500),nature:text(v.nature,'资料性质',120)}));
 if(x.mode==='real'&&sources.some(s=>s.nature==='fictional_demo'||s.nature==='simulation'))throw Error('模拟来源不能导入为真实材料');
 const platform_copy={};for(const k of ['douyin','tencent']){const v=x.platform_copy?.[k];if(v){platform_copy[k]={title:text(v.title,'平台标题',100),desc:typeof v.desc==='string'?v.desc.slice(0,5000):'',tags:typeof v.tags==='string'?v.tags.slice(0,500):'',schedule:''}}}
 const shots=Array.isArray(x.shots)?x.shots.map(v=>({spoken:text(v.spoken,'镜头口播',5000),visual:text(v.visual,'画面建议',3000)})):[];
 const questions=Array.isArray(x.topics)?x.topics.filter(v=>typeof v==='string').slice(0,100):[];
 return {schema:HANDOFF_SCHEMA,delivery_id,mode:x.mode,title,audience,topic,script,sources,gaps:x.gaps.slice(0,100),platform_copy,shots,topics:questions,owner_review:'pending'};
}
export function projectPayload(x){
 const demo=x.mode==='fictional_demo';
 const brief=[`[danjie-delivery:${x.delivery_id}]`,demo?'【虚构示例，仅供演示，不用于真实业绩或公开发布】':'【本人尚未验收的草稿】',`目标客群：${x.audience}`,`已选题目：${x.topic}`,'本人审稿：待确认；导入不代表内容获准发布。','材料来源：',...x.sources.map(s=>`- ${s.file}｜${s.role}｜${s.nature}`),'待补与拍前核对：',...(x.gaps.length?x.gaps.map(s=>'- '+s):['- 本人核对事实、语气、公开范围与取用材料。']),'镜头建议：',...x.shots.map((s,i)=>`${i+1}. ${s.spoken}\n画面：${s.visual}`)].join('\n');
 const prefix=demo?'【模拟】':'';
 return {title:prefix+x.title,brief,script:(demo?'【虚构示例，仅供演示】\n\n':'')+x.script,status:'脚本',platform_copy:Object.fromEntries(Object.entries(x.platform_copy).map(([k,v])=>[k,{...v,title:prefix+v.title,desc:(demo?'【虚构示例，仅供演示】\n':'')+v.desc}]))};
}
