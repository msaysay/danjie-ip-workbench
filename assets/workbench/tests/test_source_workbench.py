import sys,json,hashlib,subprocess,tempfile,unittest
from datetime import datetime,timezone,timedelta
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
 def test_release_builder_excludes_generated_publisher_config_and_business_files(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('release_builder_for_test',APP.parents[1]/'scripts/build_release.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  module.ROOT=Path(self.temp.name)
  for name in ['assets/workbench/server.py','assets/workbench/vendor/social-auto-upload/conf.example.py','assets/workbench/vendor/social-auto-upload/conf.py','assets/workbench/data/private.json','assets/workbench/vendor/social-auto-upload/cookies/login.json','assets/workbench/vendor/pkg.egg-info/PKG-INFO']:
   file=module.ROOT/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('synthetic test file',encoding='utf-8')
  allowed={rel.as_posix() for file,rel in module.files()};self.assertEqual(allowed,{'assets/workbench/server.py','assets/workbench/vendor/social-auto-upload/conf.example.py'})
 def test_selected_topic_does_not_approve_or_publish_script(self):
  self.profile();text=json.dumps({'mode':'fictional_demo','topics':[{'question':'本次虚构任务应该先核对哪项材料？'}]},ensure_ascii=False)
  packet={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'三圈选题','topic':'共用资料','files':[{'name':'topics.json','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.post('/methods/artifacts',packet);asset=s.get('project','p')['sources'][0]['assets'][0]
  selected=self.post('/methods/confirm-topic',{'profile_id':'p','asset_id':asset['id'],'asset_sha':asset['sha256'],'title':'本次虚构任务应该先核对哪项材料？','state':{}}).json()
  topic=s.get('writing_topic',selected['topic_id']);self.assertEqual(topic['stage'],'topic');self.assertEqual(topic['script'],'');self.assertFalse(s.listing('batch'))
 def test_prepare_exports_homework_and_codex_script_roundtrip_stays_unconfirmed(self):
  self.profile();first=self.post('/experience/business/prepare',{});self.assertEqual(first.status_code,200)
  folder=s.project_dir('p')/'workbuddy-business';fmt=(folder/'选题回传格式.md').read_text(encoding='utf-8')
  self.assertIn('prepared_script',fmt);self.assertIn('writing_material_version',fmt);self.assertNotIn('仅给WorkBuddy看',fmt)
  self.assertTrue((folder/'宿主AI维护说明.md').is_file());self.assertIn('Codex',(folder/'宿主AI维护说明.md').read_text(encoding='utf-8'))
  text=json.dumps({'mode':'fictional_demo','topics':[{'question':'本次虚构任务应该先核对哪项材料？'}]},ensure_ascii=False)
  packet={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'三圈选题','topic':'共用资料','files':[{'name':'topics.json','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.assertEqual(self.post('/methods/artifacts',packet).json()['imported'],1)
  self.assertEqual(self.post('/experience/business/prepare',{}).status_code,200)
  exported=next(p for p in folder.iterdir() if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==packet['files'][0]['sha256'])
  self.assertEqual(exported.read_text(encoding='utf-8'),text)
  version=json.loads((folder/'当前作业版本.json').read_text(encoding='utf-8'))
  self.assertEqual([x['sha256'] for x in version['sources']],[packet['files'][0]['sha256']])
  self.assertFalse(list(folder.glob('选题回传格式-外部修改保留-*')))
  title='本次虚构任务应该先核对哪项材料？'
  opening='先别按别人的结论开口。这次虚构任务要问的是，哪一项材料必须先核对，才不会把演练写成已经发生的事。'
  reason='核对方法只有一条：对照本次已经接回的选题原句，缺的材料就标成还不知道。这里没有实测数字，也不能说已经研究证明。'
  identity='我是这次课堂演练里的测试学员，只说明自己在核对材料，没有可公开的成绩。'
  ending='看完先做一件事：把还没接回的材料留空，不要补成客户原话。'
  script='\n\n'.join([opening,reason,identity,ending]);self.assertGreaterEqual(len(script),80)
  topic={'title':title,'audience':'虚构测试里的学员本人','reason':'对应这份虚构选题里唯一的核对问题','needs':[1],'framework':[{'key':'opening','label':'开头','skill':'07','text':opening},{'key':'reason','label':'支撑','skill':'04','text':reason},{'key':'identity','label':'身份','skill':'05','text':identity},{'key':'ending','label':'收尾','skill':'06','text':ending}],'prepared_script':{'script':script,'parts':[{'key':'opening','text':opening},{'key':'reason','text':reason},{'key':'identity','text':identity},{'key':'ending','text':ending}],'plan':{'opening_method':'追魂一问','proof_method':'有对比','proof_state':'method_only','muscle_state':'identity_only','muscle_gaps':['没有成绩数字'],'ending_method':'留动作','source_shas':[packet['files'][0]['sha256']],'public_entry_quotes':[]},'generated_by':'Codex'}}
  payload={'profile_id':'p','mode':'fictional_demo','writing_material_version':version['writing_material_version'],'date':datetime.now(timezone(timedelta(hours=8))).date().isoformat(),'topics':[topic]}
  (folder/'今日选题.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
  synced=self.post('/experience/business/sync',{});self.assertEqual(synced.status_code,200);self.assertEqual(synced.json()['errors'],[])
  saved=next(t for t in s.listing('writing_topic') if t['title']==title)
  self.assertEqual(saved['prepared_script']['generated_by'],'Codex');self.assertEqual(saved['stage'],'topic');self.assertEqual(saved['script'],'')
  drafted=self.post('/workflow/topics/'+saved['id']+'/draft',{'expected_revision':saved['revision']});self.assertEqual(drafted.status_code,200)
  self.assertEqual(drafted.json()['stage'],'script');self.assertIn(opening,drafted.json()['script']);self.assertNotEqual(drafted.json()['stage'],'ready')
  edited=drafted.json()['script']+'\n\n这句话是学员在页面上改的，仍是虚构。'
  reviewed=self.post('/workflow/topics/'+saved['id']+'/review',{'action':'script','script':edited,'note':'把结尾说得更口语','finish':False,'expected_revision':drafted.json()['revision']})
  self.assertEqual(reviewed.status_code,200);self.assertEqual(reviewed.json()['stage'],'script');self.assertEqual(s.get('writing_topic',saved['id'])['script'],edited)
  topic['prepared_script']['plan']['source_shas']=['0'*64]
  (folder/'今日选题.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
  rejected=self.post('/experience/business/sync',{});self.assertEqual(rejected.status_code,200);self.assertTrue(rejected.json()['errors']);self.assertIn('sha256',rejected.json()['errors'][0])
  self.assertEqual(s.get('writing_topic',saved['id'])['script'],edited);self.assertEqual(s.get('writing_topic',saved['id'])['stage'],'script');self.assertFalse(s.listing('batch'))
if __name__=='__main__':unittest.main()
