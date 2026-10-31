"""Sync only the explicitly chosen learner project into the local workbench.
No login cookies, API keys, private interview states, or global workspace scans.
"""
from pathlib import Path
import argparse,base64,hashlib,json,sys,uuid
from datetime import datetime,timezone
import urllib.request,urllib.error
from memory_limits import MAX_PROFILE_BYTES

class LocalResponse:
 def __init__(self,status,body):self.status_code=status;self.body=body;self.ok=200<=status<300
 def json(self):return json.loads(self.body.decode('utf-8'))
 def raise_for_status(self):
  if not self.ok:raise urllib.error.URLError('本机工作台暂未接通')
class LocalHTTP:
 RequestException=urllib.error.URLError
 @staticmethod
 def request(method,url,headers=None,json=None,timeout=10):
  if not url.startswith(BASE+'/'):raise ValueError('不向其他地址发送业务资料')
  body=__import__('json').dumps(json,ensure_ascii=False).encode('utf-8') if json is not None else None
  request=urllib.request.Request(url,data=body,headers={**(headers or {}),**({'Content-Type':'application/json'} if body is not None else {})},method=method)
  try:
   with urllib.request.urlopen(request,timeout=timeout) as response:
    raw=response.read(80*1024*1024+1)
    if len(raw)>80*1024*1024:raise ValueError('本机资料响应超过80MB，原资料未改动，请按业务分别接回')
    return LocalResponse(response.status,raw)
  except urllib.error.HTTPError as error:return LocalResponse(error.code,error.read(1024*1024))
 @classmethod
 def get(cls,url,**kwargs):return cls.request('GET',url,**kwargs)
 @classmethod
 def post(cls,url,**kwargs):return cls.request('POST',url,**kwargs)
 @classmethod
 def patch(cls,url,**kwargs):return cls.request('PATCH',url,**kwargs)
requests=LocalHTTP

from local_settings import api_base
BASE=api_base()
def sync(project,base=BASE):
 if base!=BASE:raise ValueError('仅支持这台电脑上的内容工作台')
 root=Path(project).resolve();state=json.loads((root/'project.json').read_text(encoding='utf-8-sig'))
 if state.get('schema') not in ['danjie-workbench/0.2.1','danjie-ip-workbench/0.1.0']:raise ValueError('请指定本人老板IP工作台项目，不是安装包目录')
 if state.get('mode') not in ['real','fictional_demo']:raise ValueError('资料性质不明确，先核对本人或课堂练习')
 packet=root/'memory/memory.json'
 if packet.exists():memory=json.loads(packet.read_text(encoding='utf-8-sig'))
 else:memory={'kind':'business_memory','schema':'danjie-business-memory/1','id':state['project_id'],'owner':state['student_ref'],'business':state['business'],'mode':state['mode'],'assets':[],'notes':[],'created_at':state.get('created_at','')}
 if (memory['owner'],memory['business'],memory['mode'])!=(state['student_ref'],state['business'],state['mode']):raise ValueError('项目与资料归属不一致，未同步')
 labels={1:'客群卡',2:'三圈选题',3:'当头一棒',4:'以理服人',5:'亮出绝活',6:'指条明路',7:'开场八式',8:'人设卡',9:'四行简介',10:'乾坤大挪移',11:'六脉神剑',12:'一题多讲'}
 mime={'.json':'application/json','.md':'text/markdown','.txt':'text/plain','.html':'text/html','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.pdf':'application/pdf','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
 # Only registered, public reading/handoff artifacts. Private module runtime is not scanned.
 skipped=[]
 for record in state.get('artifacts',{}).values():
  for role,info in record.get('files',{}).items():
   label_name=Path(str(info.get('source') or info.get('snapshot') or role)).name
   try:path=(root/info['snapshot']).resolve()
   except OSError:skipped.append(label_name+'：文件读不到');continue
   ext=path.suffix.lower()
   if path.is_symlink() or not path.is_file() or not path.is_relative_to(root):skipped.append(label_name+'：不在本次项目目录里');continue
   if ext not in mime:skipped.append(label_name+'：这种文件不接回');continue
   if path.stat().st_size>6*1024*1024:skipped.append(label_name+'：超过 6MB，没有接入');continue
   raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
   if sha!=info['sha256']:raise ValueError('原成果已改变，请按原模块核对后再登记')
   label=labels[record['step']];topic=state.get('topics',{}).get(record.get('topic_id','main'),{}).get('title','共用资料')
   if any(a['sha256']==sha and a['module']==label and a['topic']==topic for a in memory['assets']):continue
   name=Path(info.get('source',path.name)).name;encoding='text' if ext in ['.json','.html','.md','.txt'] else 'base64'
   version=1+max([a['version'] for a in memory['assets'] if (a['name'],a['module'],a['topic'])==(name,label,topic)]or[0])
   memory['assets'].append({'id':uuid.uuid4().hex,'name':name,'module':label,'topic':topic,'encoding':encoding,'content':raw.decode('utf-8') if encoding=='text' else base64.b64encode(raw).decode(),'size':len(raw),'sha256':sha,'mime':mime[ext],'version':version,'created_at':datetime.now(timezone.utc).isoformat(),'review':'pending'})
 if skipped:raise ValueError('有成果没有接入，本机项目和网页都没有改：'+'；'.join(skipped[:8]))
 for feedback in state.get('feedback',[]):
  if not feedback.get('message'):continue
  ident='feedback-'+feedback['id']
  if not any(n['id']==ident for n in memory['notes']):memory['notes'].append({'id':ident,'category':'correction','text':feedback['message'],'review':'pending','created_at':feedback['created_at']})
 if len(json.dumps(memory,ensure_ascii=False).encode())>MAX_PROFILE_BYTES:raise ValueError('本业务资料超过64MB，请按业务分开，不丢弃旧资料')
 def save_local():
  packet.parent.mkdir(exist_ok=True);temp=packet.with_suffix('.tmp');temp.write_text(json.dumps(memory,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(packet)
  index_folder=Path.home()/'Documents/蛋解内容工作台';index_folder.mkdir(parents=True,exist_ok=True);index_file=index_folder/'业务索引.json'
  index=json.loads(index_file.read_text(encoding='utf-8')) if index_file.exists() else {'schema':'danjie-owned-projects/1','projects':[]}
  entry={'project_id':state['project_id'],'name':state['name'],'owner':memory['owner'],'business':memory['business'],'mode':memory['mode'],'path':str(root),'updated_at':datetime.now(timezone.utc).isoformat()}
  index['projects']=[p for p in index['projects'] if p['project_id']!=entry['project_id']]+[entry]
  index_temp=index_file.with_suffix('.tmp');index_temp.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8');index_temp.replace(index_file)
 save_local()
 try:
  response=requests.get(base+'/state',timeout=8);response.raise_for_status();remote=response.json();headers={'x-workbench-token':remote['token']}
  existing=next((p for p in remote['projects'] if any(s.get('kind')=='business_memory' and (s.get('owner'),s.get('business'),s.get('mode'))==(memory['owner'],memory['business'],memory['mode']) for s in p.get('sources',[]))),None)
  if existing:
   old=next(s for s in existing['sources'] if s.get('kind')=='business_memory')
   for a in old['assets']:
    if not any((x['sha256'],x['module'],x['topic'])==(a['sha256'],a['module'],a['topic']) for x in memory['assets']):memory['assets'].append(a)
   memory['notes'].extend(n for n in old['notes'] if not any(x['id']==n['id'] for x in memory['notes']))
  else:
   response=requests.post(base+'/projects',headers=headers,json={'title':'我的资料｜'+memory['owner']+' · '+memory['business'],'brief':'来自本人WorkBuddy项目的已有成果和修改说明'},timeout=10);response.raise_for_status();existing=response.json()
  sources=[s for s in existing.get('sources',[]) if s.get('kind')!='business_memory']+[memory]
  if len(json.dumps(memory,ensure_ascii=False).encode())>MAX_PROFILE_BYTES:raise ValueError('网页与本机合并后超过64MB，原项目记忆已保留，请按业务拆开')
  response=requests.patch(base+'/projects/'+existing['id'],headers=headers,json={'sources':sources,'expected_revision':existing.get('revision',0)},timeout=30);response.raise_for_status()
  # Register this explicit project folder when the new classroom API is loaded.
  workspace=requests.post(base+'/classroom/workspaces',headers=headers,json={'path':str(root),'owner':memory['owner'],'profile_id':existing['id']},timeout=8)
 except requests.RequestException:raise ValueError('资料仍在本机项目里；网页工作台未连接成功，未假报同步完成') from None
 save_local()
 return {'project_id':existing['id'],'files':len(memory['assets']),'notes':len(memory['notes']),'workspace_registered':workspace.ok,'meaning':'已接入本机网页；不是WorkBuddy原生操作已验收的证明'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--project',required=True);a=p.parse_args()
 try:print(json.dumps(sync(a.project),ensure_ascii=False))
 except (ValueError,KeyError,OSError) as e:raise SystemExit(str(e))
