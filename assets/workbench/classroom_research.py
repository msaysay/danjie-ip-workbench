"""Bounded public-source collection through the learner's own TikHub account."""
from pathlib import Path
import base64,ctypes,hashlib,html,json,os,re,math
from datetime import datetime,timezone,timedelta
import requests

REGISTER='https://user.tikhub.io/register?ref=u58I2I4n'
CONSOLE='https://user.tikhub.io/dashboard/api'
DOCS='https://docs.tikhub.io'
GUIDE='https://tikhub.io/zh/getting-started'
SITE='https://tikhub.io/'
API='https://api.tikhub.io'
DEV_PLAIN=b'DANJIE-DEV-PLAINTEXT-v1\n'
def tikhub_links():return {'register_url':REGISTER,'console_url':CONSOLE,'docs_url':DOCS,'guide_url':GUIDE,'site_url':SITE}
def storage_info():
 if __import__('sys').platform=='darwin':return {'storage':'keychain','storage_note':'密钥保存在这台 Mac 的钥匙串里。'}
 if os.name=='nt':return {'storage':'dpapi','storage_note':'密钥用 Windows 账户保护，只留在这台电脑。'}
 return {'storage':'dev_plaintext','storage_note':'这台是 Linux，密钥写在本机文件里，只适合开发调试，不要放在学员电脑上。'}
PLATFORMS={'douyin':'抖音','tencent':'视频号','wechat':'公众号','xiaohongshu':'小红书','kuaishou':'快手','bilibili':'B站','weibo':'微博','zhihu':'知乎'}
SEARCH_PLATFORMS=set(PLATFORMS)
HOT_PLATFORMS=['douyin','weibo','kuaishou','bilibili','zhihu']
ROUTES={
 'douyin_user_search':('POST','/api/v1/douyin/search/fetch_user_search_v2'),
 'douyin_search':('POST','/api/v1/douyin/search/fetch_video_search_v1'),
 'tencent_search':('POST','/api/v1/wechat_search/v2/fetch_search_videos'),
 'wechat_search':('POST','/api/v1/wechat_search/v2/fetch_search'),
 'douyin_account':('GET','/api/v1/douyin/app/v3/fetch_user_post_videos'),
 'tencent_account':('POST','/api/v1/wechat_channels/v2/fetch_user_videos'),
 'wechat_account':('POST','/api/v1/wechat_mp/v2/fetch_account_articles'),
 'douyin_hot':('GET','/api/v1/douyin/app/v3/fetch_hot_search_list'),
 'weibo_hot':('GET','/api/v1/weibo/web_v2/fetch_hot_search'),
 'bilibili_hot':('GET','/api/v1/bilibili/web/fetch_com_popular'),
 'user_info':('GET','/api/v1/tikhub/user/get_user_info'),
 'xiaohongshu_search':('GET','/api/v1/xiaohongshu/app_v2/search_notes'),
 'xiaohongshu_account':('GET','/api/v1/xiaohongshu/app_v2/get_user_posted_notes'),
 'xiaohongshu_user_search':('GET','/api/v1/xiaohongshu/app_v2/search_users'),
 'kuaishou_search':('GET','/api/v1/kuaishou/app/search_video_v2'),
 'kuaishou_account':('GET','/api/v1/kuaishou/app/fetch_user_post_v2'),
 'kuaishou_hot':('GET','/api/v1/kuaishou/web/fetch_kuaishou_hot_list_v2'),
 'bilibili_search':('GET','/api/v1/bilibili/web/fetch_general_search'),
 'bilibili_account':('GET','/api/v1/bilibili/web/fetch_user_post_videos'),
 'weibo_search':('GET','/api/v1/weibo/web_v2/fetch_realtime_search'),
 'weibo_account':('GET','/api/v1/weibo/web_v2/fetch_user_posts'),
 'zhihu_search':('GET','/api/v1/zhihu/web/fetch_article_search_v3'),
 'zhihu_account':('GET','/api/v1/zhihu/web/fetch_user_articles'),
 'zhihu_hot':('GET','/api/v1/zhihu/web/fetch_hot_list'),
}
class Blob(ctypes.Structure):_fields_=[('size',ctypes.c_uint32),('data',ctypes.POINTER(ctypes.c_ubyte))]
def protect(raw,decode=False):
 if __import__('sys').platform=='darwin':
  from platform_secrets import protect_mac
  return protect_mac(raw,decode)
 if os.name!='nt':
  # Development machines only. Learner installs are Windows or Mac and use the branches above.
  if decode:
   if not raw.startswith(DEV_PLAIN):raise ValueError('这台电脑没有系统密钥保护。开发用的明文记录对不上，请重新连接。')
   return raw[len(DEV_PLAIN):]
  return DEV_PLAIN+raw
 source=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw);inp=Blob(len(raw),source);out=Blob()
 crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 fn=crypt.CryptUnprotectData if decode else crypt.CryptProtectData
 args=[ctypes.byref(inp),None,None,None,None,1,ctypes.byref(out)]
 if not fn(*args):raise ValueError('Windows未能保护或读取本机密钥')
 try:return ctypes.string_at(out.data,out.size)
 finally:kernel.LocalFree(out.data)
class TikHub:
 def __init__(self,folder):self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.file=self.folder/'tikhub.dpapi'
 def key(self):return protect(self.file.read_bytes(),True).decode() if self.file.exists() else ''
 def status(self):
  base={**tikhub_links(),**storage_info()}
  try:key=self.key()
  except ValueError:return {**base,'configured':False,'needs_reconnect':True}
  return {**base,'configured':bool(key),'suffix':key[-4:] if key else ''}
 def connect(self,key):
  key=str(key).strip()
  if len(key)<12 or len(key)>500 or any(c.isspace() for c in key):raise ValueError('请粘贴 TikHub 控制台里的完整密钥，中间不要有空格。')
  self.call('user_info',{},key=key)
  self.file.write_bytes(protect(key.encode()));return self.status()
 def call(self,route,payload,key=None):
  key=key or self.key()
  if not key:raise ValueError('先连接你的TikHub账号，再开始查找')
  method,path=ROUTES[route]
  try:
   response=requests.request(method,API+path,headers={'Authorization':'Bearer '+key},json=payload if method=='POST' else None,params=payload if method=='GET' else None,timeout=65)
  except requests.RequestException:raise ValueError('连不上 TikHub。请检查网络后再测一次。为避免重复扣额度，这次不自动重试。') from None
  if not response.ok:
   note=''
   try:
    detail=response.json().get('detail',{})
    if isinstance(detail,dict) and '不会被扣费' in str(detail.get('message_zh','')):note='。TikHub 说明这次不扣费'
   except ValueError:pass
   code=response.status_code
   if code==401:raise ValueError('密钥不对或已经失效。请到 TikHub 控制台重新复制完整密钥，再测一次'+note+'。不会自动重试。')
   if code==402:raise ValueError('TikHub 提示额度不够。请到你的 TikHub 账户查看余额。工作台不代充值'+note+'。不会自动重试。')
   if code==403:raise ValueError('这个密钥还不能调用。请先在 TikHub 验证邮箱，或检查密钥权限'+note+'。不会自动重试。')
   if code==429:raise ValueError('请求太频繁，TikHub 暂时拦住了。请稍后再试一次。不会自动重试。')
   raise ValueError(f'TikHub 这次返回 HTTP {code}，没有取到内容'+note+'。不会自动重试。')
  try:result=json.loads(response.text,parse_int=str)
  except ValueError:raise ValueError('TikHub返回格式无法读取，本次没有导入结果') from None
  if str(result.get('code','200')) not in ['0','200']:raise ValueError('TikHub未返回成功结果，本次没有导入；请检查账户状态')
  if route!='user_info':
   # Short-lived response cache supports adapter repairs without paying again. Windows and Mac encrypt it; Linux development machines use the marked plaintext envelope.
   cache=self.folder.parent/'research-cache';cache.mkdir(exist_ok=True)
   ident=hashlib.sha256(json.dumps([route,payload],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
   raw=json.dumps(result,ensure_ascii=False).replace(key,'[redacted]').encode()
   if len(raw)<=8_000_000:
    (cache/(ident+'.dpapi')).write_bytes(protect(raw))
    (cache/(ident+'.json')).write_text(json.dumps({'route':route,'payload':payload,'stored_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False),encoding='utf-8')
  return result

def validate_config(body):
 industry=str(body.get('industry','')).strip()[:80]
 keywords=body.get('keywords',[])
 if isinstance(keywords,str):keywords=re.split(r'[,，\n]+',keywords)
 keywords=list(dict.fromkeys(str(k).strip() for k in keywords if str(k).strip()))
 if len(keywords)>10 or any(len(k)>100 for k in keywords):raise ValueError('最多关注10个关键词，每个100字内')
 platforms=body.get('platforms',['douyin','tencent','wechat'])
 if not isinstance(platforms,list) or not platforms or any(k not in SEARCH_PLATFORMS for k in platforms):raise ValueError('请至少选择一个支持的平台')
 accounts=[]
 for a in body.get('accounts',[])[:20]:
  if a.get('platform') not in SEARCH_PLATFORMS:raise ValueError('账号平台不支持')
  ident=str(a.get('account_key','')).strip()
  if not ident or len(ident)>256:raise ValueError('请从查询结果关注作者，不能把昵称冒充账号编号')
  accounts.append({'platform':a['platform'],'account_key':ident,'name':str(a.get('name','关注的账号'))[:100]})
 hot=body.get('hot_platforms',['douyin'])
 if not isinstance(hot,list) or any(k not in HOT_PLATFORMS for k in hot):raise ValueError('请选择抖音、微博、快手、B站或知乎热榜')
 try:daily_limit=int(body.get('daily_limit',20));daily_count=int(body.get('daily_count',10))
 except (ValueError,TypeError):raise ValueError('每天条数和查询上限请填整数')
 return {'id':'main','industry':industry,'keywords':keywords,'platforms':list(dict.fromkeys(platforms)),'accounts':accounts,'include_hot':bool(body.get('include_hot',True)),'hot_platforms':list(dict.fromkeys(hot)),'daily_limit':min(60,max(1,daily_limit)),'daily_count':min(30,max(1,daily_count))}
def clean(value):return html.unescape(re.sub('<[^>]+>','',str(value or ''))).strip()
def number(value):
 if isinstance(value,bool):return None
 try:
  text=str(value).strip().replace(',','');scale=10000 if text.endswith('万') else 100000000 if text.endswith('亿') else 1
  if scale!=1:text=text[:-1]
  result=float(text)*scale
  return int(result) if math.isfinite(result) and result.is_integer() else result if math.isfinite(result) else None
 except (ValueError,TypeError):return None
def lists(value):
 if isinstance(value,list):
  for item in value:
   if isinstance(item,dict):yield item
   yield from lists(item)
 elif isinstance(value,dict):
  for key,item in value.items():
   if key not in ['author','user','statistics','video','images','cover','avatar_thumb']:yield from lists(item)
def normalize(payload,platform,kind,query):
 rows={}
 def first(*values):return next((v for v in values if v is not None and v!=''),None)
 def link(value):
  if isinstance(value,dict):value=first(value.get('url_default'),value.get('url'),(value.get('url_list') or [None])[0])
  if isinstance(value,list):value=value[0] if value else ''
  value=str(value or '')
  return 'https:'+value if value.startswith('//') else value if value.startswith(('https://','http://')) else ''
 root=payload.get('data',payload)
 def find_list(value,key):
  if isinstance(value,dict):
   if isinstance(value.get(key),list):return value[key]
   for v in value.values():
    found=find_list(v,key)
    if found is not None:return found
  return None
 specific=None
 if kind=='hot':
  if platform=='douyin':specific=find_list(root,'word_list')
  if platform=='weibo':specific=find_list(root,'realtime')
  if platform=='kuaishou':specific=find_list(root,'hots')
  if platform=='bilibili':specific=find_list(root,'list')
  if platform=='zhihu':specific=find_list(root,'data')
 else:
  if platform in ['wechat','tencent','xiaohongshu']:specific=find_list(root,'notes' if platform=='xiaohongshu' and kind=='account' else 'items')
  if platform=='kuaishou':specific=find_list(root,'mixFeeds')
  if platform=='bilibili':specific=find_list(root,'result') if kind=='keyword' else find_list(root,'vlist')
  if platform=='weibo':specific=find_list(root,'results')
  if platform=='zhihu':specific=find_list(root,'data')
 for wrapper in specific if specific is not None else lists(root):
  item=wrapper
  if not isinstance(item,dict):continue
  for key in ['aweme_info','note_card','note','mblog','target','object','feed']:
   if isinstance(item.get(key),dict):item={**item,**item[key]}
  if isinstance(item.get('photo'),dict):item={**item,**item['photo']}
  title=clean(first(item.get('title'),item.get('display_title'),item.get('displayTitle'),item.get('caption'),item.get('desc') if platform in ['douyin','xiaohongshu'] else None,item.get('text_raw'),item.get('text'),item.get('content') if platform=='weibo' else None,item.get('word'),item.get('keyword') if kind=='hot' else None,item.get('name') if kind=='hot' else None,(item.get('question') or {}).get('title'),item.get('content_desc'),item.get('note') if kind=='hot' and isinstance(item.get('note'),str) else None,item.get('id') if kind=='hot' and platform=='kuaishou' and not str(item.get('id','')).isdigit() else None))
  ident=first(item.get('aweme_id'),item.get('note_id'),item.get('noteId'),item.get('exportId'),item.get('export_id'),item.get('object_id'),item.get('docID'),item.get('bvid'),item.get('photoId'),item.get('photo_id'),item.get('weibo_id'),item.get('id'))
  share=item.get('share_info') or {};share=share if isinstance(share,dict) else {}
  url=link(first(item.get('share_url'),share.get('shareUrl'),share.get('share_url'),item.get('url'),item.get('content_url'),item.get('article_url'),item.get('doc_url'),item.get('post_url'),item.get('target_url'),item.get('arcurl')))
  if not title or len(title)<2 or (not ident and not url and kind!='hot'):continue
  author=first(item.get('author'),item.get('user'),item.get('owner'),{})
  if not isinstance(author,dict):author={'name':author}
  jump=item.get('jumpInfo') or {};stats={**(item.get('statistics') or item.get('stat') or {}),**(item.get('interact_info') or {}),**(item.get('interaction') or {})}
  source=item.get('source') or {};source=source if isinstance(source,dict) else {}
  name=clean(first(author.get('nickname'),author.get('screen_name'),author.get('name'),jump.get('nickName'),item.get('nickname'),item.get('author_name'),item.get('user_nick'),item.get('user_name'),source.get('title')))
  account=first(author.get('sec_uid'),author.get('username'),author.get('user_name'),jump.get('userName'),item.get('username'))
  if platform=='xiaohongshu':account=first(author.get('user_id'),author.get('userid'),author.get('id'),account)
  if platform=='kuaishou':account=first(author.get('user_id'),author.get('id'),item.get('userId'),item.get('user_id'),account)
  if platform=='bilibili':account=first(author.get('mid'),item.get('mid'),account)
  if platform=='weibo':
   uid=re.match(r'(?://|https?://)(?:www\.)?weibo\.com/(?:u/)?(\d+)',str(item.get('user_url') or ''))
   account=first(author.get('idstr'),author.get('id'),uid.group(1) if uid else None,account)
  if platform=='zhihu':account=first(author.get('url_token'),account)
  if platform=='xiaohongshu' and not url and ident:url='https://www.xiaohongshu.com/explore/'+str(ident)
  if platform=='douyin' and kind=='hot' and item.get('sentence_id'):url='https://www.douyin.com/hot/'+str(item['sentence_id'])
  if platform=='weibo' and kind=='hot':
   from urllib.parse import quote
   url='https://s.weibo.com/weibo?q='+quote(title)
  if platform=='zhihu' and url.startswith('https://api.zhihu.com/'):
   qid=(item.get('question') or {}).get('id')
   if item.get('type')=='answer' and qid:url='https://www.zhihu.com/question/'+str(qid)+'/answer/'+str(ident)
   elif item.get('type')=='article':url='https://zhuanlan.zhihu.com/p/'+str(ident)
   elif item.get('type')=='question':url='https://www.zhihu.com/question/'+str(ident)
  if platform=='douyin' and kind!='hot' and str(ident).isdigit():url='https://www.douyin.com/video/'+str(ident)
  if platform=='wechat' and url.startswith('http://mp.weixin.qq.com/'):url='https://'+url[len('http://'):]
  if not url and platform=='bilibili' and str(ident).startswith('BV'):url='https://www.bilibili.com/video/'+str(ident)
  if not url and platform=='weibo' and item.get('bid'):url='https://weibo.com/'+str(account or '0')+'/'+str(item['bid'])
  key=hashlib.sha256((platform+'|'+str(ident or url or title)).encode()).hexdigest()[:24]
  images=item.get('images_list') or [];first_image=images[0] if images and isinstance(images[0],dict) else {}
  row={'id':key,'content_id':str(ident or ''),'platform':platform,'kind':kind,'title':title[:1200],'url':url,'author':name,'account_key':str(account or ''),'query':query,'published_at':str(first(item.get('create_time'),item.get('publish_time'),item.get('publishTime'),item.get('pubdate'),item.get('timestamp'),item.get('pubTime'),item.get('dateTime'),item.get('created_time'),item.get('created'),item.get('time'),item.get('created_at')) or ''),'likes':number(first(stats.get('digg_count'),stats.get('liked_count'),stats.get('like'),item.get('liked_count'),item.get('like_count'),item.get('likeCount'),item.get('likeNum'),item.get('likedCount'),item.get('attitudes_count'),item.get('voteup_count'))),'views':number(first(stats.get('play_count'),stats.get('view'),item.get('read_count'),item.get('view_count'),item.get('viewCount'),item.get('play'))),'comments':number(first(stats.get('comment_count'),stats.get('comment'),item.get('comment_count'),item.get('comments_count'))),'shares':number(first(stats.get('share_count'),stats.get('repost'),item.get('share_count'),item.get('shared_count'),item.get('reposts_count'))),'saves':number(first(stats.get('collected_count'),stats.get('collect_count'),item.get('collect_count'),item.get('collected_count'))),'cover_url':link(first(item.get('cover'),item.get('coverUrl'),item.get('pic'),item.get('image'),item.get('thumbUrl'),first_image.get('url'),(item.get('cover_thumbnail_urls') or [None])[0],(item.get('video') or {}).get('cover'))),'rank':number(first(item.get('position'),item.get('realpos'),item.get('rank'))),'heat':number(first(item.get('hot_value'),item.get('hotValue'),item.get('raw_hot'),item.get('heat'),item.get('hot'),item.get('num'))),'normalization_version':2,'provenance':'TikHub公开内容；不是本人经营后台数据'}
  if kind=='hot' and row['rank'] is None:row['rank']=len(rows)+1
  if kind=='hot' and platform=='douyin' and str(item.get('word_type'))=='14' and item.get('position') is None:row['rank']=0;row['heat']=None
  if platform=='xiaohongshu':
   row['likes']=number(first(item.get('likes'),item.get('liked_count'),row['likes']))
   # Public notes do not expose a trustworthy view count; a returned 0 is not verified audience data.
   row['views']=None
  if platform=='douyin' and row['views']==0 and any((row.get(k) or 0)>0 for k in ['likes','comments','shares']):row['views']=None
  row['normalization_version']=3
  row['is_promoted']=str(item.get('is_ad','')).lower() in ['1','true']
  if key not in rows or sum(v is not None and v!='' for v in row.values())>sum(v is not None and v!='' for v in rows[key].values()):rows[key]=row
 return list(rows.values())[:50]

def ranked_board(items,platform,limit=10):
 rows=[x for x in items if x['platform']==platform and x['kind']=='hot']
 if not rows:return []
 newest=max(rows,key=lambda x:x.get('collected_at',''));batch=newest.get('batch_id') or newest.get('run_id')
 rows=[x for x in rows if (x.get('batch_id') or x.get('run_id'))==batch and not x.get('is_promoted')]
 rows.sort(key=lambda x:x.get('rank') if x.get('rank') is not None else 999)
 result=[];seen=set()
 for row in rows:
  if row['title'] in seen:continue
  result.append(row);seen.add(row['title'])
  if len(result)>=limit:break
 return result
def plan(config,kind='all',day=None):
 if kind not in ['all','keyword','account','hot']:raise ValueError('请选择精选、账号动态或热榜')
 queries=config['keywords'] or ([config['industry']] if config['industry'] else [])
 if queries:
  ordinal=(day or datetime.now(timezone(timedelta(hours=8))).date()).toordinal();offset=ordinal%len(queries);queries=queries[offset:]+queries[:offset]
 calls=[]
 for query in queries:
  for platform in config['platforms']:
   payload={'keyword':query}
   if platform=='douyin':payload.update(cursor=0,sort_type='1',publish_time='7',filter_duration='0',content_type='1',search_id='',backtrace='')
   elif platform in ['tencent','wechat']:
    payload.update(raw=False,sort='hot',publish_time='week',offset=0)
    if platform=='wechat':payload['business_type']='article'
   elif platform=='xiaohongshu':payload.update(page=1,sort_type='popularity_descending',time_filter='一周内')
   elif platform=='bilibili':payload.update(order='click',page=1,page_size=20)
   elif platform=='weibo':payload={'query':query,'page':1}
   elif platform=='zhihu':payload.update(offset='0',limit='20',sort='upvoted_count')
   calls.append((platform+'_search',payload,platform,'keyword',query))
 for account in config['accounts']:
  p=account['platform'];ident=account['account_key'];payload={'sec_user_id':ident,'count':10,'max_cursor':0} if p=='douyin' else {'username':ident,'raw':False}
  if p in ['xiaohongshu','kuaishou']:payload={'user_id':ident}
  if p in ['bilibili','weibo']:payload={'uid':ident}
  if p=='zhihu':payload={'user_url_token':ident,'limit':'20'}
  calls.append((p+'_account',payload,p,'account',account['name']))
 hot_calls=[(platform+'_hot',{},platform,'hot',PLATFORMS[platform]+'热榜') for platform in config.get('hot_platforms',['douyin'])] if config['include_hot'] else []
 first=calls[:len(config['platforms'])] if queries else []
 rest=calls[len(first):];accounts=[c for c in rest if c[3]=='account'];extra=[c for c in rest if c[3]!='account']
 planned=first+hot_calls+accounts+extra
 return [c for c in planned if kind=='all' or c[3]==kind][:config['daily_limit']]

def published_time(value):
 try:
  if str(value).replace('.','',1).isdigit():return datetime.fromtimestamp(float(value)/(1000 if len(str(value).split('.')[0])>11 else 1),timezone.utc)
  from email.utils import parsedate_to_datetime
  try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).replace(tzinfo=timezone.utc) if '+' not in str(value) and 'Z' not in str(value) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
  except ValueError:return parsedate_to_datetime(str(value))
 except (ValueError,TypeError,OverflowError):return None

def curate(rows,config,day,limit=None):
 """Ten useful references across platforms, never a claim of proven commercial quality."""
 by_platform={};now=datetime.now(timezone.utc);zone=timezone(timedelta(hours=8));requested=datetime.strptime(day,'%Y-%m-%d').replace(hour=23,minute=59,second=59,tzinfo=zone)
 if requested.date()<now.astimezone(zone).date():now=requested
 for row in rows:
  if row.get('kind')!='keyword' or row.get('collected_day',str(row.get('collected_at',''))[:10])!=day or row.get('platform') not in config['platforms']:continue
  text=(row['title']+' '+row.get('query','')).lower();matches=[w for w in config['keywords'] if w.lower() in row['title'].lower()]
  # Search query provenance gives relevance context, but is weaker than a title match.
  if row.get('query') not in config['keywords'] and not matches:continue
  when=published_time(row.get('published_at'));age=(now-when).total_seconds()/86400 if when else None
  if age is not None and (age< -1 or age>30):continue
  engagement=sum(max(0,row.get(k) or 0) for k in ['likes','comments','shares','saves'])
  score=20*len(matches)+(8 if row.get('query') in config['keywords'] else 0)+max(0,7-(age if age is not None else 7))+min(12,math.log1p(engagement))
  reason=('标题提到'+ '、'.join(matches) if matches else '平台按“'+row.get('query','')+'”查回，相关性待核对')+('；近7天发布' if age is not None and age<=7 else '；发布时间待核对' if age is None else '；近30天发布')+('；有公开互动可回看' if engagement else '；互动字段不全，先看内容')
  by_platform.setdefault(row['platform'],[]).append({**row,'selection_score':round(score,2),'selection_reason':reason})
 for batch in by_platform.values():batch.sort(key=lambda x:x['selection_score'],reverse=True)
 selected=[];seen=set();cap=limit or config.get('daily_count',10)
 while len(selected)<cap and any(by_platform.values()):
  for p in config['platforms']:
   batch=by_platform.get(p,[])
   if not batch:continue
   row=batch.pop(0)
   if row['id'] not in seen:selected.append(row);seen.add(row['id'])
   if len(selected)>=cap:break
 return selected
