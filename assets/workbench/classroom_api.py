"""Learner-facing connections, work requests, finished-video delivery and daily reports."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import hashlib,json,os,re,sys,threading,time
from fastapi import Request,UploadFile,File,HTTPException
from memory_limits import MAX_PROFILE_BYTES
from classroom_research import TikHub,PLATFORMS,HOT_PLATFORMS,validate_config,normalize,plan,curate,protect,published_time,ranked_board
from review_board import build_review_board,clean_prefs

VERSION='0.8.0'
def daily_reports(rows,projects,account_rows=None):
 days={};titles={p['id']:p['title'] for p in projects}
 for row in rows:
  if row.get('metric_scope')!='lifetime':continue
  day=str(row.get('observed_at',''))[:10]
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):continue
  key=(row.get('platform'),str(row.get('post_id')))
  bucket=days.setdefault(day,{})
  if key not in bucket or (row['observed_at'],row.get('snapshot_source')=='browser_detail')>(bucket[key]['observed_at'],bucket[key].get('snapshot_source')=='browser_detail'):bucket[key]=row
 result=[]
 for day,items in sorted(days.items(),reverse=True):
  items=[{**row,'title':titles.get(row.get('project_id'),row.get('title') or row.get('post_id','未命名作品'))} for row in items.values()]
  known=[r.get('views') for r in items if isinstance(r.get('views'),(int,float))]
  total=sum(known) if known else None
  counts={platform:sum(r.get('platform')==platform for r in items) for platform in ['douyin','tencent']};leaders=[]
  for platform,label in [('douyin','抖音'),('tencent','视频号')]:
   candidates=[r for r in items if r.get('platform')==platform and isinstance(r.get('views'),(int,float))]
   if candidates:
    top=max(candidates,key=lambda r:r['views']);leaders.append({'platform':platform,'title':top['title'],'views':top['views']})
  summary='本次记录：'+'、'.join(label+str(counts[p])+'条' for p,label in [('douyin','抖音'),('tencent','视频号')] if counts[p])+'。'
  if leaders:summary+='各平台累计播放最多的题目：'+'；'.join(('抖音' if r['platform']=='douyin' else '视频号')+'「'+r['title'].removeprefix('复盘 · ')[:28]+'」'+f"{r['views']:,}次" for r in leaders)+'。'
  summary+='先点日期看明细，核对这些题是否贴近你的客户；比较时也要看发布时长。这是累计快照，不是当日新增。'
  result.append({'day':day,'works':len(items),'known_views_sum':total,'missing_views':len(items)-len(known),'summary':summary,'leaders':leaders,'platform_counts':counts,'items':items})
 for row in account_rows or []:
  day=row.get('day','')
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):continue
  entry=next((r for r in result if r['day']==day),None)
  if entry is None:
   entry={'day':day,'works':0,'known_views_sum':None,'missing_views':0,'summary':'','items':[]};result.append(entry)
  entry.setdefault('accounts',[]).append(row)
  values=row.get('values',{});parts=[]
  for key,label in [('new_views','新增播放'),('net_followers','净增关注'),('new_comments','新增评论')]:
   if isinstance(values.get(key),(int,float)):parts.append(label+f"{values[key]:,}")
  entry['summary']+=(' ' if entry['summary'] else '')+'视频号账号当日：'+'、'.join(parts)+'。这是账号整天的数据，与单条作品累计值分开查看。'
 return sorted(result,key=lambda x:x['day'],reverse=True)

def attach(app,core):
 root=core.ROOT;tikhub=TikHub(core.DATA/'connections');zone=timezone(timedelta(hours=8));research_lock=threading.Lock()
 def latest(kind,default):
  rows=core.listing(kind);return rows[0] if rows else default
 def research_config():return validate_config(latest('research_config',{}))
 def output_ready(p):
  out=p.get('output')
  if not out:return False
  if out.get('kind')=='finished_video':
   file=(core.DATA/out['file']).resolve()
   if not file.is_relative_to(core.DATA.resolve()) or not file.is_file():return False
   sha=hashlib.sha256()
   with file.open('rb') as stream:
    for block in iter(lambda:stream.read(1024*1024),b''):sha.update(block)
   return sha.hexdigest()==out.get('sha256')
  return out.get('edit_hash')==core.edit_hash(p)
 def collect(kind='all',selected_platform='all'):
  if not research_lock.acquire(blocking=False):raise ValueError('上一批还在查询，请等它完成后查看，避免重复花额度')
  try:return collect_serial(kind,selected_platform)
  finally:research_lock.release()
 def collect_serial(kind='all',selected_platform='all'):
  requested_kind=kind;config=research_config();rows=[];errors=[];today=datetime.now(zone).date().isoformat()
  with core.LOCK:
   used=sum(int(r.get('calls',0)) for r in core.listing('research_run') if r.get('day')==today)
   calls=[c for c in plan(config,kind) if selected_platform=='all' or c[2]==selected_platform][:max(0,config['daily_limit']-used)]
   if not calls:raise ValueError('今日查询次数已用完，或还没有关注内容')
   if not tikhub.status()['configured']:raise ValueError('请先连接你的TikHub账号')
   run=core.put('research_run',{'id':core.uid(),'day':today,'kind':kind,'calls':len(calls),'completed_calls':0,'outcomes':[],'state':'running','items':0,'errors':[],'created':core.now(),'config':config})
  outcomes=[]
  for route,payload,platform,kind,query in calls:
   try:
    response=tikhub.call(route,payload);parsed=normalize(response,platform,kind,query);batch_at=core.now()
    for row in parsed:
     item={**row,'source_id':row['id'],'id':core.digest({'content':row['id'],'kind':kind,'day':today})[:24],'collected_day':today,'run_id':run['id'],'batch_id':run['id']+':'+route,'collected_at':batch_at};core.put('research_item',item);rows.append(item)
    # Structure-only diagnostics contain no headers, secrets, URLs or user-info payload.
    def shape(v,depth=0):
     if depth>3:return type(v).__name__
     if isinstance(v,dict):return {k:shape(x,depth+1) for k,x in list(v.items())[:18] if not any(s in k.lower() for s in ['token','key','auth','cookie'])}
     if isinstance(v,list):return [shape(v[0],depth+1)] if v else []
     return type(v).__name__
    outcomes.append({'platform':platform,'kind':kind,'query':query,'state':'success' if parsed else 'empty','items':len(parsed),'route':route,'shape':shape(response.get('data',response))})
   except ValueError as e:
    errors.append({'platform':platform,'message':str(e)});outcomes.append({'platform':platform,'kind':kind,'query':query,'state':'failed','items':0,'route':route})
   core.patch('research_run',run['id'],{'completed_calls':len(outcomes),'items':len(rows),'outcomes':outcomes,'errors':errors})
  core.patch('research_run',run['id'],{'state':'completed' if not errors else 'partial','items':len(rows),'errors':errors})
  if requested_kind=='all' and selected_platform=='all' and rows:core.put('classroom_clock',{'id':today+':research','day':today,'kind':'research','origin':'manual_or_scheduled_collection','run_id':run['id'],'created':core.now()})
  if not rows and errors:raise ValueError('各平台查询暂未成功，没有导入虚构内容。请检查TikHub连接与额度。')
  return {'items':len(rows),'calls':len(calls),'errors':errors,'note':'视频号、公众号、小红书只展示实际搜索或账号内容，不标成全站热榜。'}
 def douyin_pipeline():
  import requests
  base='http://127.0.0.1:'+os.getenv('WORKBENCH_ANALYTICS_PORT','8770')+'/bridge'
  try:state=requests.get(base+'/state',timeout=10).json()
  except requests.RequestException:raise ValueError('数据连接没有启动，请先完成一次连接设置') from None
  if not state.get('status',{}).get('acknowledged'):raise ValueError('先在数据连接说明里由本人启用一次，再登录；之后可以自动收回')
  token=state['token']
  detail_warnings=[]
  for action in ['sync','details','export','import']:
   response=requests.post(base+'/actions/'+action,json={},headers={'X-Analytics-Token':token},timeout=20)
   if not response.ok:raise ValueError('后台数据更新未完成，请查看连接状态')
   job=response.json();deadline=time.monotonic()+450
   while job.get('state')=='running' and time.monotonic()<deadline:
    time.sleep(2);job=core.get('job',job['id'])
   if job.get('state')!='completed':
    if action=='details':detail_warnings.append('观看详情这次没有完整返回，先更新实际读到的播放互动');continue
    raise ValueError(job.get('message','后台数据暂未完成，未填入虚构数值'))
  return {'status':'completed','days':len(daily_reports(core.listing('metric'),core.listing('project'))),'platform':'douyin','warnings':detail_warnings}
 def analytics_pipeline():
  results=[]
  for platform,fn in [('douyin',douyin_pipeline),('tencent',lambda:core.PLATFORM_DATA['channels']())]:
   try:results.append({'platform':platform,'result':fn()})
   except Exception as e:results.append({'platform':platform,'error':str(e)})
  if all('error' in x for x in results):raise ValueError('；'.join(x['platform']+'：'+x['error'] for x in results))
  return {'platforms':results,'note':'只写入实际取得的记录；请核对各平台是否单独通过。'}
 @app.get('/api/classroom/status')
 def status():
  return {'version':VERSION,'research':tikhub.status(),'workspaces':core.listing('workspace'),'workbuddy_tasks':core.listing('learning_task')[:30],'model_connected':bool(__import__('os').getenv('WORKBENCH_MODEL_BASE_URL') and __import__('os').getenv('WORKBENCH_MODEL')),'schedule':latest('classroom_schedule',{'id':'main','research_enabled':False,'analytics_enabled':False,'time':'09:00'}),'research_config':research_config(),'last_research_run':latest('research_run',None)}
 @app.post('/api/classroom/tikhub/connect')
 async def connect(r:Request):
  d=await r.json()
  try:return tikhub.connect(d.get('key',''))
  except ValueError as e:raise HTTPException(400,str(e))
 @app.post('/api/classroom/research/config')
 async def configure(r:Request):
  try:return core.put('research_config',validate_config(await r.json()))
  except (ValueError,TypeError) as e:raise HTTPException(400,str(e))
 @app.post('/api/classroom/research/update')
 async def research_update(r:Request):
  d=await r.json();kind=d.get('kind','all');platform=d.get('platform','all')
  if kind not in ['all','keyword','account','hot']:raise HTTPException(400,'请选择精选、账号动态或热榜')
  if platform!='all' and platform not in PLATFORMS:raise HTTPException(400,'请选择支持的平台')
  return core.job('找我关注的新内容','research',lambda _:collect(kind,platform))
 @app.get('/api/classroom/research/results')
 def research_results():return {'items':core.listing('research_item')[:150],'runs':core.listing('research_run')[:10]}
 @app.post('/api/classroom/research/reparse')
 def reparse_research():
  cache=core.DATA/'research-cache';today=datetime.now(zone).date().isoformat();count=0
  for path in sorted(cache.glob('*.json'))[:100]:
   meta=json.loads(path.read_text(encoding='utf-8'));stored=datetime.fromisoformat(meta['stored_at']).astimezone(zone)
   if stored.date().isoformat()!=today:continue
   route=meta['route'];platform,suffix=route.rsplit('_',1)
   if platform not in PLATFORMS or suffix not in ['search','hot','account']:continue
   kind={'search':'keyword','hot':'hot','account':'account'}[suffix];query=meta['payload'].get('keyword') or meta['payload'].get('query') or (PLATFORMS[platform]+'热榜' if kind=='hot' else '关注作者')
   encrypted=path.with_suffix('.dpapi')
   if encrypted.stat().st_size>9_000_000:continue
   response=json.loads(protect(encrypted.read_bytes(),True))
   for row in normalize(response,platform,kind,query):
    core.put('research_item',{**row,'source_id':row['id'],'id':core.digest({'content':row['id'],'kind':kind,'day':today})[:24],'collected_day':today,'batch_id':path.stem+':'+meta['stored_at'],'collected_at':stored.isoformat(),'reparsed_at':core.now()});count+=1
  return {'items':count,'calls':0,'note':'只重新整理本机已有响应，没有调用外部接口或消耗新的查询次数。'}
 @app.get('/api/classroom/research/feed')
 def research_feed(day:str=''):
  today=datetime.now(zone).date().isoformat();day=day or today
  try:datetime.strptime(day,'%Y-%m-%d')
  except ValueError:raise HTTPException(400,'请选择正确的日期')
  cfg=research_config();allrows=core.listing('research_item');items=[x for x in allrows if x.get('normalization_version',0)>=3 and x.get('collected_day',str(x.get('collected_at',''))[:10])==day];runs=[x for x in core.listing('research_run') if x.get('day')==day];schedule=latest('classroom_schedule',{})
  used=sum(int(x.get('calls',0)) for x in core.listing('research_run') if x.get('day')==today)
  boards=[]
  for p in HOT_PLATFORMS:
   board=[x for x in items if x['platform']==p and x['kind']=='hot'];last=next((o for r in runs for o in r.get('outcomes',[]) if o['platform']==p and o['kind']=='hot'),None)
   boards.append({'platform':p,'name':PLATFORMS[p]+('热门视频' if p=='bilibili' else '热榜'),'items':ranked_board(board,p),'last_outcome':last,'enabled':cfg['include_hot'] and p in cfg['hot_platforms']})
  chosen=curate(items,cfg,day);account_rows=[x for x in items if x['kind']=='account'];account_rows.sort(key=lambda x:published_time(x.get('published_at')).timestamp() if published_time(x.get('published_at')) else 0,reverse=True)
  cutoff=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=zone)-timedelta(days=30);recent_accounts=[x for x in account_rows if not published_time(x.get('published_at')) or published_time(x['published_at'])>=cutoff]
  return {'day':day,'today':today,'available_days':sorted(set([today]+[x.get('collected_day',str(x.get('collected_at',''))[:10]) for x in allrows]+[r.get('day',today) for r in core.listing('research_run')]),reverse=True)[:30],'selected':chosen,'keyword_items':[x for x in items if x['kind']=='keyword'][:500],'account_items':recent_accounts[:150],'account_older_count':len(account_rows)-len(recent_accounts),'boards':boards,'runs':runs[:15],'used_calls':used,'remaining_calls':max(0,cfg['daily_limit']-used),'config':cfg,'schedule':schedule,'platforms':PLATFORMS,'hot_platforms':HOT_PLATFORMS,'plan':[{'platform':p,'kind':k,'query':q} for _,_,p,k,q in plan(cfg)][:max(0,cfg['daily_limit']-used)],'selection_note':'先看关注词是否贴题，再看新近内容与可见互动；各平台轮流挑选，最多'+str(cfg['daily_count'])+'条。这是选题参考，不保证内容质量或获客效果。'}
 @app.post('/api/classroom/research/{ident}/idea')
 def use_as_idea(ident:str):
  row=core.get('research_item',ident)
  pid=core.WORKFLOW['settings']().get('profile_id')
  if not pid:raise HTTPException(409,'先在设置选择本次业务，再留下给它的选题参考')
  existing=next((x for x in core.listing('idea') if x.get('source_research_id')==ident and x.get('profile_id')==pid),None)
  return existing or core.put('idea',{'id':core.uid(),'profile_id':pid,'source_research_id':ident,'title':row['title'][:300],'url':row['url'],'source':PLATFORMS[row['platform']]+' · '+row.get('author',''),'notes':'这条来源对我的业务有什么用？哪些内容我能用自己的经历说明？','source_text':row['title'],'status':'待判断','created':core.now()})
 @app.post('/api/classroom/learning/tasks')
 async def learning_task(r:Request):
  d=await r.json();step=int(d.get('step',0))
  if step not in range(1,13):raise HTTPException(400,'请先选择要做哪一项')
  if not str(d.get('message','')).strip():raise HTTPException(400,'先说说你想做什么')
  task={'id':core.uid(),'step':step,'profile_id':str(d.get('profile_id','')),'message':str(d['message'])[:12000],'state':'waiting_workbuddy','created':core.now(),'output':None}
  folder=core.DATA/'learner-requests';folder.mkdir(exist_ok=True)
  (folder/(task['id']+'.json')).write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding='utf-8')
  return core.put('learning_task',task)
 @app.post('/api/classroom/workspaces')
 async def workspace(r:Request):
  d=await r.json();path=Path(str(d.get('path',''))).expanduser()
  if not path.is_absolute() or not path.is_dir():raise HTTPException(400,'请提供这次业务资料所在的文件夹')
  profile_id=str(d.get('profile_id',''))
  if profile_id:
   profile=core.get('project',profile_id)
   if not any(s.get('kind')=='business_memory' and s.get('owner')==d.get('owner') for s in profile.get('sources',[])):raise HTTPException(400,'业务文件夹与当前资料归属不一致')
  return core.put('workspace',{'id':core.digest(str(path.resolve()))[:16],'path':str(path.resolve()),'owner':str(d.get('owner','本人业务'))[:100],'profile_id':profile_id,'created':core.now()})
 @app.get('/api/classroom/discover')
 def discover():
  # Reuse existing imported results first. Never scan all disks or other learners.
  saved=[{'project_id':p['id'],'title':p['title'],'sources':len(p.get('sources',[])),'memory':any(s.get('kind')=='business_memory' for s in p.get('sources',[]))} for p in core.listing('project') if p.get('sources')]
  files=[]
  for workspace in core.listing('workspace'):
   folder=Path(workspace['path']).resolve()
   skipped={'老板IP工作台','runtime','history','internal','_internal','packages','node_modules','__pycache__','.venv','venv'};scanned=0
   for parent,directories,names in os.walk(folder,followlinks=False):
    current=Path(parent);depth=len(current.relative_to(folder).parts)
    directories[:]=[] if depth>=2 else [name for name in directories if name not in skipped and not name.startswith('.') and not (current/name).is_symlink() and not getattr(current/name,'is_junction',lambda:False)()]
    for name in names:
     scanned+=1
     if len(files)>=80 or scanned>500:break
     path=current/name
     if path.is_symlink() or name in ['project.json','memory.json','interview-state.json','learner-reply.txt','selection-reply.txt']:continue
     if path.suffix.lower() in ['.html','.json','.md','.txt','.png','.jpg','.pdf','.docx'] and path.stat().st_size<=6*1024*1024:files.append({'name':name,'path':str(path),'workspace':workspace['id'],'owner':workspace['owner'],'profile_id':workspace.get('profile_id','')})
    if len(files)>=80 or scanned>500:break
  return {'saved':saved,'files':files,'note':'只查这台工作台已保存的资料和本人指定过的业务文件夹。'}
 @app.post('/api/classroom/discover/import')
 async def import_discovered(r:Request):
  import base64,mimetypes
  d=await r.json();p=core.get('project',str(d.get('project_id','')));memory=next((s for s in p.get('sources',[]) if s.get('kind')=='business_memory'),None)
  if not memory:raise HTTPException(400,'先确认这次资料属于哪项业务')
  allowed={f['path']:f for f in discover()['files'] if f['owner']==memory['owner'] and f['profile_id']==p['id']};requested=d.get('paths',[])
  if not isinstance(requested,list) or len(requested)>50 or any(path not in allowed for path in requested):raise HTTPException(400,'只能接入本次业务指定文件夹中实际找到的成品')
  next_memory=json.loads(json.dumps(memory));imported=0
  for name in requested:
   path=Path(name);raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();suffix=path.suffix.lower();label='其他成品'
   for word,value in [('客户','客群卡'),('客群','客群卡'),('选题','三圈选题'),('人设','人设卡'),('视频稿','完整脚本'),('文稿','完整脚本'),('脚本','完整脚本')]:
    if word in path.name:label=value;break
   topic='共用资料'
   if any(a['sha256']==sha and a['module']==label and a['topic']==topic for a in next_memory['assets']):continue
   encoding='text' if suffix in ['.html','.json','.md','.txt'] else 'base64'
   if suffix=='.json':
    try:source=json.loads(raw.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise HTTPException(400,'文件无法读取：'+path.name) from None
    if isinstance(source,dict) and source.get('mode') in ['real','fictional_demo'] and source['mode']!=memory['mode']:raise HTTPException(400,'课堂演示与真实业务不能混入同一份资料')
   version=1+max([a['version'] for a in next_memory['assets'] if (a['name'],a['module'],a['topic'])==(path.name,label,topic)]or[0])
   next_memory['assets'].append({'id':core.uid(),'name':path.name,'module':label,'topic':topic,'size':len(raw),'sha256':sha,'mime':mimetypes.guess_type(path.name)[0]or'application/octet-stream','encoding':encoding,'content':raw.decode('utf-8') if encoding=='text' else base64.b64encode(raw).decode(),'version':version,'created_at':core.now(),'review':'pending'});imported+=1
  if len(json.dumps(next_memory,ensure_ascii=False).encode())>MAX_PROFILE_BYTES:raise HTTPException(400,'这项业务资料超过64MB，请按不同业务分开')
  with core.LOCK:
   if core.get('project',p['id']).get('revision')!=p.get('revision'):raise HTTPException(409,'资料刚有新修改，旧说明已保留，请再找一次已有成果')
   saved=core.patch('project',p['id'],{'sources':[next_memory if s.get('kind')=='business_memory' else s for s in p['sources']]})
  return {'imported':imported,'project_id':saved['id'],'note':'原件已接住，内容仍待本人核对。'}
 def review_prefs():
  row=next((item for item in core.listing('review_board_prefs') if item.get('id')=='main'),None)
  return {'weekly_goal':None if not row else row.get('weekly_goal'),'checked':[] if not row else list(row.get('checked') or [])}
 def review_board(days=7,platform='all'):
  if days not in (1,7) or platform not in ('all','douyin','tencent'):raise HTTPException(400,'请选择昨天或近7日，平台选抖音、视频号或全部')
  return build_review_board(core.listing('metric'),core.listing('project'),core.listing('account_daily'),review_prefs(),days=days,platform=platform)
 @app.get('/api/classroom/reports')
 def reports():
  metrics,projects,accounts=core.listing('metric'),core.listing('project'),core.listing('account_daily')
  return {'days':daily_reports(metrics,projects,accounts)[:31],'schedule':latest('classroom_schedule',{'time':'09:00','analytics_enabled':False}),'note':'只展示实际取得的后台记录。账号每日新增与作品累计值分开，不混算。','board':build_review_board(metrics,projects,accounts,review_prefs())}
 @app.get('/api/classroom/reports/board')
 def reports_board(days:int=7,platform:str='all'):return review_board(days,platform)
 @app.post('/api/classroom/reports/board')
 async def reports_board_save(r:Request,days:int=7,platform:str='all'):
  try:prefs=clean_prefs(await r.json(),review_prefs())
  except ValueError as e:raise HTTPException(400,str(e))
  core.put('review_board_prefs',{'id':'main',**prefs})
  return review_board(days,platform)
 @app.post('/api/classroom/reports/update')
 def reports_update():return core.job('收回我的后台数据','analytics-pipeline',lambda _:analytics_pipeline())
 @app.post('/api/classroom/schedule')
 async def schedule(r:Request):
  d=await r.json();at=str(d.get('time','09:00'))
  if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',at):raise HTTPException(400,'请选择准确时间')
  previous=latest('classroom_schedule',{'id':'main','research_enabled':False,'analytics_enabled':False,'time':'09:00'});kind=d.get('kind')
  next_schedule={**previous,'timezone':'Asia/Shanghai','note':'本机工作台保持打开时运行；关闭期间不会假报执行，重新打开后会补查当天未运行的任务。'}
  if kind in ['research','analytics']:
   next_schedule[kind+'_time']=at;next_schedule[kind+'_enabled']=bool(d.get(kind+'_enabled'))
  else:
   next_schedule.update(time=at,research_time=at,analytics_time=at,research_enabled=bool(d.get('research_enabled')),analytics_enabled=bool(d.get('analytics_enabled')))
  return core.put('classroom_schedule',next_schedule)
 @app.post('/api/projects/{ident}/finished-video')
 async def finished_video(ident:str,file:UploadFile=File(...)):
  p=core.get('project',ident);suffix=Path(file.filename or '').suffix.lower()
  if suffix not in ['.mp4','.mov','.webm','.mkv']:raise HTTPException(400,'请上传剪辑好的MP4、MOV、WEBM或MKV视频')
  folder=core.project_dir(ident)/'finished';folder.mkdir(exist_ok=True);destination=folder/(core.uid()+suffix);sha=hashlib.sha256();size=0
  with destination.open('wb') as handle:
   while block:=await file.read(1024*1024):
    size+=len(block)
    if size>4*1024**3:raise HTTPException(413,'视频超过4GB')
    handle.write(block);sha.update(block)
  try:info=json.loads(core.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',destination]))
  except Exception:raise HTTPException(400,'无法读取这个视频，请检查文件能否正常播放') from None
  video=next((s for s in info['streams'] if s.get('codec_type')=='video'),None)
  if not video:raise HTTPException(400,'文件没有可发布的视频画面')
  final={'kind':'finished_video','file':str(destination.relative_to(core.DATA)).replace('\\','/'),'sha256':sha.hexdigest(),'duration':float(info['format']['duration']),'size':size,'width':video['width'],'height':video['height'],'edit_hash':'finished:'+sha.hexdigest(),'uploaded_at':core.now()}
  return core.patch('project',ident,{'output':final,'status':'待发布','publish_preparation':None})
 @app.post('/api/projects/{ident}/prepare-delivery')
 def prepare_delivery(ident:str):
  p=core.get('project',ident)
  if not output_ready(p):raise HTTPException(409,'先上传一份剪辑好的成片，或检查视频文件是否改变')
  def work(job):
   from semantic_delivery import prepare
   return prepare(core,ident)
  return core.job('理解视频并准备两平台发布信息',ident,work)
 @app.on_event('startup')
 def start_clock():
  def loop():
   while True:
    try:
     schedule=latest('classroom_schedule',{});now=datetime.now(zone);day=now.date().isoformat()
     for name,enabled,callback in [('research',schedule.get('research_enabled'),collect),('analytics',schedule.get('analytics_enabled'),analytics_pipeline)]:
      key=day+':'+name
      if enabled and now.strftime('%H:%M')>=schedule.get(name+'_time',schedule.get('time','09:00')) and not any(r['id']==key for r in core.listing('classroom_clock')):
       core.put('classroom_clock',{'id':key,'day':day,'kind':name,'created':core.now()});core.job('每天更新 · '+name,'clock-'+name,lambda _,fn=callback:fn())
    except Exception:pass
    time.sleep(30)
  threading.Thread(target=loop,daemon=True).start()
 return {'output_ready':output_ready,'collect':collect,'analytics_pipeline':analytics_pipeline,'tikhub':tikhub,'research_config':research_config}
