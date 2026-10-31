from pathlib import Path
import sys,json,argparse,uuid,datetime
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'assets/workbench';sys.path.insert(0,str(APP))
from workbuddy_sync import LocalHTTP,BASE
def main():
 a=argparse.ArgumentParser();a.add_argument('--owner',required=True);a.add_argument('--business',required=True);a.add_argument('--mode',choices=['real','fictional_demo'],default='real');p=a.parse_args()
 session=LocalHTTP.get(BASE+'/local-session').json();headers={'x-workbench-token':session['token']}
 def post(path,data):
  r=LocalHTTP.post(BASE+path,json=data,headers=headers,timeout=30);r.raise_for_status();return r.json()
 def patch(path,data):
  r=LocalHTTP.patch(BASE+path,json=data,headers=headers,timeout=30);r.raise_for_status();return r.json()
 state=LocalHTTP.get(BASE+'/state',timeout=30).json();project=None
 for existing in state['projects']:
  memory=next((m for m in existing.get('sources',[]) if m.get('kind')=='business_memory'),None)
  if memory and all(memory[k]==v for k,v in [('owner',p.owner),('business',p.business),('mode',p.mode)]):project=existing;break
 if project is None:
  project=post('/projects',{'title':p.business,'brief':''});stamp=datetime.datetime.now().astimezone().isoformat()
  memory={'kind':'business_memory','schema':'danjie-business-memory/1','id':uuid.uuid4().hex[:16],'owner':p.owner,'business':p.business,'mode':p.mode,'assets':[],'notes':[],'created_at':stamp}
  project=patch('/projects/'+project['id'],{'sources':[memory],'expected_revision':project['revision']})
 post('/workflow/settings',{'profile_id':project['id'],'enabled':False,'count':5,'time':'08:30'});post('/experience/business/prepare',{})
 print(json.dumps({'profile_id':project['id'],'owner':p.owner,'business':p.business,'mode':p.mode,'note':'空白业务已就绪，未导入其他人的作业或连接。'},ensure_ascii=False))
if __name__=='__main__':main()
