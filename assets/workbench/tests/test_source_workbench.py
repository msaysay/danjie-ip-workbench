import sys,json,hashlib,subprocess,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
import server as s

class SourceWorkbenchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=s.DATA,s.DB;s.DATA=Path(self.temp.name);s.DB=s.DATA/'test.sqlite3'
  with s.connect() as c:c.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
  self.client=TestClient(s.app);self.headers={'x-workbench-token':s.TOKEN}
 def tearDown(self):s.DATA,s.DB=self.old;self.temp.cleanup()
 def post(self,path,data):return self.client.post('/api'+path,json=data,headers=self.headers)
 def profile(self):
  m={'kind':'business_memory','schema':'danjie-business-memory/1','id':'memory','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','assets':[],'notes':[]}
  s.put('project',{'id':'p','title':'测试业务','sources':[m],'segments':[]});s.put('workflow_settings',{'id':'main','profile_id':'p','time':'08:30','count':5,'enabled':False});return m
 def test_blank_installation_has_no_other_person_data_or_accounts(self):
  data=self.client.get('/api/state').json()
  self.assertTrue(all(not data[k] for k in ['projects','accounts','ideas','metrics','jobs']))
  self.assertIsNone(self.client.get('/api/workflow').json()['settings']['profile_id'])
 def test_local_api_requires_same_origin_and_session_for_writes(self):
  self.assertEqual(self.client.get('/api/state',headers={'host':'foreign.example'}).status_code,403)
  self.assertEqual(self.client.get('/api/local-session',headers={'origin':'https://foreign.example'}).status_code,403)
  self.assertEqual(self.client.post('/api/projects',json={'title':'x'}).status_code,403)
 def test_generated_original_card_is_readable_interactive_and_not_owner_confirmation(self):
  self.profile();model=Path(self.temp.name)/'model.json';html=Path(self.temp.name)/'card.html'
  model.write_text(json.dumps({'mode':'fictional_demo','hero_sentence':'我是测试业务的负责人。','note':'虚构测试，不是实际业务成果。'},ensure_ascii=False),encoding='utf-8')
  renderer=next((APP/'frozen-skills-v041/05').glob('*/scripts/render_card.py'))
  subprocess.run([sys.executable,'-X','utf8',str(renderer),str(model),str(html)],check=True,capture_output=True)
  text=html.read_text(encoding='utf-8');body={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'亮出绝活','topic':'共用资料','files':[{'name':'原版.html','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.assertEqual(self.post('/methods/artifacts',body).json()['imported'],1)
  self.assertEqual(self.post('/methods/artifacts',body).json()['imported'],0)
  row=next(x for x in self.client.get('/api/methods').json()['methods'] if x['step']=='05')
  result=self.client.get('/api/methods/assets/'+row['primary_id']).json();self.assertTrue(result['interactive']);self.assertEqual(result['blocked_scripts'],0)
  self.assertFalse(s.listing('writing_topic'));self.assertEqual(s.get('project','p')['sources'][0]['assets'][0]['review'],'pending')
 def test_another_person_cannot_mix_artifacts_into_active_business(self):
  self.profile();text='<h1>虚构卡片</h1>';packet={'profile_id':'p','owner':'其他人','business':'独立虚构业务','mode':'fictional_demo','module':'当头一棒','topic':'共用资料','files':[{'name':'x.html','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.assertEqual(self.post('/methods/artifacts',packet).status_code,409);self.assertFalse(s.get('project','p')['sources'][0]['assets'])
 def test_selected_topic_does_not_approve_or_publish_script(self):
  self.profile();text=json.dumps({'mode':'fictional_demo','topics':[{'question':'本次虚构任务应该先核对哪项材料？'}]},ensure_ascii=False)
  packet={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'三圈选题','topic':'共用资料','files':[{'name':'topics.json','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.post('/methods/artifacts',packet);asset=s.get('project','p')['sources'][0]['assets'][0]
  selected=self.post('/methods/confirm-topic',{'profile_id':'p','asset_id':asset['id'],'asset_sha':asset['sha256'],'title':'本次虚构任务应该先核对哪项材料？','state':{}}).json()
  topic=s.get('writing_topic',selected['topic_id']);self.assertEqual(topic['stage'],'topic');self.assertEqual(topic['script'],'');self.assertFalse(s.listing('batch'))
if __name__=='__main__':unittest.main()
