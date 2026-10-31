import hashlib,json
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException

def attach(app,core):
 def channels():
  a=next((a for a in core.listing('account') if a['platform']=='tencent'),None)
  if not a:raise ValueError('先在发布视频里添加并登录自己的视频号账号')
  raw=core.run([core.SAUPY,core.ROOT/'channels_data.py',a['alias']],cwd=core.SAU,timeout=100)
  marker=next((s for s in raw.splitlines() if s.startswith('WORKBENCH_RESULT=')),None)
  if not marker:raise ValueError('视频号读取未返回完整记录，未导入数据')
  result=json.loads(marker.split('=',1)[1]);stamp=core.now()
  overview=result.get('overview',{});day=(datetime.now(timezone(timedelta(hours=8)))-timedelta(days=1)).date().isoformat()
  core.put('platform_data_connection',{'id':'tencent','platform':'tencent','account_id':a['id'],'state':result['state'],'message':result['message'],'rows':len(result['items']),'checked_at':stamp,'overview':overview,'data_day':day if overview else None})
  if overview:core.put('account_daily',{'id':'tencent:'+a['id']+':'+day,'platform':'tencent','account_id':a['id'],'account_label':a['label'],'day':day,'observed_at':stamp,'scope':'account_day','source':'本人视频号后台昨日数据','values':overview})
  for row in result['items']:
   project=next((p for p in core.listing('project') if p.get('platform_post_ids',{}).get('tencent')==row['post_id']),None)
   identity='tencent:'+row['post_id']+':'+stamp[:10]
   core.put('metric',{'id':hashlib.sha256(identity.encode()).hexdigest()[:16],**row,'platform':'tencent','account':a['alias'],'project_id':project['id'] if project else None,'observed_at':stamp,'metric_scope':'lifetime','snapshot_source':'browser_list','provenance':'本人视频号后台当前页可见作品；累计快照，非当日新增','gmv':None,'profit':None,'ad_spend':None,'leads':None})
  if result['state'] not in ['verified','verified_empty','verified_overview']:raise ValueError(result['message'])
  return {'platform':'tencent','rows':len(result['items']),'message':result['message'],'overview':overview}
 @app.get('/api/platform-data')
 def state():return {'connections':core.listing('platform_data_connection'),'accounts':[{k:a.get(k) for k in ['id','platform','label','status','checked_at']} for a in core.listing('account') if a['platform'] in ['douyin','tencent']]}
 @app.post('/api/platform-data/tencent/update')
 def update():return core.job('检查并读取我的视频号数据','channels-data',lambda _:channels())
 return {'channels':channels}
