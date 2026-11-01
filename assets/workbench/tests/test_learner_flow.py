import json,os,sys,tempfile,unittest
from pathlib import Path
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
import server as s
from experience_api import publish_copy_prompt

class LearnerFlowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=s.DATA,s.DB;s.DATA=Path(self.temp.name);s.DB=s.DATA/'test.sqlite3'
  with s.connect() as c:c.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
  from fastapi.testclient import TestClient
  self.client=TestClient(s.app);self.headers={'x-workbench-token':s.TOKEN}
 def tearDown(self):s.DATA,s.DB=self.old;self.temp.cleanup()
 def post(self,path,data):return self.client.post('/api'+path,json=data,headers=self.headers)
 def profile(self):
  m={'kind':'business_memory','schema':'danjie-business-memory/1','id':'memory','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','assets':[],'notes':[]}
  s.put('project',{'id':'p','title':'测试业务','sources':[m],'segments':[]});s.put('workflow_settings',{'id':'main','profile_id':'p','time':'08:30','count':5,'enabled':False});return m
 def test_pages_show_the_non_edit_path_and_empty_ctas(self):
  src=APP/'src'
  main=(src/'main.jsx').read_text(encoding='utf-8')
  daily=(src/'DailyHome.jsx').read_text(encoding='utf-8')
  publish=(src/'PublishingPage.jsx').read_text(encoding='utf-8')
  review=(src/'ReviewBoard.jsx').read_text(encoding='utf-8')
  methods=(src/'MethodHome.jsx').read_text(encoding='utf-8')
  path=(src/'LearnerPath.jsx').read_text(encoding='utf-8')
  self.assertIn('成片在外部剪好再上传',path)
  self.assertIn('不在这里剪',path)
  self.assertNotIn("setNav('video'",main)
  self.assertIn('回蛋解方法选一题',daily)
  self.assertIn('成片剪好了，去发布上传',daily)
  self.assertIn('选题或底稿还没接住',daily)
  self.assertIn('工作台不剪视频',publish)
  self.assertIn('还没有稿，去选题脚本',publish)
  self.assertIn('粘贴发布文字',publish)
  self.assertIn('去发布上传成片',review)
  self.assertIn('去登录账号',review)
  self.assertIn('工作台里没有剪辑',methods)
  handoff=(src/'StoryCueHandoff.jsx').read_text(encoding='utf-8')
  connect=(src/'ConnectAnalytics.jsx').read_text(encoding='utf-8')
  calendar=(src/'PublishCalendar.jsx').read_text(encoding='utf-8')
  self.assertNotIn('sayFrame',handoff)
  self.assertIn('自己剪好，再在工作台「发布」上传成片',handoff)
  self.assertIn('外部剪辑工具',handoff)
  self.assertIn('现在更新',connect)
  self.assertIn("/classroom/reports/update",connect)
  self.assertIn('每天回收一次',connect)
  self.assertNotIn('10*3600',publish)
  self.assertIn('SCHEDULE_LEAD_MS=2*60*60*1000',publish)
  self.assertIn('至少晚 2 小时',publish)
  self.assertIn('至少晚 2 小时',calendar)
  self.assertIn('近7天',review)
  self.assertIn('所以这里是 0 条',review)
  self.assertIn('WorkBuddy 或 Codex',methods)
  self.assertIn('WorkBuddy 或 Codex',daily)
  settings=(src/'SettingsPage.jsx').read_text(encoding='utf-8')
  self.assertIn('WorkBuddy 或 Codex',settings)
  self.assertIn('现在更新',settings)
  self.assertIn('每天回收一次',settings)
  skill=(APP.parents[1]/'SKILL.md').read_text(encoding='utf-8')
  self.assertIn('不要接 sayFrame',skill)
  self.assertIn('外部剪好',skill)
 def test_bad_topic_json_and_oversized_file_are_reported(self):
  self.profile();self.assertEqual(self.post('/experience/business/prepare',{}).status_code,200)
  folder=s.project_dir('p')/'workbuddy-business'
  (folder/'今日选题.json').write_text('{',encoding='utf-8')
  bad=self.post('/experience/business/sync',{})
  self.assertEqual(bad.status_code,200)
  self.assertTrue(any('读不出来' in item for item in bad.json()['errors']))
  self.assertFalse(s.listing('writing_topic'))
  (folder/'今日选题.json').write_bytes(b'x'*(1024*1024+1))
  huge=self.post('/experience/business/sync',{})
  self.assertTrue(any('超过 1MB' in item for item in huge.json()['errors']))
  self.assertFalse(s.listing('writing_topic'))
 def test_shared_folder_outside_the_business_is_reported(self):
  self.profile();self.post('/experience/business/prepare',{})
  link=s.listing('business_chat_link')[0]
  s.put('business_chat_link',{**link,'folder':str(Path(self.temp.name)/'not-this-business')})
  moved=self.post('/experience/business/sync',{})
  self.assertTrue(any('文件夹' in item for item in moved.json()['errors']))
 def test_task_pack_does_not_send_the_learner_to_an_editor(self):
  project=self.post('/projects',{'title':'一条口播','brief':'先写稿'}).json()
  pack=self.post('/projects/'+project['id']+'/task-pack',{})
  self.assertEqual(pack.status_code,200)
  text=pack.json()['prompt']
  self.assertNotIn('OpenFilm',text)
  self.assertNotIn('剪辑：',text)
  self.assertIn('外部剪好',text)
  self.assertIn('粘贴 AI 写好的发布文字',text)
 def test_publish_copy_prompt_uses_the_running_port(self):
  previous=os.environ.get('WORKBENCH_PORT')
  os.environ['WORKBENCH_PORT']='18866'
  try:text=publish_copy_prompt('abc','sha','existing_exact_video')
  finally:
   if previous is None:os.environ.pop('WORKBENCH_PORT',None)
   else:os.environ['WORKBENCH_PORT']=previous
  self.assertIn('http://127.0.0.1:18866/api/state',text)
  self.assertIn('http://127.0.0.1:18866/api/projects/abc',text)
  self.assertNotIn('8766',text)
  self.assertNotIn('OpenFilm',text)
  self.assertIn('粘贴 AI 写好的发布文字',text)
  self.assertIn('不剪辑',text)
 def test_null_platform_copy_is_rejected_without_changing_the_project(self):
  project=self.post('/projects',{'title':'成片'}).json()
  rejected=self.client.patch('/api/projects/'+project['id'],json={'platform_copy':None,'expected_revision':project['revision']},headers=self.headers)
  self.assertEqual(rejected.status_code,400)
  self.assertIn('原稿没有改',rejected.json()['detail'])
  self.assertEqual(s.get('project',project['id']).get('platform_copy'),{})
 def test_mismatched_prepared_script_is_not_applied_silently(self):
  self.profile();text=json.dumps({'mode':'fictional_demo','topics':[{'question':'本次虚构任务应该先核对哪项材料？'}]},ensure_ascii=False)
  packet={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'三圈选题','topic':'共用资料','files':[{'name':'topics.json','encoding':'text','content':text,'sha256':__import__('hashlib').sha256(text.encode()).hexdigest()}]}
  self.assertEqual(self.post('/methods/artifacts',packet).json()['imported'],1)
  asset=s.get('project','p')['sources'][0]['assets'][0]
  s.put('writing_topic',{'id':'t1','profile_id':'p','title':'本次虚构任务应该先核对哪项材料？','audience':'','reason':'','needs':[],'framework':[{'key':key,'label':key,'skill':'','text':''} for key in ['opening','reason','identity','ending']],'confirmed':False,'stage':'topic','script':'','history':[],'demo':True,'prepared_script':{'material_signature':'stale','script':'旧稿','parts':[],'plan':{}},'created':s.now()})
  chosen=self.post('/methods/confirm-topic',{'profile_id':'p','asset_id':asset['id'],'asset_sha':asset['sha256'],'title':'本次虚构任务应该先核对哪项材料？','state':{'opening':'一个对不上的开头'}})
  self.assertEqual(chosen.status_code,200)
  topic=s.get('writing_topic','t1')
  self.assertIn('没有自动套用旧稿',topic.get('draft_bind_warning',''))
  self.assertEqual(topic['prepared_script']['script'],'旧稿')
  self.assertEqual(topic['stage'],'topic')
 def test_missing_registered_artifact_is_not_a_successful_sync(self):
  import workbuddy_sync
  root=Path(self.temp.name)/'proj';root.mkdir()
  state={'schema':'danjie-ip-workbench/0.1.0','mode':'fictional_demo','project_id':'p1','student_ref':'测试','business':'虚构','name':'测试','artifacts':{'a':{'step':2,'topic_id':'main','files':{'card':{'snapshot':'missing.json','sha256':'abc','source':'选题.json'}}}}}
  (root/'project.json').write_text(json.dumps(state),encoding='utf-8')
  with self.assertRaises(ValueError) as caught:workbuddy_sync.sync(root)
  self.assertIn('没有接入',str(caught.exception))
  self.assertFalse((root/'memory'/'memory.json').exists())
if __name__=='__main__':unittest.main()
