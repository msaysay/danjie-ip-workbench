(()=>{
 const aid=ASSET_ID,mod=MODULE,titles=CANDIDATES;let restoring=false;
 const text=selector=>document.querySelector(selector)?.textContent.trim()||'';
 function read(){
  let raw=text('#topic')||text('#chosen')||text('[data-k="topic"]')||text('[data-k="question"]')||text('#view .view h2');
  let topic=titles.find(t=>t===raw)||titles.find(t=>raw.includes(t))||'';
  if(!topic)for(const el of document.querySelectorAll('button[aria-pressed="true"],button.active,button.selected')){const candidate=titles.find(t=>el.textContent.includes(t));if(candidate){topic=candidate;break}}
  const cells=[...document.querySelectorAll('.cell[aria-pressed="true"][data-axis]')].map(x=>({axis:Number(x.dataset.axis),index:Number(x.dataset.index)}));
  const controls=[...document.querySelectorAll('button[aria-pressed="true"],button[aria-selected="true"],button.active,button.selected')].slice(0,20).map(el=>({id:el.id||'',label:el.textContent.trim().slice(0,500),data:Object.fromEntries([...el.attributes].filter(a=>/^data-(topic|method|axis|index|scene|interest|question|pick|id|role|b|t)$/.test(a.name)&&/^[\w-]{1,80}$/.test(a.value)).map(a=>[a.name,a.value]))}));
  return {topic,chain:text('#chain')||text('[data-k="chain"]'),cells,controls,center:document.getElementById('centerInput')?.value||'',opening:text('#opening'),method:text('#style')};
 }
 function send(){if(restoring)return;const state=read();parent.postMessage({type:'danjie-method-selection',asset_id:aid,module:mod,title:state.topic,state},'*')}
 document.addEventListener('click',()=>setTimeout(send,40));document.addEventListener('change',()=>setTimeout(send,40));
 window.addEventListener('message',e=>{
  if(e.source===parent&&e.data?.type==='danjie-selection-saved'&&e.data.asset_id===aid){const notice=document.getElementById('notice');if(notice?.textContent.includes('不支持保存状态'))notice.textContent='选择已保存在工作台，点外层“就写这题”后接着写稿。';return}
  if(e.source!==parent||e.data?.type!=='danjie-restore-selection'||e.data.asset_id!==aid)return;
  restoring=true;const st=e.data.state||{};
  if(typeof st.topic==='string'&&titles.includes(st.topic)){
   const initial=[...document.querySelectorAll('button')].find(b=>b.textContent.includes(st.topic));initial?.click();
  }
  if(Array.isArray(st.cells))for(const x of st.cells)if(Number.isInteger(x.axis)&&Number.isInteger(x.index))document.querySelector('.cell[data-axis="'+x.axis+'"][data-index="'+x.index+'"]')?.click();
  if(Array.isArray(st.controls))for(const x of st.controls){if(x.id&&/^[\w-]{1,100}$/.test(x.id)){document.getElementById(x.id)?.click();continue}let selector='button';for(const [k,v] of Object.entries(x.data||{}))if(/^data-[\w-]+$/.test(k)&&/^[\w-]{1,80}$/.test(v))selector+='['+k+'="'+v+'"]';if(selector!=='button')document.querySelector(selector)?.click();else if(typeof x.label==='string'&&x.label.length<=500)[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===x.label)?.click()}
  restoring=false;setTimeout(send,60);
 });
 setTimeout(send,100);
})();
