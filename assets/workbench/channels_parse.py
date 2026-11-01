"""Turn a 视频号助手 page snapshot into work items.

The assistant renders 内容管理 / 首页近期作品 inside an open shadow root on
wujie-app (see channels_data.py). Counts and the opaque object id are often on
the Vue post object, while the card text is description, publish time, then
播放 / 点赞 / 评论 / 转发 / 收藏. This module only copies numbers that are
actually present.
"""
import hashlib,re
from datetime import datetime,timedelta,timezone
from html.parser import HTMLParser
from urllib.parse import unquote

FIELDS=('views','likes','comments','shares','saves')
ZONE=timezone(timedelta(hours=8))
STATUS={'已发表','审核中','仅自己可见','公开','好友可见','转码中','已删除','审核不通过','定时发表'}
TIME_RE=re.compile(r'(?:\d{4}年)?\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}')
LABELS=(('播放量','views'),('播放次数','views'),('播放','views'),('点赞数','likes'),('点赞','likes'),('评论数','comments'),('评论','comments'),('转发数','shares'),('转发','shares'),('分享数','shares'),('分享','shares'),('收藏数','saves'),('收藏','saves'))
VUE_FIELDS=(('readCount','views'),('likeCount','likes'),('commentCount','comments'),('forwardCount','shares'),('favCount','saves'))
VOID={'area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr'}
BLOCK={'div','p','li','tr','h1','h2','h3','h4','section','article','br','ul','ol','table','header','footer'}

def num(value):
 s=str(value).strip().replace(',','').replace('，','')
 if not re.fullmatch(r'\d+(?:\.\d+)?[万亿]?',s):return None
 return int(float(s.rstrip('万亿'))*(10000 if s.endswith('万') else 100000000 if s.endswith('亿') else 1))

def first_number(text):
 match=re.search(r'[\d,，]+(?:\.\d+)?[万亿]?',str(text or ''))
 return num(match.group(0)) if match else None

def field_from_icon(icon):
 s=str(icon or '').lower()
 if any(key in s for key in ('eyes','eye-on','outlined-play','icon-play','browse')):return 'views'
 if any(key in s for key in ('like','thumb')):return 'likes'
 if 'comment' in s:return 'comments'
 if any(key in s for key in ('share','forward')):return 'shares'
 if any(key in s for key in ('star','fav','collect','bookmark')):return 'saves'
 return None

def field_from_label(text):
 raw=str(text or '')
 for label,field in LABELS:
  if label in raw:return field
 return None

def clean_title(text):
 text=re.sub(r'\s+',' ',str(text or '')).strip()
 if not text or text in STATUS or TIME_RE.fullmatch(text) or num(text) is not None:return ''
 return text[:500]

def usable_id(value):
 value=unquote(str(value or '')).strip()
 if not 6<=len(value)<=400 or any(ch.isspace() for ch in value):return ''
 if value.lower() in {'undefined','null','true','false'}:return ''
 return value

def iso_from_unix(value):
 try:number=float(value)
 except (TypeError,ValueError):return None
 if number>10**12:number/=1000
 if not 10**9<=number<=10**11:return None
 return datetime.fromtimestamp(number,ZONE).replace(microsecond=0).isoformat()

def iso_from_text(text):
 match=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})',str(text or ''))
 if not match:match=re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})',str(text or ''))
 if not match:return None
 try:return datetime(*map(int,match.groups()),tzinfo=ZONE).isoformat()
 except ValueError:return None

def pieces(text):
 raw=[re.sub(r'\s+',' ',line).strip() for line in str(text or '').splitlines()]
 raw=[line for line in raw if line]
 out=[]
 for line in raw:
  match=TIME_RE.search(line)
  if not match:
   out.append(line);continue
  before,after=line[:match.start()].strip(),line[match.end():].strip()
  if before:out.append(before)
  out.append(match.group(0))
  if after:out.append(after)
 return out

def metrics_from_text(text):
 parts=pieces(text)
 time_at=next((i for i,part in enumerate(parts) if TIME_RE.fullmatch(part)),None)
 title='';posted='';region=parts
 if time_at is not None:
  posted=parts[time_at]
  before=[part for part in parts[:time_at] if part not in STATUS and num(part) is None]
  title=before[0] if before else ''
  region=parts[time_at+1:]
 labeled=[];bare=[]
 label_re=re.compile(r'(播放量|播放次数|播放|点赞数|点赞|评论数|评论|转发数|转发|分享数|分享|收藏数|收藏)\s*[:：]?\s*([\d,，]+(?:\.\d+)?[万亿]?)')
 for part in region:
  if part in STATUS:continue
  found=label_re.findall(part)
  if found:
   labeled.extend(found);continue
  if re.fullmatch(r'(?:[\d,，]+(?:\.\d+)?[万亿]?\s*)+',part):
   bare.extend(re.findall(r'[\d,，]+(?:\.\d+)?[万亿]?',part))
 return clean_title(title),posted,labeled,bare

def blank_counts():return {key:None for key in FIELDS}

def apply_labeled(counters,metrics,labeled):
 for item in metrics or []:
  field=field_from_icon(item.get('icon')) or field_from_label(item.get('label')) or field_from_label(item.get('text'))
  value=first_number(item.get('text'))
  if field and value is not None and counters[field] is None:counters[field]=value
 for label,token in labeled:
  field=field_from_label(label);value=num(token)
  if field and value is not None and counters[field] is None:counters[field]=value

def fill_counts(vue,metrics,text,allow_positional):
 counters=blank_counts();vue_used=False
 for source,field in VUE_FIELDS:
  value=(vue or {}).get(source)
  if isinstance(value,(int,float)) and not isinstance(value,bool) and value>=0:
   counters[field]=int(value);vue_used=True
 _,_,labeled,bare=metrics_from_text(text)
 apply_labeled(counters,metrics,labeled)
 if allow_positional and not vue_used and all(value is None for value in counters.values()) and len(bare)==5:
  for field,token in zip(FIELDS,bare):
   value=num(token)
   if value is not None:counters[field]=value
 return counters

def link_id(url):
 if not url or not re.search(r'https://(?:channels\.weixin\.qq\.com|weixin\.qq\.com)/',url):return ''
 match=re.search(r'(?:feedid|objectId|object_id|id)=([^&#]+)',url)
 if match:return usable_id(match.group(1))
 match=re.search(r'/sph/([A-Za-z0-9_-]+)',url)
 return usable_id(match.group(1)) if match else ''

def works_from_cards(cards,account):
 items=[]
 for card in cards or []:
  vue=card.get('vue') or {}
  title=clean_title(vue.get('description')) or clean_title(card.get('title'))
  posted=str(card.get('posted_at') or '').strip()
  text_title,text_time,_,_=metrics_from_text(card.get('text'))
  if not title:title=text_title
  if not TIME_RE.search(posted):posted=text_time or posted
  allow_positional=card.get('kind') in ('post-feed-item','post-list-item','post-feed')
  counters=fill_counts(vue,card.get('metrics'),card.get('text'),allow_positional)
  vue_id=usable_id(vue.get('objectId'));linked=link_id(card.get('url'));attr_id=''
  for key in ('data-id','data-feed-id','data-object-id','data-export-id'):
   attr_id=usable_id((card.get('attrs') or {}).get(key))
   if attr_id:break
  if vue_id:post_id,source=vue_id,'platform_object_id'
  elif attr_id:post_id,source=attr_id,'platform_object_id'
  elif linked:post_id,source=linked,'platform_link'
  elif title and posted:post_id,source='local:'+hashlib.sha256((str(account)+'\n'+title+'\n'+posted).encode()).hexdigest(),'local_title_and_publish_time'
  else:continue
  published_at=iso_from_unix(vue.get('createTime')) or iso_from_text(posted)
  if not title:title='未命名作品'
  item={'post_id':post_id,'identity_source':source,'title':title,'url':card.get('url') or None,**counters}
  if posted:item['published_text']=posted
  if published_at:item['published_at']=published_at
  items.append(item)
 return items

def items_from_tables(tables):
 items=[]
 for table in tables or []:
  headers=[str(cell).strip() for cell in table.get('headers') or []]
  indices={field:next((i for i,header in enumerate(headers) if header in [label for label,name in LABELS if name==field]),None) for field in FIELDS}
  if not any(index is not None for index in indices.values()):continue
  for row in table.get('rows') or []:
   link=next((a for a in row.get('links') or [] if link_id(a.get('url'))),None)
   if not link:continue
   cells=row.get('cells') or []
   counters=blank_counts()
   for field,index in indices.items():
    if index is not None and index<len(cells):counters[field]=num(cells[index])
   items.append({'post_id':link_id(link['url']),'identity_source':'platform_link','title':clean_title(link.get('title')) or clean_title(cells[0] if cells else '') or '未命名作品','url':link['url'],**counters})
 return items

def score(item):
 return sum(item.get(key) is not None for key in FIELDS)+(0 if str(item.get('post_id','')).startswith('local:') else 2)

def dedupe(items):
 ranked={}
 for item in items:
  current=ranked.get(item['post_id'])
  ranked[item['post_id']]=item if current is None or score(item)>=score(current) else current
 platform=[item for item in ranked.values() if not str(item['post_id']).startswith('local:')]
 merged=[]
 for local in [item for item in ranked.values() if str(item['post_id']).startswith('local:')]:
  match=next((item for item in platform if item.get('title')==local.get('title') and item.get('published_text')==local.get('published_text') and item.get('title')),None)
  if match:
   for key in FIELDS:
    if match.get(key) is None and local.get(key) is not None:match[key]=local[key]
   if not match.get('published_at') and local.get('published_at'):match['published_at']=local['published_at']
  else:merged.append(local)
 return platform+merged

def overview_from_text(text):
 if '昨日数据' not in str(text or ''):return {}
 overview={}
 for field,label in (('new_views','新增播放'),('net_followers','净增关注'),('new_comments','新增评论')):
  match=re.search(re.escape(label)+r'\s*([\d,，]+)',text)
  if match:overview[field]=int(match.group(1).replace(',','').replace('，',''))
 return overview

def build_result(snapshot,account):
 text=snapshot.get('text') or ''
 items=dedupe(items_from_tables(snapshot.get('tables'))+works_from_cards(snapshot.get('cards'),account))
 overview=overview_from_text(text)
 base={'items':items,'overview':overview,'source_url':snapshot.get('source_url'),'scope':'lifetime'}
 if items:
  message=f'已读到本人视频号当前页{len(items)}条作品'
  if overview:message+='，并读到昨日账号数据'
  message+='。数字来自页面上的作品，不代表全部历史。'
  return {**base,'state':'verified','message':message,'coverage':'visible_page_only'}
 if any(marker in text for marker in ('暂无内容','暂无作品','还没有发表')):
  return {**base,'state':'verified_empty','message':'已进入本人后台，平台显示暂无作品。'}
 if overview:
  return {**base,'state':'verified_overview','message':'已读到本人视频号的昨日账号数据；当前页面没有读到逐条作品明细。'}
 return {**base,'state':'unverified','message':'页面已打开，但尚未识别到作品明细；没有写入空值或虚构数字。'}

class Node:
 def __init__(self,tag,attrs):
  self.tag=tag;self.attrs=dict(attrs);self.children=[];self.parent=None
 def attr(self,name):return self.attrs.get(name,'')
 def classes(self):return self.attr('class').split()

class Builder(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.root=Node('document',{});self.stack=[self.root];self.skip=0
 def handle_starttag(self,tag,attrs):
  if self.skip:
   if tag in ('script','style'):self.skip+=1
   return
  node=Node(tag,attrs);node.parent=self.stack[-1];self.stack[-1].children.append(node)
  if tag not in VOID:self.stack.append(node)
  if tag in ('script','style'):self.skip=1
 def handle_endtag(self,tag):
  if tag in ('script','style') and self.skip:
   self.skip-=1
   if self.skip:return
  if self.skip or tag in VOID:return
  for index in range(len(self.stack)-1,0,-1):
   if self.stack[index].tag==tag:
    del self.stack[index:];return
 def handle_data(self,data):
  if not self.skip and data:self.stack[-1].children.append(data)
 def handle_startendtag(self,tag,attrs):
  self.handle_starttag(tag,attrs)

def parse_html(html):
 builder=Builder();builder.feed(html);builder.close();return builder.root

def inner_text(node):
 if node is None:return ''
 chunks=[]
 def walk(current):
  if isinstance(current,str):chunks.append(current);return
  if current.tag in ('script','style') or (current.tag=='template' and not current.attr('shadowrootmode')):return
  if current.tag in BLOCK:chunks.append('\n')
  for child in current.children:walk(child)
  if current.tag in BLOCK:chunks.append('\n')
 for child in node.children:walk(child)
 return re.sub(r'\n{2,}','\n',''.join(chunks)).strip()

def walk_elements(node,pierce_shadow,visit):
 for child in node.children:
  if isinstance(child,str):continue
  if child.tag=='template':
   if pierce_shadow and child.attr('shadowrootmode'):walk_elements(child,True,visit)
   continue
  visit(child);walk_elements(child,pierce_shadow,visit)

def cards_from_html(html,pierce_shadow=True):
 root=parse_html(html);found=[]
 def take(node):
  classes=node.classes()
  if 'post-feed-item' in classes or any('post-list-item' in name or name=='post-feed' for name in classes):found.append(node)
 walk_elements(root,pierce_shadow,take)
 strict=[node for node in found if 'post-feed-item' in node.classes()]
 chosen=strict or found
 chosen=[node for node in chosen if not any(other is not node and contains(node,other) for other in chosen)]
 return [card_from_node(node) for node in chosen]

def contains(parent,node):
 found=False
 def visit(current):
  nonlocal found
  if current is node:found=True
 walk_elements(parent,True,visit)
 return found

def descendants(node):
 found=[]
 walk_elements(node,False,found.append)
 return found

def card_from_node(node):
 classes=node.classes()
 if 'post-feed-item' in classes:kind='post-feed-item'
 elif any('post-list-item' in name for name in classes):kind='post-list-item'
 elif 'post-feed' in classes:kind='post-feed'
 else:kind='card'
 title_node=next((item for item in descendants(node) if {'post-title','desc-text','post-desc','wording'} & set(item.classes())),None)
 time_node=next((item for item in descendants(node) if {'time-label','post-time','publish-time','create-time'} & set(item.classes())),None)
 metrics=[]
 for item in descendants(node):
  if 'data-item' in item.classes() or 'data-cell' in item.classes() or (item.tag=='li' and item.parent and 'statistic' in item.parent.classes()):
   count=next((child for child in descendants(item) if {'count','value'} & set(child.classes()) or child.tag=='em'),None)
   icon=next((child for child in descendants(item) if child.tag in ('i','svg','use') or 'icon' in child.classes()),None)
   icon_text=' '.join(icon.attr(name) for name in ('class','href','xlink:href')) if icon else ''
   metrics.append({'text':inner_text(count or item),'icon':icon_text.strip(),'label':item.attr('aria-label') or item.attr('title')})
 url=next((item.attr('href') for item in descendants(node) if item.tag=='a' and item.attr('href').startswith('http')),None)
 attrs={key:node.attr(key) for key in ('data-id','data-feed-id','data-object-id','data-export-id') if node.attr(key)}
 return {'kind':kind,'title':inner_text(title_node) if title_node else '','posted_at':inner_text(time_node) if time_node else '','text':inner_text(node),'url':url,'attrs':attrs,'metrics':metrics,'vue':None}

def tables_from_html(html,pierce_shadow=True):
 root=parse_html(html);tables=[]
 def take(node):
  if node.tag!='table':return
  headers=[inner_text(cell) for row in descendants(node) if row.tag=='tr' and row.parent and row.parent.tag=='thead' for cell in row.children if not isinstance(cell,str) and cell.tag=='th']
  rows=[]
  for row in descendants(node):
   if row.tag!='tr' or not row.parent or row.parent.tag!='tbody':continue
   cells=[inner_text(cell) for cell in row.children if not isinstance(cell,str) and cell.tag=='td']
   links=[{'url':item.attr('href'),'title':inner_text(item)} for item in descendants(row) if item.tag=='a' and item.attr('href')]
   rows.append({'cells':cells,'links':links})
  tables.append({'headers':headers,'rows':rows})
 walk_elements(root,pierce_shadow,take)
 return tables

def text_from_html(html):
 return inner_text(parse_html(html))

def snapshot_from_html(html,pierce_shadow=True):
 if not pierce_shadow:
  root=parse_html(html)
  def light_text(node):
   chunks=[]
   def walk(current):
    if isinstance(current,str):chunks.append(current);return
    if current.tag in ('script','style','template'):return
    if current.tag in BLOCK:chunks.append('\n')
    for child in current.children:walk(child)
    if current.tag in BLOCK:chunks.append('\n')
   for child in node.children:walk(child)
   return re.sub(r'\n{2,}','\n',''.join(chunks)).strip()
  return {'cards':cards_from_html(html,False),'tables':tables_from_html(html,False),'text':light_text(root)}
 return {'cards':cards_from_html(html,True),'tables':tables_from_html(html,True),'text':text_from_html(html)}
