"""Evidence-bounded content review. Published age is measured at observation time.

The 24/72-hour capture tolerances and peer/sample floors are workbench heuristics,
not platform rules, statistical significance, or a promise of paid results.
"""
from datetime import datetime,timedelta,timezone
from collections import Counter,defaultdict
from statistics import median
import math,re

ZONE=timezone(timedelta(hours=8))
DEFAULTS={'goal':'consultation','review_days':3,'min_observation_hours':24,'min_peer_count':3,'min_sample_views':100,'test_budget':None,'max_cost_per_lead':None,'landing_ready':False}
PF={'douyin':'抖音','tencent':'视频号'}

def timestamp(value):
 if isinstance(value,bool) or value in [None,'']:return None
 try:
  if isinstance(value,(int,float)) or str(value).isdigit():
   number=float(value)
   if number>10**12:number/=1000
   return datetime.fromtimestamp(number,ZONE) if number>0 and math.isfinite(number) else None
  text=str(value).strip()
  if re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):return None # date-only is not an exact publication time
  if '年' in text:return datetime.strptime(text,'%Y年%m月%d日 %H:%M').replace(tzinfo=ZONE)
  date=datetime.fromisoformat(text.replace('Z','+00:00'));return date.replace(tzinfo=ZONE) if date.tzinfo is None else date.astimezone(ZONE)
 except (TypeError,ValueError,OverflowError,OSError):return None

def number(value):
 return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 else None

def identity(row):return row.get('platform'),str(row.get('account_id') or row.get('account') or 'current-linked-account'),str(row.get('source_local_id') or row.get('post_id') or '')
def interaction(row):
 views=number(row.get('views'));parts=[number(row.get(k)) for k in ['likes','comments','shares']]
 return sum(parts)/views if views and all(x is not None for x in parts) else None

def build_review(rows,account_days=None,projects=None,settings=None,days=3,platform='all',now=None):
 now=timestamp(now) or datetime.now(ZONE);settings={**DEFAULTS,**(settings or {})}
 days=int(days);days=days if days in [0,1,3,7,30] else 3
 start=now.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=days) if days else None
 history=defaultdict(list);titles={p['id']:p['title'] for p in projects or []}
 for raw in rows:
  if raw.get('metric_scope')!='lifetime' or raw.get('platform') not in PF:continue
  if platform!='all' and raw.get('platform')!=platform:continue
  observed=timestamp(raw.get('observed_at'));published=timestamp(raw.get('published_at') or raw.get('published_text'))
  if not observed or observed>now+timedelta(minutes=5) or not identity(raw)[2]:continue
  row={**raw,'title':raw.get('title') or titles.get(raw.get('project_id')) or '未命名作品','_observed':observed,'_published':published}
  row['title']=row['title'].removeprefix('复盘 · ');history[identity(row)].append(row)
 latest=[];waiting=[];excluded=Counter();captured_windows=defaultdict(list)
 minimum=max(24,float(settings['min_observation_hours']))
 for key,versions in history.items():
  versions.sort(key=lambda r:r['_observed']);row=versions[-1];published=next((r['_published'] for r in reversed(versions) if r['_published']),None)
  qualifying=[r for r in versions if published and (r['_observed']-published).total_seconds()/3600>=minimum]
  if qualifying:
   # Keep play/interaction counts together, rather than merging mismatched counters.
   row=dict(next((r for r in reversed(qualifying) if number(r.get('views')) is not None),qualifying[-1]))
   field_times={}
   for field in ['completion_rate','five_second_completion_rate','average_watch_duration_seconds','follower_gain','exposure_count']:
    detail=next((r for r in reversed(qualifying) if number(r.get(field)) is not None),None)
    if detail:row[field]=detail[field];field_times[field]=detail['_observed'].isoformat()
   row['detail_field_times']=field_times
  observed=row['_observed']
  for target,tolerance in [(24,4),(72,8)]:
   matches=[r for r in versions if published and number(r.get('views')) is not None and target<= (r['_observed']-published).total_seconds()/3600<=target+tolerance]
   if matches:captured_windows[key].append((target,min(matches,key=lambda r:abs((r['_observed']-published).total_seconds()/3600-target))))
  if not captured_windows.get(key):
   # A daily morning pull often first sees an evening post at ~36h. Compare
   # it with other ~36h captures; never rename that capture "first 24h".
   first_after_day=next((r for r in versions if published and number(r.get('views')) is not None and 24<=(r['_observed']-published).total_seconds()/3600<=48),None)
   if first_after_day:
    hours=(first_after_day['_observed']-published).total_seconds()/3600
    captured_windows[key].append((int(round(hours/4))*4,first_after_day))
  if not published:
   waiting.append({'id':row['id'],'title':row['title'],'platform':row['platform'],'reason':'还没有准确的发布时间'});excluded['unknown_published']+=1;continue
  if published>observed:
   waiting.append({'id':row['id'],'title':row['title'],'platform':row['platform'],'reason':'发布时间与采集时间不一致'});excluded['invalid_time']+=1;continue
  if start and published<start:excluded['outside_period']+=1;continue
  age=(observed-published).total_seconds()/3600
  if age<minimum:
   waiting.append({'id':row['id'],'title':row['title'],'platform':row['platform'],'reason':f'采集时发布未满{minimum:g}小时','age_hours':round(age,1)});excluded['under_age']+=1;continue
  windows=captured_windows.get(key,[]);window=windows[0] if windows else None
  growth=None;growth_interval=None
  before=[r for r in versions[:-1] if 20<=(observed-r['_observed']).total_seconds()/3600<=28]
  if before:
   previous=min(before,key=lambda r:abs((observed-r['_observed']).total_seconds()/3600-24))
   current_count=number(row.get('views'));old_count=number(previous.get('views'))
   if current_count is not None and old_count is not None and current_count>=old_count:
    growth=current_count-old_count;growth_interval=round((observed-previous['_observed']).total_seconds()/3600,1)
  latest.append({**row,'_key':key,'age_hours':round(age,1),'published_at':published.isoformat(),'observed_at':observed.isoformat(),'interaction_rate':interaction(row),'growth_views':growth,'growth_interval':growth_interval,'capture_window_hours':window[0] if window else None,'_window_row':window[1] if window else None,'measurement_label':f'{window[0]}小时附近有记录' if window else '只有当前累计记录'})
 for row in latest:
  win=row['capture_window_hours'];current=row['_window_row'];peers=[]
  if win:
   for key,windows in captured_windows.items():
    if key[:2]!=row['_key'][:2] or key==row['_key']:continue
    peers.extend(candidate for target,candidate in windows if target==win and number(candidate.get('views')) is not None)
  peer_views=[r['views'] for r in peers];baseline=median(peer_views) if len(peers)>=settings['min_peer_count'] else None
  current_views=number(current.get('views')) if current else None
  ratio=current_views/baseline if baseline and current_views is not None else None
  rate=row['interaction_rate'];peer_rates=[interaction(r) for r in peers if interaction(r) is not None]
  reference_rate=median(peer_rates) if len(peer_rates)>=settings['min_peer_count'] else None
  comparison_rate=interaction(current) if current else None
  enough=current_views is not None and current_views>=settings['min_sample_views']
  state='observe'
  if ratio is not None and enough:
   if ratio>=1.5 and comparison_rate is not None and reference_rate is not None and comparison_rate>=reference_rate:state='good'
   elif ratio<=0.7:state='improve'
  facts=[f"采集时已发布{row['age_hours']:g}小时"]
  if number(row.get('views')) is not None:facts.append(f"当前累计播放{row['views']:,}")
  if rate is not None:facts.append(f'赞评转合计占播放{rate:.1%}')
  for field,label in [('five_second_completion_rate','前5秒完播'),('completion_rate','整条完播')]:
   value=number(row.get(field))
   if value is not None and value<=1:facts.append(label+f'{value:.1%}')
  if number(row.get('average_watch_duration_seconds')) is not None:facts.append(f"平均观看{row['average_watch_duration_seconds']:g}秒")
  if number(row.get('follower_gain')) is not None:facts.append(f"本条带来关注{row['follower_gain']:g}")
  if ratio is not None:facts.append(f'{win}小时附近播放是同账号对照的{ratio:.2f}倍（{len(peers)}条对照）')
  if row['growth_views'] is not None:facts.append(f"两次回收相隔{row['growth_interval']:g}小时，播放增加{row['growth_views']:,}")
  missing=[]
  if not win:missing.append('发布24/72小时附近的历史记录')
  if baseline is None:missing.append('同账号、同观察时段的足量对照')
  if number(row.get('completion_rate')) is None:missing.append('完播与观看停留')
  if number(row.get('leads')) is None:missing.append('有效咨询与成交结果')
  if number(row.get('ad_spend')) is None:missing.append('是否投过流、实际花费')
  if state=='good':
   hypothesis='可能是题目、开场或传播点更贴合观众；需回看内容和评论核对，数据本身不能说明原因。'
   action='优先回看这条的开场、具体例子和评论；下一条只延展同一个客户问题，保留可对照的记录。'
  elif state=='improve':
   hypothesis='可能与题目、标题承诺、开场节奏或触达人群有关；当前无法认定是哪一个。'
   action='先检查标题是否在正文兑现，再回看开头；下一条只改一个地方，按同样时段重新观察。'
  else:
   hypothesis='当前只能描述已回收的表现。对照或观看数据不够，先不判断是开场、选题还是流量导致。'
   action='先补一次后续回收；回看客户在评论里问什么，再选一个具体问题延展。'
  if state=='observe' and settings['goal']=='consultation' and any(w in row['title'] for w in ['瓶颈','认知','重构','方法论','token','Token']):
   hypothesis='一种需要核对的可能：讲法偏概念，观众未必立刻知道与你能解决的哪件工作有关。先回看开头和评论；没有留存对照，不能认定这是原因。'
   action='同题下一条换成一件具体经营任务：谁遇到什么问题、拿什么材料、做出什么结果、怎样核对。只改这一处，再按同样时段观察。'
  five=number(row.get('five_second_completion_rate'));complete=number(row.get('completion_rate'))
  if state=='observe' and five is not None and complete is not None and complete<=five<=1:
   if 1-five>five-complete:
    hypothesis=f'先回看开头：后台前5秒完播{five:.1%}、整条完播{complete:.1%}。优先核对是否及时说清客户问题与看点；也可能是触达人群不同，仍需对照。'
    action='下一条先只改开头：直接说清谁遇到什么问题、看完能学会哪一步，再给一个真实例子。按相同观察时段回收，核对前5秒与咨询有没有改善。'
   else:
    hypothesis=f'开头与后段都要对照：前5秒完播{five:.1%}、整条完播{complete:.1%}。可能是后面铺垫较长或材料不够具体，需要回看原片验证，不能仅靠两个比例认定原因。'
    action='先回看开头之后是否尽快给出具体例子与做法。下一条只改铺垫和例子的位置，再留同时间记录比较。'
  if settings['goal']=='consultation':action+=' 同时确认这条主要是破圈、建立信任还是接咨询，再用对应结果评价；播放高不等于有效咨询多。'
  spend=number(row.get('ad_spend'));leads=number(row.get('leads'))
  gates={'已满观察时间':row['age_hours']>=minimum,'同时间对照表现持续较好':state=='good' and enough,'对照记录在近7天':bool(current) and (now-current['_observed']).total_seconds()<=7*86400,'自然与付费表现已分清':spend==0 or number(row.get('organic_views')) is not None,'有业务结果可核对':bool(leads) if settings['goal']=='consultation' else bool(number(row.get('follower_gain'))) if settings['goal']=='followers' else bool(number(row.get('profit'))),'有试投上限和承接安排':bool(settings.get('test_budget')) and bool(settings.get('landing_ready'))}
  if settings['goal']=='consultation':gates['有可接受的咨询成本']=bool(settings.get('max_cost_per_lead')) and leads is not None and leads>0 and spend is not None and spend/leads<=settings['max_cost_per_lead']
  if state=='improve':ad={'state':'hold','label':'先改内容，暂不放大','reason':'同时间表现还没达到本账号对照，先完成一次改稿复测。'}
  elif all(gates.values()):ad={'state':'test','label':'可讨论一次小额验证','reason':'已有对照与业务记录；先人工核对目标、单次上限和停止条件，再决定是否试投。','budget_cap':settings['test_budget']}
  else:ad={'state':'insufficient','label':'先补证据，再判断投流','reason':'还需确认：'+'、'.join(k for k,v in gates.items() if not v)+'。'}
  row.update(performance=state,facts=facts,hypothesis=hypothesis,next_action=action,missing=missing,peer_count=len(peers),reference_views=baseline,view_multiple=ratio,comparison_interaction_rate=comparison_rate,comparison_observed_at=current['_observed'].isoformat() if current else None,ad_advice=ad)
 latest.sort(key=lambda r:r['_published'],reverse=True)
 public=[{k:v for k,v in row.items() if not k.startswith('_')} for row in latest]
 days_rows=[]
 for row in account_days or []:
  try:day=datetime.fromisoformat(row['day']).replace(tzinfo=ZONE)
  except (ValueError,TypeError,KeyError):continue
  if (not start or day>=start) and day.date()<now.date() and (platform=='all' or row.get('platform')==platform):days_rows.append(row)
 total_views=sum(r.get('values',{}).get('new_views',0) for r in days_rows if number(r.get('values',{}).get('new_views')) is not None)
 ready_ads=[r for r in public if r['ad_advice']['state']=='test']
 return {'as_of':now.isoformat(),'days':days,'period_start':start.isoformat() if start else None,'platform':platform,'goal':settings['goal'],'counts':{'reviewable':len(public),'waiting':len(waiting),'outside_period':excluded['outside_period'],'unknown_published':excluded['unknown_published'],'good':sum(r['performance']=='good' for r in public),'improve':sum(r['performance']=='improve' for r in public),'observe':sum(r['performance']=='observe' for r in public),'near_24h':sum(r['capture_window_hours']==24 for r in public),'near_72h':sum(r['capture_window_hours']==72 for r in public),'growth_available':sum(r['growth_views'] is not None for r in public)},'account_days':days_rows,'daily_new_views':total_views if days_rows else None,'posts':public,'waiting':waiting,'ad_summary':{'label':'有内容可讨论小额验证' if ready_ads else '先核对业务结果，暂不按播放量加钱','ready_count':len(ready_ads),'automatic_spend':False},'method':{'minimum_hours':minimum,'capture_windows':{'24':[24,28],'72':[72,80]},'peer_floor':settings['min_peer_count'],'sample_floor':settings['min_sample_views'],'note':'24小时门槛、对照数量和观察下限是工作台的操作规则，不是平台保证。累计值、相隔约一天的新增、24/72小时附近快照分开看。'}}
