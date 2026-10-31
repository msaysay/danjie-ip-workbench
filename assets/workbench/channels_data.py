"""Read the owner's visible Channels work table using the existing local session.

No publish action, no private endpoint spoofing, no invented missing counters.
Run with the publisher's isolated Python so its browser runtime stays consistent.
"""
import asyncio,json,re,sys,hashlib
from pathlib import Path

async def main():
 root=Path(__file__).resolve().parent;vendor=root/'vendor/social-auto-upload';sys.path.insert(0,str(vendor))
 from uploader.tencent_uploader.main import async_playwright,_build_launch_kwargs,TENCENT_MANAGE_URL
 from utils.base_social_media import set_init_script
 cookie=vendor/'cookies'/('tencent_'+sys.argv[1]+'.json')
 if not cookie.is_file():return {'state':'needs_login','message':'先登录视频号，再检查是否能读到作品表现。','items':[]}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(**_build_launch_kwargs(headless=True))
  try:
   ctx=await browser.new_context(storage_state=str(cookie));ctx=await set_init_script(ctx);page=await ctx.new_page();await page.goto(TENCENT_MANAGE_URL,wait_until='domcontentloaded',timeout=45000)
   try:await page.wait_for_url('**/login.html**',timeout=8000)
   except Exception:pass
   if 'login' in page.url or any('open.weixin.qq.com/connect/qrconnect' in f.url for f in page.frames):return {'state':'needs_login','message':'视频号登录已过期，请扫码后重新检查。','items':[]}
   initial='\n'.join(dict.fromkeys(await page.locator('body').all_inner_texts()))
   overview={}
   if '昨日数据' in initial:
    for field,label in [('new_views','新增播放'),('net_followers','净增关注'),('new_comments','新增评论')]:
     match=re.search(re.escape(label)+r'\s*([\d,]+)',initial)
     if match:overview[field]=int(match[1].replace(',',''))
   # Some account sessions redirect a deep link to the home page on first load.
   # Use the platform's visible Video menu to enter content management.
   if '昨日数据' in initial:
    target=page.locator('li.finder-ui-desktop-sub-menu__item:visible').filter(has_text=re.compile(r'^\s*视频\s*$')).first
    if await target.count():
     await target.click()
     try:await page.wait_for_load_state('networkidle',timeout=12000)
     except Exception:pass
   try:await page.locator('table').first.wait_for(state='visible',timeout=15000)
   except Exception:pass
   tables=await page.locator('table').evaluate_all('(tables)=>tables.map(t=>({headers:[...t.querySelectorAll("thead th")].map(x=>x.innerText.trim()),rows:[...t.querySelectorAll("tbody tr")].map(r=>({cells:[...r.querySelectorAll("td")].map(c=>c.innerText.trim()),links:[...r.querySelectorAll("a[href]")].map(a=>({url:a.href,title:a.innerText.trim()}))}))}))')
   items=[]
   fields={'views':['播放量','播放次数','播放'],'likes':['点赞数','点赞'],'comments':['评论数','评论'],'shares':['转发数','转发','分享'],'saves':['收藏数','收藏']}
   def num(s):
    s=str(s).strip().replace(',','')
    if not re.fullmatch(r'\d+(?:\.\d+)?[万亿]?',s):return None
    return int(float(s.rstrip('万亿'))*(10000 if s.endswith('万') else 100000000 if s.endswith('亿') else 1))
   for table in tables:
    indices={k:next((i for i,h in enumerate(table['headers']) if h in names),None) for k,names in fields.items()}
    if not any(i is not None for i in indices.values()):continue
    for row in table['rows']:
     link=next((a for a in row['links'] if a['url'].startswith('https://channels.weixin.qq.com/') and re.search(r'(?:feedid|objectId|object_id|id)=',a['url'])),None)
     if not link:continue
     ident=re.search(r'(?:feedid|objectId|object_id|id)=([^&#]+)',link['url'])[1]
     items.append({'post_id':ident,'title':link['title'] or row['cells'][0],'url':link['url'],**{k:num(row['cells'][i]) if i is not None and i<len(row['cells']) else None for k,i in indices.items()}})
   if items:return {'state':'verified','message':'已从本人视频号作品表读到实际记录。','items':items,'source_url':TENCENT_MANAGE_URL,'scope':'lifetime','overview':overview}
   text='\n'.join(dict.fromkeys(await page.locator('body').all_inner_texts()))
   evidence=root/'data/platform-evidence/tencent';evidence.mkdir(parents=True,exist_ok=True)
   (evidence/'visible-text.txt').write_text(text,encoding='utf-8')
   structure=await page.locator('body').evaluate_all('(bodies)=>bodies.flatMap((body,i)=>[...body.querySelectorAll("[class]")].filter(e=>typeof e.className==="string"&&/list|table|card|item|data|count/.test(e.className)).map(e=>({body:i,tag:e.tagName,cls:e.className,text:e.innerText?.slice(0,1800)})).filter(e=>e.text).slice(0,180))')
   (evidence/'visible-structure.json').write_text(json.dumps(structure,ensure_ascii=False,indent=2),encoding='utf-8')
   cards=await page.locator('.post-feed-item').evaluate_all('(cards)=>cards.slice(0,20).map(c=>({title:c.querySelector(".post-title")?.innerText||"",posted_at:c.querySelector(".time-label")?.innerText||"",metrics:[...c.querySelectorAll(".data-item")].map(d=>({text:d.querySelector(".count")?.innerText||"",icon:d.querySelector(".icon")?.getAttribute("class")||"",use:d.querySelector("use")?.getAttribute("xlink:href")||""}))}))')
   (evidence/'cards.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2),encoding='utf-8')
   if await page.locator('.post-feed-item').count():await page.locator('.post-feed-item').first.screenshot(path=str(evidence/'first-work.png'))
   for card in cards:
    if not card['title'] or not card['posted_at']:continue
    counters={'views':None,'likes':None,'comments':None,'shares':None,'saves':None}
    for item in card['metrics']:
     icon=item['icon']+' '+item['use'];field=next((field for key,field in [('outlined-eyes-on','views'),('outlined-like','likes'),('outlined-comment','comments'),('#icon-share','shares')] if key in icon),None)
     if field:counters[field]=num(item['text'])
    if not any(v is not None for v in counters.values()):continue
    ident='local:'+hashlib.sha256((sys.argv[1]+'\n'+card['title']+'\n'+card['posted_at']).encode()).hexdigest()
    items.append({'post_id':ident,'identity_source':'local_title_and_publish_time','title':card['title'],'published_text':card['posted_at'],'url':None,**counters})
   if items:return {'state':'verified','message':f'已读到本人视频号当前页{len(items)}条作品表现与昨日账号数据；不代表全部历史作品。','items':items,'overview':overview,'source_url':TENCENT_MANAGE_URL,'scope':'lifetime','coverage':'visible_page_only'}
   if '暂无内容' in text or '暂无作品' in text:return {'state':'verified_empty','message':'已进入本人后台，平台显示暂无作品。','items':[],'source_url':TENCENT_MANAGE_URL}
   if overview:return {'state':'verified_overview','message':'已读到本人视频号的昨日账号数据；逐条作品明细仍待适配。','items':[],'overview':overview,'source_url':TENCENT_MANAGE_URL}
   return {'state':'unverified','message':'页面已打开，但尚未识别到带作品编号的真实数据表；没有写入空值或虚构数字。','items':[],'source_url':TENCENT_MANAGE_URL}
  finally:await browser.close()

if __name__=='__main__':
 try:result=asyncio.run(main())
 except Exception as e:
  message=re.sub(r'([?&](?:token|key|session|sign|signature|access_token)=)[^&\s]+',r'\1[redacted]',str(e),flags=re.I)
  result={'state':'failed','message':'视频号读取暂未完成：'+type(e).__name__+' '+message[:1600],'items':[]}
 print('WORKBENCH_RESULT='+json.dumps(result,ensure_ascii=False))
