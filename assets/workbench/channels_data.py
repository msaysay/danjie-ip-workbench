"""Read the owner's visible Channels works using the existing local session.

No publish action, no private endpoint calls, no invented missing counters.
Run with the publisher's isolated Python so its browser runtime stays consistent.

The assistant is a wujie app: /platform/post/list often redirects to the home
shell, 昨日数据 stays in the light DOM, and .post-feed-item lives in
wujie-app.shadowRoot. Playwright's page text and a light-DOM querySelector
therefore see the overview and zero works. Counts and objectId are read from
the Vue post on each card when the page has them, otherwise from the card text.
"""
import asyncio,json,re,sys
from pathlib import Path

from channels_parse import build_result

EXTRACT_JS=r"""() => {
 const seenRoots = new Set();
 function eachRoot(doc, fn) {
  function visit(root) {
   if (!root || seenRoots.has(root)) return;
   seenRoots.add(root);
   fn(root);
   if (!root.querySelectorAll) return;
   for (const el of root.querySelectorAll('*')) if (el.shadowRoot) visit(el.shadowRoot);
  }
  visit(doc);
 }
 function plainNumber(value) {
  if (typeof value === 'boolean' || value == null) return null;
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) return value;
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) return Number(value.trim());
  return null;
 }
 function pick(post, keys) {
  for (const key of keys) {
   if (post && Object.prototype.hasOwnProperty.call(post, key)) {
    const value = plainNumber(post[key]);
    if (value != null) return value;
   }
  }
  return null;
 }
 function vueOn(el) {
  try {
   const vue2 = el.__vue__;
   if (vue2 && vue2.$props && vue2.$props.post) return vue2.$props.post;
  } catch (e) {}
  try {
   const vue3 = el.__vueParentComponent;
   if (vue3 && vue3.props && vue3.props.post) return vue3.props.post;
   if (vue3 && vue3.ctx && vue3.ctx.post) return vue3.ctx.post;
  } catch (e) {}
  return null;
 }
 function plainPost(post) {
  if (!post || typeof post !== 'object') return null;
  const desc = post.desc || {};
  const description = typeof desc.description === 'string' ? desc.description : typeof post.description === 'string' ? post.description : '';
  const objectId = [post.objectId, post.object_id, post.exportId].find(value => typeof value === 'string' && value.trim()) || '';
  return {
   objectId: objectId.trim(),
   description: description.trim(),
   createTime: plainNumber(post.createTime != null ? post.createTime : post.create_time),
   readCount: pick(post, ['readCount', 'read_count', 'playCount']),
   likeCount: pick(post, ['likeCount', 'like_count']),
   commentCount: pick(post, ['commentCount', 'comment_count']),
   forwardCount: pick(post, ['forwardCount', 'forward_count', 'shareCount']),
   favCount: pick(post, ['favCount', 'fav_count', 'favoriteCount', 'collectCount'])
  };
 }
 function findVue(el) {
  const nodes = [el, ...el.querySelectorAll('*')].slice(0, 40);
  for (const node of nodes) {
   const post = plainPost(vueOn(node));
   if (post && (post.objectId || post.description || post.readCount != null)) return post;
  }
  return null;
 }
 function kindOf(el) {
  const cls = typeof el.className === 'string' ? el.className : '';
  if (/(^|\s)post-feed-item(\s|$)/.test(cls)) return 'post-feed-item';
  if (cls.includes('post-list-item')) return 'post-list-item';
  if (/(^|\s)post-feed(\s|$)/.test(cls)) return 'post-feed';
  return 'card';
 }
 function cardFrom(el) {
  const titleNode = el.querySelector('.post-title, .desc-text, .post-desc, .wording');
  const timeNode = el.querySelector('.time-label, .post-time, .publish-time, .create-time');
  const metrics = [...el.querySelectorAll('.data-item, .data-cell, .statistic li')].slice(0, 8).map(node => {
   const count = node.querySelector('.count, .value, em');
   const iconEl = node.querySelector('.icon, i, svg, use');
   const use = node.querySelector('use');
   const icon = [iconEl && iconEl.getAttribute('class'), iconEl && (iconEl.getAttribute('xlink:href') || iconEl.getAttribute('href')), use && (use.getAttribute('xlink:href') || use.getAttribute('href'))].filter(Boolean).join(' ');
   return {text: ((count && count.innerText) || node.innerText || '').trim().slice(0, 80), icon, label: (node.getAttribute('aria-label') || node.getAttribute('title') || '').trim()};
  });
  const link = [...el.querySelectorAll('a[href]')].map(anchor => anchor.href).find(href => /https:\/\/(?:channels\.weixin\.qq\.com|weixin\.qq\.com)\//.test(href)) || null;
  const attrs = {};
  for (const name of ['data-id', 'data-feed-id', 'data-object-id', 'data-export-id']) {
   const value = el.getAttribute(name);
   if (value) attrs[name] = value;
  }
  return {kind: kindOf(el), title: (titleNode && titleNode.innerText || '').trim(), posted_at: (timeNode && timeNode.innerText || '').trim(), text: (el.innerText || '').trim().slice(0, 1500), url: link, attrs, metrics, vue: findVue(el)};
 }
 function collect(root) {
  if (!root.querySelectorAll) return [];
  const strict = [...root.querySelectorAll('.post-feed-item')];
  const nodes = strict.length ? strict : [...root.querySelectorAll('.post-list-item, .post-feed')];
  return nodes.filter(el => !nodes.some(other => other !== el && el.contains(other)));
 }
 const cards = []; const tables = []; const texts = [];
 eachRoot(document, root => {
  for (const el of collect(root)) cards.push(cardFrom(el));
  if (root.querySelectorAll) {
   for (const table of [...root.querySelectorAll('table')].slice(0, 8)) {
    tables.push({headers: [...table.querySelectorAll('thead th')].map(cell => (cell.innerText || '').trim()), rows: [...table.querySelectorAll('tbody tr')].slice(0, 40).map(row => ({cells: [...row.querySelectorAll('td')].map(cell => (cell.innerText || '').trim()), links: [...row.querySelectorAll('a[href]')].map(anchor => ({url: anchor.href, title: (anchor.innerText || '').trim()}))}))});
   }
  }
  if (root.body) texts.push(root.body.innerText || '');
  else texts.push(root.innerText || root.textContent || '');
 });
 return {cards: cards.slice(0, 40), tables, text: texts.join('\n').slice(0, 20000)};
}"""

CLICK_JS=r"""(label) => {
 const seen = new Set();
 const candidates = [];
 function visit(root) {
  if (!root || seen.has(root) || !root.querySelectorAll) return;
  seen.add(root);
  for (const el of root.querySelectorAll('a,button,li,span,div')) {
   const direct = [...el.childNodes].filter(node => node.nodeType === 3).map(node => node.textContent).join('').replace(/\s+/g, ' ').trim();
   const whole = (el.innerText || '').replace(/\s+/g, ' ').trim();
   if (direct === label || whole === label) candidates.push(el);
  }
  for (const el of root.querySelectorAll('*')) if (el.shadowRoot) visit(el.shadowRoot);
 }
 visit(document);
 const visible = candidates.find(el => { const box = el.getClientRects(); return box.length && box[0].width > 0 && box[0].height > 0; });
 const target = visible || candidates[0];
 if (!target) return false;
 (target.closest('a,button,li') || target).click();
 return true;
}"""

def snapshot_ready(snapshot):
 text=snapshot.get('text') or ''
 return bool(snapshot.get('cards')) or any(marker in text for marker in ('暂无作品','暂无内容','还没有发表'))

async def read_snapshot(page):
 cards=[];tables=[];texts=[]
 for frame in list(page.frames):
  try:data=await frame.evaluate(EXTRACT_JS)
  except Exception:continue
  if not isinstance(data,dict):continue
  cards.extend(data.get('cards') or []);tables.extend(data.get('tables') or [])
  if data.get('text'):texts.append(data['text'])
 return {'cards':cards[:40],'tables':tables,'text':'\n'.join(dict.fromkeys(texts))[:20000]}

async def wait_snapshot(page,seconds):
 snapshot=await read_snapshot(page)
 for _ in range(seconds):
  if snapshot_ready(snapshot):return snapshot
  await page.wait_for_timeout(1000)
  snapshot=await read_snapshot(page)
 return snapshot

async def click_label(page,label):
 for frame in list(page.frames):
  try:
   if await frame.evaluate(CLICK_JS,label):return True
  except Exception:continue
 return False

async def main():
 root=Path(__file__).resolve().parent;vendor=root/'vendor/social-auto-upload';sys.path.insert(0,str(vendor))
 from uploader.tencent_uploader.main import async_playwright,_build_launch_kwargs,TENCENT_MANAGE_URL
 from utils.base_social_media import set_init_script
 alias=sys.argv[1]
 cookie=vendor/'cookies'/('tencent_'+alias+'.json')
 if not cookie.is_file():return {'state':'needs_login','message':'先登录视频号，再检查是否能读到作品表现。','items':[]}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(**_build_launch_kwargs(headless=True))
  try:
   ctx=await browser.new_context(storage_state=str(cookie));ctx=await set_init_script(ctx);page=await ctx.new_page()
   await page.goto(TENCENT_MANAGE_URL,wait_until='domcontentloaded',timeout=45000)
   try:await page.wait_for_url('**/login.html**',timeout=8000)
   except Exception:pass
   if 'login' in page.url or any('open.weixin.qq.com/connect/qrconnect' in frame.url for frame in page.frames):
    return {'state':'needs_login','message':'视频号登录已过期，请扫码后重新检查。','items':[]}
   snapshot=await wait_snapshot(page,12)
   if not snapshot_ready(snapshot):
    opened=await click_label(page,'视频')
    if not opened:
     await click_label(page,'内容管理');await page.wait_for_timeout(600);await click_label(page,'视频')
    snapshot=await wait_snapshot(page,8)
   snapshot['source_url']=page.url or TENCENT_MANAGE_URL
   result=build_result(snapshot,alias)
   if result['state'] in ('verified_overview','unverified'):
    evidence=root/'data/platform-evidence/tencent';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'visible-text.txt').write_text(snapshot.get('text') or '',encoding='utf-8')
    summary=[{'kind':card.get('kind'),'title':card.get('title'),'vue':bool(card.get('vue')),'metrics':len(card.get('metrics') or [])} for card in snapshot.get('cards') or []]
    (evidence/'cards.json').write_text(json.dumps({'url':page.url,'cards':summary},ensure_ascii=False,indent=2),encoding='utf-8')
   return result
  finally:await browser.close()

if __name__=='__main__':
 try:result=asyncio.run(main())
 except Exception as e:
  message=re.sub(r'([?&](?:token|key|session|sign|signature|access_token)=)[^&\s]+',r'\1[redacted]',str(e),flags=re.I)
  result={'state':'failed','message':'视频号读取暂未完成：'+type(e).__name__+' '+message[:1600],'items':[]}
 print('WORKBENCH_RESULT='+json.dumps(result,ensure_ascii=False))
