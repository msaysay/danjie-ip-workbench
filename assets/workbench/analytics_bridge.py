"""Local adapter to an unmodified, separately licensed douyin-mcp CLI."""
from __future__ import annotations
import json,os,secrets,sqlite3,subprocess,threading,uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import server as core

ROOT=Path(__file__).resolve().parent
REPO=ROOT/'vendor/douyin-mcp'
PYTHON=REPO/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
STATE=ROOT/'data/analytics/douyin'
STATE.mkdir(parents=True,exist_ok=True)
TOKEN=secrets.token_urlsafe(32)
ORIGINS=core.UI_ORIGINS
APP=FastAPI(title='Content Workbench Analytics Adapter',docs_url=None,redoc_url=None)
APP.add_middleware(CORSMiddleware,allow_origins=ORIGINS,allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Content-Type','X-Analytics-Token'])

def cli_env():
    safe={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ['KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL','COOKIE','AUTH']) and not k.upper().startswith('CODEX_')}
    return {**safe,'PYTHONUTF8':'1','DATA_DIR':str(STATE),'DOUYIN_BROWSER_PROFILE_DIR':str(STATE/'browser-profile'),
        'DOUYIN_BROWSER_CHANNEL':('msedge' if os.name=='nt' else 'chromium'),'DOUYIN_BROWSER_HEADLESS':'false','DOUYIN_BROWSER_AUTO_CLOSE':'true',
        'TRANSCRIPT_INGESTION_ENABLED':'false','MCP_TRANSPORT':'stdio','OTEL_SDK_DISABLED':'true','DO_NOT_TRACK':'1'}

def run_cli(arguments,timeout=180):
    if not PYTHON.exists():raise RuntimeError('数据模块尚未安装')
    p=subprocess.run([str(PYTHON),'-m','douyin_creator_mcp.cli',*arguments],cwd=REPO,env=cli_env(),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:payload=json.loads(p.stdout)
    except ValueError:raise RuntimeError('数据模块未返回有效 JSON：'+p.stderr[-1000:])
    if p.returncode or not payload.get('ok'):raise RuntimeError(json.dumps(payload,ensure_ascii=False)[-2500:])
    return payload

def cached():
    try:return core.get('analytics','douyin')
    except HTTPException:return {'id':'douyin','state':'未诊断','acknowledged':False}

@APP.middleware('http')
async def local_request(request:Request,call_next):
    if request.headers.get('host','').split(':')[0] not in ['127.0.0.1','localhost','testserver']:return JSONResponse({'detail':'仅限本机'},403)
    origin=request.headers.get('origin')
    if origin and origin not in ORIGINS:return JSONResponse({'detail':'来源不允许'},403)
    if request.method not in ['GET','HEAD','OPTIONS'] and request.headers.get('x-analytics-token')!=TOKEN:return JSONResponse({'detail':'请重新打开数据模块'},403)
    return await call_next(request)

@APP.get('/bridge/health')
def health():return {'component':'danjie-analytics','data_dir':str(STATE),'installed':PYTHON.exists()}
@APP.get('/bridge/state')
def state():return {'token':TOKEN,'installed':PYTHON.exists(),'status':cached(),'jobs':[j for j in core.listing('job') if j['target']=='analytics-douyin'][:15]}
@APP.get('/bridge/notice')
def notice():
    return {'title':'上游工具的使用前确认','text':(REPO/'PLATFORM_COMPLIANCE.md').read_text(encoding='utf-8'),'source':'https://github.com/Kuhakucai/douyin-mcp/blob/53c888a5e1d83ea70978e71432ad8774707d69b7/PLATFORM_COMPLIANCE.md'}

def diagnostics():
    doctor=run_cli(['doctor']);status=run_cli(['status'])
    compliance=status.get('platform_compliance',{})
    result={'id':'douyin','state':'离线诊断通过' if doctor.get('ready') else '需检查环境','doctor':doctor,'upstream_status':status,
        'acknowledged':bool(compliance.get('acknowledged')),'checked_at':core.now(),'live_verified':False}
    return core.put('analytics',result)

def number(value,count=False):
    if value is None or value=='':return None
    try:
        n=float(value)
        if not __import__('math').isfinite(n) or n<0:return None
        return int(n) if count and n.is_integer() else n
    except (TypeError,ValueError):return None

def normalize_export(payload,identity=None,quality=None):
    identity=identity or {};quality=quality or {};rows=[];skipped=0
    for row in payload.get('rows',[]):
        local=str(row.get('video_id') or '')
        if not local or not row.get('captured_at'):skipped+=1;continue
        observed=datetime.fromisoformat(str(row['captured_at']).replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
        actual=str(identity.get(local) or '')
        platform_id=actual if actual.isdigit() else None
        source=str(row.get('source') or 'unknown')
        q=quality.get((local,row['captured_at'],source),{})
        rows.append({'source_local_id':local,'post_id':platform_id or 'local:'+local,'identity_status':'platform_id_confirmed' if platform_id else 'local_identity_only',
            'title':str(row.get('title') or '未命名作品'),'platform':'douyin','url':'https://www.douyin.com/video/'+platform_id if platform_id else '',
            'observed_at':observed,'window_hours':None,'metric_scope':'lifetime','published_at':row.get('publish_time'),
            'views':number(row.get('play_count'),True),'likes':number(row.get('like_count'),True),'comments':number(row.get('comment_count'),True),
            'shares':number(row.get('share_count'),True),'saves':number(row.get('collect_count'),True),'leads':None,'gmv':None,'profit':None,'ad_spend':None,'refund_amount':None,
            'completion_rate':number(row.get('completion_rate')),'five_second_completion_rate':number(row.get('five_second_completion_rate')),
            'average_watch_duration_seconds':number(row.get('average_watch_duration_seconds')),'exposure_count':number(row.get('exposure_count'),True),
            'follower_gain':number(row.get('follower_gain'),True),'snapshot_source':source,'quality':q.get('quality','unknown'),
            'missing_reasons':q.get('missing_reasons',{}),'provenance':'douyin-mcp/'+source})
    return {'rows':rows,'skipped_without_snapshot':skipped,'scope_note':'累计快照；period 按采集时间筛选，不能当成发布后观察窗口。'}

def export_normalized():
    path=STATE/'exports'/('workbench-'+uuid.uuid4().hex+'.json')
    result=run_cli(['export','--format','json','--period','all','--output',str(path)])
    payload=json.loads(path.read_text(encoding='utf-8'));identity={};quality={}
    db=STATE/'douyin.sqlite'
    if db.exists():
        conn=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)
        try:
            identity={str(k):v for k,v in conn.execute('SELECT id,COALESCE(item_id,video_id) FROM videos')}
            for local,at,source,q,missing in conn.execute('SELECT video_id,captured_at,source,quality,missing_reason_json FROM video_metric_snapshots'):
                try:missing=json.loads(missing or '{}')
                except ValueError:missing={}
                quality[(str(local),at,source)]={'quality':q,'missing_reasons':missing}
        finally:conn.close()
    out=normalize_export(payload,identity,quality);out['created_at']=core.now();out['upstream_row_count']=result.get('row_count',0)
    (STATE/'normalized-export.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'rows':len(out['rows']),'skipped':out['skipped_without_snapshot'],'scope_note':out['scope_note']}

def preview():
    path=STATE/'normalized-export.json'
    if not path.exists():return {'rows':[],'total':0,'note':'尚无导出快照'}
    data=json.loads(path.read_text(encoding='utf-8'));return {'rows':data['rows'][:20],'total':len(data['rows']),'note':data['scope_note']}

@APP.get('/bridge/preview')
def preview_route():return preview()

def import_snapshots():
    data=json.loads((STATE/'normalized-export.json').read_text(encoding='utf-8'))
    projects={p.get('analytics_source_key'):p for p in core.listing('project') if p.get('analytics_source_key')}
    selected=[];ids=[]
    # Bound the first import to 20 distinct works; retain all snapshots of those works.
    for row in data['rows']:
        ident=row['source_local_id']
        if ident not in ids and len(ids)<20:ids.append(ident)
        if ident in ids:selected.append(row)
    for row in selected:
        source_key='douyin-mcp:'+row['source_local_id']
        p=projects.get(source_key)
        if not p:
            p=core.put('project',{'id':core.uid(),'title':'复盘 · '+row['title'],'brief':'来自本人创作者中心的累计快照，先核对数据覆盖率与作品年龄。','script':'','status':'复盘',
                'sources':[{'title':row['title'],'url':row['url'],'notes':'数据来源 '+row['provenance']}],'segments':[],'platform_copy':{},'analytics_source_key':source_key,'created':core.now()})
            projects[source_key]=p
        record={**row,'project_id':p['id'],'imported_at':core.now()}
        record['id']=core.digest({k:record[k] for k in ['platform','post_id','observed_at','snapshot_source']})[:24]
        core.put('metric',record)
    return {'imported_snapshots':len(selected),'distinct_works':len(ids),'source':'local authenticated browser DOM','metric_scope':'lifetime'}

@APP.post('/bridge/actions/{action}')
async def action_route(action:str,r:Request):
    if action not in ['doctor','acknowledge','login','sync','details','export','import']:raise HTTPException(404)
    body=await r.json()
    if action=='acknowledge' and body.get('confirmation')!='我已阅读并确认':raise HTTPException(409,'须由使用者阅读上游说明后明确确认')
    if action in ['login','sync','details'] and not cached().get('acknowledged'):raise HTTPException(409,'请先阅读并确认上游工具的说明；发布账号登录不能替代此模块的确认和专用登录')
    def work(j):
        if action=='doctor':return diagnostics()
        if action=='acknowledge':
            run_cli(['acknowledge-platform-risk','--yes']);return diagnostics()
        if action=='login':result=run_cli(['login','--timeout','180'],timeout=230)
        elif action=='sync':result=run_cli(['sync','--mode','visible'],timeout=300)
        elif action=='details':result=run_cli(['details','--recent-limit','5','--batch-size','5','--mode','visible'],timeout=300)
        elif action=='export':return export_normalized()
        else:return import_snapshots()
        status=run_cli(['status']);compliance=status.get('platform_compliance',{})
        core.patch('analytics','douyin',{'upstream_status':status,'acknowledged':bool(compliance.get('acknowledged')),'last_action':action,'last_result':result,'checked_at':core.now(),
            'live_verified':action in ['sync','details'] and result.get('status') in ['completed','partial']})
        return result
    return core.job('抖音数据 · '+action,'analytics-douyin',work)

if __name__=='__main__':
    import uvicorn
    uvicorn.run(APP,host='127.0.0.1',port=int(os.getenv('WORKBENCH_ANALYTICS_PORT','8770')))
