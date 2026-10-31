"""Period review from consecutive local snapshots.

Counters move only when two stored snapshots can be subtracted. Missing
numbers stay missing. Account-day totals are returned beside post totals
and are never added into them.
"""
from datetime import datetime,timedelta,timezone
from collections import defaultdict
import math,re

ZONE=timezone(timedelta(hours=8))
PF={'douyin':'抖音','tencent':'视频号'}
FIELDS=('views','likes','comments','shares')
TEMPLATES=[
 {'id':'extend-top','label':'下一条接着讲本期看得最多的那题'},
 {'id':'fix-title','label':'播放少的几条，下条只改标题，别的先不动'},
 {'id':'fill-gap','label':'空档的日子补一条，避免连着断更'},
 {'id':'ask-comment','label':'结尾留一个具体问题，方便观众留言'},
 {'id':'both-platforms','label':'同一题两个平台都发，看哪边有人看'},
 {'id':'sync-again','label':'再同步一次后台，补上和上一期比'},
]
TEMPLATE_IDS=[item['id'] for item in TEMPLATES]

def number(value):
 return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 else None

def as_count(value):
 value=number(value)
 if value is None:return None
 return int(value) if float(value).is_integer() else value

def parse_dt(value):
 if isinstance(value,bool) or value in (None,''):return None
 try:
  if isinstance(value,(int,float)) or str(value).isdigit():
   raw=float(value)
   if raw>10**12:raw/=1000
   return datetime.fromtimestamp(raw,ZONE) if raw>0 and math.isfinite(raw) else None
  text=str(value).strip()
  if re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):return datetime.strptime(text,'%Y-%m-%d').replace(tzinfo=ZONE)
  if '年' in text:return datetime.strptime(text,'%Y年%m月%d日 %H:%M').replace(tzinfo=ZONE)
  parsed=datetime.fromisoformat(text.replace('Z','+00:00'))
  return parsed.replace(tzinfo=ZONE) if parsed.tzinfo is None else parsed.astimezone(ZONE)
 except (TypeError,ValueError,OverflowError,OSError):return None

def clean_prefs(raw,previous=None):
 previous=previous or {};raw=raw or {}
 if not isinstance(raw,dict):raise ValueError('请按页面上的项目保存')
 goal=previous.get('weekly_goal')
 if 'weekly_goal' in raw:
  goal=raw.get('weekly_goal')
  if goal in ('',None):goal=None
  elif isinstance(goal,bool) or not isinstance(goal,(int,float)) or not float(goal).is_integer() or not 1<=int(goal)<=14:raise ValueError('目标周更请填 1 到 14 的整数，也可以先留空')
  else:goal=int(goal)
 checked=list(previous.get('checked') or [])
 if 'checked' in raw:
  checked=raw.get('checked')
  if not isinstance(checked,list) or len(checked)>len(TEMPLATE_IDS) or len(set(checked))!=len(checked):raise ValueError('请勾选列出的行动')
  if any(not isinstance(item,str) or item not in TEMPLATE_IDS for item in checked):raise ValueError('请勾选列出的行动')
 return {'weekly_goal':goal,'checked':checked}

def _latest_on_or_before(by_day,day):
 chosen=None
 for key,row in by_day.items():
  if key<=day and (chosen is None or key>chosen[0]):chosen=(key,row)
 return chosen[1] if chosen else None

def _counters(row):
 return {field:as_count(number(row.get(field))) if row else None for field in FIELDS}

def _diff(start,end):
 out={}
 for field in FIELDS:
  before,after=number(start.get(field)) if start else None,number(end.get(field)) if end else None
  out[field]=as_count(after-before) if before is not None and after is not None and after>=before else None
 return out

def _decreased(start,end):
 if not start or not end:return False
 before,after=number(start.get('views')),number(end.get('views'))
 return before is not None and after is not None and after<before

def _classify(by_day,anchor,days):
 start_edge=anchor-timedelta(days=days);end=None
 for day,row in by_day.items():
  if start_edge<day<=anchor and (end is None or day>end['_day']):end=row
 if end is None:
  older=_latest_on_or_before(by_day,anchor)
  return {'end':older,'start':None,'coverage':'stale' if older else 'none','span_days':None,'delta':_diff(None,older),'decreased':False}
 start=_latest_on_or_before(by_day,start_edge)
 if start and start['_day']<end['_day']:
  span=(end['_day']-start['_day']).days
  coverage='window' if span==days else 'partial' if span<days else 'too_wide'
  return {'end':end,'start':start,'coverage':coverage,'span_days':span,'delta':_diff(start,end),'decreased':_decreased(start,end)}
 earlier=[row for day,row in by_day.items() if start_edge<day<end['_day']]
 if earlier:
  start=min(earlier,key=lambda row:row['_day']);span=(end['_day']-start['_day']).days
  return {'end':end,'start':start,'coverage':'partial','span_days':span,'delta':_diff(start,end),'decreased':_decreased(start,end)}
 return {'end':end,'start':None,'coverage':'single','span_days':None,'delta':_diff(None,end),'decreased':False}

def _field_total(changes,field,included,basis):
 if basis=='unaligned':return {'value':None,'missing':0,'complete':False}
 rows=included if basis=='period_delta' else [item for item in changes if item['coverage']!='none']
 source='delta' if basis=='period_delta' else 'cumulative'
 values=[item[source][field] for item in rows]
 known=[value for value in values if value is not None];missing=sum(value is None for value in values)
 return {'value':sum(known) if known else None,'missing':missing,'complete':bool(rows) and missing==0}

def _summarize(changes,days):
 window=[item for item in changes if item['coverage']=='window' and item['delta']['views'] is not None]
 partial=[item for item in changes if item['coverage']=='partial' and item['delta']['views'] is not None]
 if window:
  included,coverage,span,basis=window,'window',days,'period_delta'
 elif partial:
  spans={item['span_days'] for item in partial}
  if len(spans)==1:included,coverage,span,basis=partial,'partial',spans.pop(),'period_delta'
  else:included,coverage,span,basis=[],'mixed',None,'unaligned'
 else:
  included,span,basis=[],None,'cumulative'
  if any(item['coverage']=='window' for item in changes):coverage='window'
  elif any(item['coverage']=='too_wide' for item in changes):coverage='too_wide'
  elif any(item['coverage']=='partial' for item in changes):coverage='partial'
  elif any(item['coverage']=='single' for item in changes):coverage='single'
  elif any(item['coverage']=='stale' for item in changes):coverage='stale'
  else:coverage='none'
 included_keys={item['key'] for item in included}
 for item in changes:item['in_total']=item['key'] in included_keys
 return {'included':included,'coverage':coverage,'span_days':span,'basis':basis,'views':_field_total(changes,'views',included,basis),'likes':_field_total(changes,'likes',included,basis),'comments':_field_total(changes,'comments',included,basis),'shares':_field_total(changes,'shares',included,basis),'decreased':sum(item['decreased'] for item in changes)}

def _direction(value,prior):
 if value is None or prior is None:return None
 if value>prior:return 'up'
 if value<prior:return 'down'
 return 'flat'

def _metric(value,prior,basis):
 return {'value':value,'prior':prior,'direction':_direction(value,prior),'basis':basis}

def _short(day):return f'{day.month:02d}-{day.day:02d}'

def _bounds(now,days):
 today=now.astimezone(ZONE).date();anchor=today-timedelta(days=1) if days==1 else today
 return anchor,anchor-timedelta(days=days)

def _count_posts(works,start_edge,anchor):
 if not works:return {'value':None,'undated':0}
 dated=[work for work in works if work['published_day']]
 if not dated:return {'value':None,'undated':len(works)}
 return {'value':sum(start_edge<work['published_day']<=anchor for work in dated),'undated':len(works)-len(dated)}

def _apply(works,anchor,days):
 applied=[]
 for work in works:
  change=_classify(work['by_day'],anchor,days)
  applied.append({**work,**change,'cumulative':_counters(change['end']),'in_total':False})
 return applied

def _public_work(item):
 show_delta=item['coverage'] in ('window','partial')
 end=item.get('end')
 return {'id':(end or {}).get('id') or item['key'][2],'platform':item['platform'],'label':PF[item['platform']],'title':item['title'],'published_on':item['published_day'].isoformat() if item['published_day'] else None,'observed_on':end['_day'].isoformat() if end else None,'coverage':item['coverage'],'span_days':item['span_days'],'in_total':item['in_total'],'views':item['cumulative']['views'],'views_delta':item['delta']['views'] if show_delta else None,'likes':item['cumulative']['likes'],'likes_delta':item['delta']['likes'] if show_delta else None,'comments':item['cumulative']['comments'],'comments_delta':item['delta']['comments'] if show_delta else None,'shares':item['cumulative']['shares'],'shares_delta':item['delta']['shares'] if show_delta else None}

def _highlights(changes,summary):
 if summary['basis']=='period_delta':
  pool=[item for item in changes if item['in_total'] and item['delta']['views'] is not None];rank=lambda item:item['delta']['views'];basis='period_delta'
 elif summary['basis']=='cumulative':
  pool=[item for item in changes if item['cumulative']['views'] is not None];rank=lambda item:item['cumulative']['views'];basis='cumulative'
 else:return {'basis':'unaligned','top':[],'bottom':[],'note':'每条作品相隔的天数不一样，先不排先后。'}
 pool=sorted(pool,key=lambda item:(-rank(item),item['title']))
 top=pool[:3];rest=pool[3:];bottom=list(reversed(rest[-3:])) if rest else []
 note='按累计播放排列。再同步一次，才能按增加了多少来排。' if basis=='cumulative' else None
 return {'basis':basis,'top':[_public_work(item) for item in top],'bottom':[_public_work(item) for item in bottom],'note':note}

def _share(values):
 if any(value is None for value in values):return [None for _ in values]
 total=sum(values)
 if total<=0:return [None for _ in values]
 return [round(value/total,4) for value in values]

def _platform_block(platform,changes,days,anchor,start_edge):
 summary=_summarize(changes,days);posts=_count_posts(changes,start_edge,anchor)
 return {'platform':platform,'label':PF[platform],'posts':posts['value'],'undated':posts['undated'],'views':summary['views']['value'],'views_basis':summary['basis'] if changes else None,'views_complete':summary['views']['complete'],'coverage':summary['coverage'] if changes else 'none','span_days':summary['span_days'],'note':None if changes else '还没有同步'}

def _tip(snapshot_days,summary,prior_views,platform,days):
 if snapshot_days==0:return '这个平台还没有同步记录。' if platform!='all' else '还没有收回来的后台记录。先同步一次抖音或视频号，这里才会有数字。'
 if snapshot_days==1 or summary['coverage'] in ('single','stale','none'):return '目前只有一次同步记录，显示的是累计数字。再同步一次，才能看出增加了多少。'
 if summary['basis']=='unaligned':return '每条作品两次同步相隔的天数不一样，播放没有加总。'
 if summary['coverage']=='too_wide':return '已经有两次同步，但相隔超过这段时间，不能当成这段时间的增加。'
 if summary['basis']=='period_delta' and summary['coverage']=='partial':return f"这段时间还没对齐到正好{days}天。下面的增加来自最近两次同步，相隔{summary['span_days']}天。"
 if summary['basis']!='period_delta' and summary['decreased']:return '播放比上次记录少，差额没有算成增加。上面显示的是累计。'
 if summary['basis']!='period_delta':return '两次同步还减不出这段时间的播放增加，上面显示的是累计。'
 if summary['coverage']=='window' and prior_views is None:return '播放的增加已经能看。还要再早一次同步，才能和上一期的播放比。'
 return None

def _interactions(summary,prior):
 parts=[summary[field] for field in ('likes','comments','shares')]
 if any(part['value'] is None or not part['complete'] for part in parts):return _metric(None,None,summary['basis'])
 prior_value=None
 if prior and prior['basis']=='period_delta' and prior['coverage']=='window' and summary['coverage']=='window':
  prior_parts=[prior[field] for field in ('likes','comments','shares')]
  if all(part['value'] is not None and part['complete'] for part in prior_parts):prior_value=sum(part['value'] for part in prior_parts)
 return _metric(sum(part['value'] for part in parts),prior_value,summary['basis'])

def build_review_board(rows,projects=None,account_rows=None,prefs=None,days=7,platform='all',now=None):
 now=parse_dt(now) or datetime.now(ZONE)
 if now.tzinfo is None:now=now.replace(tzinfo=ZONE)
 else:now=now.astimezone(ZONE)
 days=7 if days not in (1,7) else days
 platform=platform if platform in ('all','douyin','tencent') else 'all'
 prefs=prefs or {};titles={item.get('id'):item.get('title') for item in projects or [] if isinstance(item,dict)}
 grouped=defaultdict(dict)
 for raw in rows or []:
  if not isinstance(raw,dict) or raw.get('metric_scope')!='lifetime' or raw.get('platform') not in PF:continue
  observed=parse_dt(raw.get('observed_at'))
  if not observed or observed>now+timedelta(minutes=5):continue
  ident=str(raw.get('source_local_id') or raw.get('post_id') or '')
  if not ident:continue
  account=str(raw.get('account_id') or raw.get('account') or 'current-linked-account')
  key=(raw.get('platform'),account,ident);day=observed.astimezone(ZONE).date();candidate={**raw,'_observed':observed,'_day':day}
  current=grouped[key].get(day)
  if current is None or (observed,raw.get('snapshot_source')=='browser_detail')>=(current['_observed'],current.get('snapshot_source')=='browser_detail'):grouped[key][day]=candidate
 works=[]
 for key,by_day in grouped.items():
  latest=max(by_day.values(),key=lambda row:row['_observed']);published=None
  for row in sorted(by_day.values(),key=lambda item:item['_observed'],reverse=True):
   stamp=parse_dt(row.get('published_at') or row.get('published_text'))
   if stamp:published=stamp.astimezone(ZONE).date();break
  title=latest.get('title') or titles.get(latest.get('project_id')) or '未命名作品'
  works.append({'key':key,'platform':key[0],'by_day':by_day,'published_day':published,'title':str(title).removeprefix('复盘 · ')})
 anchor,start_edge=_bounds(now,days);prior_anchor=anchor-timedelta(days=days)
 def scoped(which):return [work for work in works if which=='all' or work['platform']==which]
 def changes_for(which,at):return _apply(scoped(which),at,days)
 posts=_count_posts(scoped(platform),start_edge,anchor);prior_posts=_count_posts(scoped(platform),prior_anchor-timedelta(days=days),prior_anchor)
 snapshot_days=len({day for work in scoped(platform) for day in work['by_day']})
 platforms=[_platform_block(name,changes_for(name,anchor),days,anchor,start_edge) for name in ('douyin','tencent')]
 comparable=[block for block in platforms if block['views'] is not None]
 same_view=len({(block['views_basis'],block['coverage'],block['span_days']) for block in comparable})==1
 view_shares=_share([block['views'] for block in platforms]) if same_view else [None,None]
 post_shares=_share([block['posts'] for block in platforms])
 for block,view_share,post_share in zip(platforms,view_shares,post_shares):
  block['view_share']=view_share;block['post_share']=post_share
 scoped_changes=changes_for(platform,anchor);current=_summarize(scoped_changes,days);prior=_summarize(changes_for(platform,prior_anchor),days)
 prior_views=prior['views']['value'] if current['coverage']=='window' and current['basis']=='period_delta' and prior['coverage']=='window' and prior['basis']=='period_delta' else None
 highlights=_highlights(scoped_changes,current)
 engagement_available=any(item['cumulative'][field] is not None for item in scoped_changes for field in ('likes','comments','shares'))
 accounts=[]
 for row in account_rows or []:
  if not isinstance(row,dict) or (platform not in ('all',row.get('platform'))):continue
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(row.get('day') or '')):continue
  day=datetime.strptime(row['day'],'%Y-%m-%d').date()
  if not start_edge<day<=anchor:continue
  values=row.get('values') if isinstance(row.get('values'),dict) else {}
  accounts.append({'id':row.get('id'),'platform':row.get('platform'),'label':PF.get(row.get('platform'),'视频号'),'account_label':row.get('account_label'),'day':row['day'],'new_views':as_count(number(values.get('new_views'))),'net_followers':as_count(number(values.get('net_followers'))),'new_comments':as_count(number(values.get('new_comments')))})
 today=now.date();week_start=today-timedelta(days=today.weekday());week_end=week_start+timedelta(days=6)
 week=_count_posts(scoped(platform),week_start-timedelta(days=1),week_end)
 by_day=[];empty=0;streak=0;longest=0
 for offset in range(days):
  day=start_edge+timedelta(days=offset+1);count=None if posts['value'] is None else sum(work['published_day']==day for work in scoped(platform))
  by_day.append({'day':day.isoformat(),'posts':count})
  if count==0:empty+=1;streak+=1;longest=max(longest,streak)
  elif count is not None:streak=0
 if posts['value'] is None:cadence_note='这些作品还没有发布时间，暂时数不清本期发了几条。'
 elif days==1:cadence_note='这天有更新。' if posts['value'] else '这天没有新内容。'
 elif longest>=2:cadence_note=f'最长连续 {longest} 天没发。'
 elif empty==0:cadence_note='这几天每天都有更新。'
 else:cadence_note=f'中间空了 {empty} 天。'
 if posts['undated']:cadence_note+=f"另有 {posts['undated']} 条没有发布时间，没算进去。"
 checked=[item for item in (prefs.get('checked') or []) if item in TEMPLATE_IDS]
 goal=prefs.get('weekly_goal')
 if isinstance(goal,bool) or not isinstance(goal,(int,float)) or not float(goal).is_integer() or not 1<=int(goal)<=14:goal=None
 else:goal=int(goal)
 works_public=sorted((_public_work(item) for item in scoped_changes),key=lambda item:(-(item['views_delta'] if item['views_delta'] is not None else item['views'] if item['views'] is not None else -1),item['title']))
 measured=None
 if current['basis']=='period_delta' and current['included']:
  start_day=min(item['start']['_day'] for item in current['included']);end_day=max(item['end']['_day'] for item in current['included'])
  measured={'start':start_day.isoformat(),'end':end_day.isoformat(),'label':f'{_short(start_day)} 至 {_short(end_day)}'}
 return {'version':1,'as_of':now.isoformat(timespec='seconds'),'days':days,'platform':platform,'period':{'start':(start_edge+timedelta(days=1)).isoformat(),'end':anchor.isoformat(),'label':_short(anchor) if days==1 else f'{_short(start_edge+timedelta(days=1))} 至 {_short(anchor)}'},'comparison':{'mode':'period_delta' if current['basis']=='period_delta' else current['basis'],'coverage':current['coverage'],'snapshot_days':snapshot_days,'span_days':current['span_days'],'measured':measured,'excluded_decreased':current['decreased'],'tip':_tip(snapshot_days,current,prior_views,platform,days)},'overview':{'posts':_metric(posts['value'],prior_posts['value'] if posts['value'] is not None else None,'published'),'views':_metric(current['views']['value'],prior_views,current['basis']),'interactions':_interactions(current,prior)},'cadence':{'posts':posts['value'],'undated':posts['undated'],'active_days':None if posts['value'] is None else sum(item['posts'] not in (0,None) for item in by_day),'span_days':days,'empty_days':None if posts['value'] is None else empty,'longest_gap':None if posts['value'] is None else longest,'note':cadence_note,'by_day':by_day,'max_posts':max([item['posts'] or 0 for item in by_day],default=0),'weekly_goal':goal,'week_start':week_start.isoformat(),'week_end':week_end.isoformat(),'week_posts':week['value'],'week_label':f'{_short(week_start)} 至 {_short(week_end)}'},'platforms':platforms,'highlights':highlights,'engagement':{'available':engagement_available,'likes':{**current['likes'],'basis':current['basis']},'comments':{**current['comments'],'basis':current['basis']},'shares':{**current['shares'],'basis':current['basis']}},'actions':{'checked':checked,'suggested':3,'templates':TEMPLATES},'works':works_public,'account_daily':accounts,'placeholders':[{'platform':'xiaohongshu','label':'小红书','note':'这次先不计入'}]}
