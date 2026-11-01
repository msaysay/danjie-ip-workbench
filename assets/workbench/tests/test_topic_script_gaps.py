import sys,json,hashlib,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
import server as s
from danjie_writing import request_context,digest,REFERENCE_HINT

class TopicScriptGapTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=s.DATA,s.DB;s.DATA=Path(self.temp.name);s.DB=s.DATA/'test.sqlite3'
  with s.connect() as c:c.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
  from fastapi.testclient import TestClient
  self.client=TestClient(s.app);self.headers={'x-workbench-token':s.TOKEN}
 def tearDown(self):s.DATA,s.DB=self.old;self.temp.cleanup()
 def post(self,path,data=None):return self.client.post('/api'+path,json=data or {},headers=self.headers)
 def profile(self):
  m={'kind':'business_memory','schema':'danjie-business-memory/1','id':'memory','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','assets':[],'notes':[]}
  s.put('project',{'id':'p','title':'测试业务','sources':[m],'segments':[]});s.put('workflow_settings',{'id':'main','profile_id':'p','time':'08:30','count':5,'enabled':False});return m
 def import_topic_card(self):
  text=json.dumps({'mode':'fictional_demo','topics':[{'question':'本次虚构任务应该先核对哪项材料？'}]},ensure_ascii=False)
  packet={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'三圈选题','topic':'共用资料','files':[{'name':'topics.json','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.assertEqual(self.post('/methods/artifacts',packet).json()['imported'],1)
  return packet['files'][0]['sha256']
 def sync_prepared(self,sha,title='本次虚构任务应该先核对哪项材料？'):
  self.post('/experience/business/prepare',{})
  folder=s.project_dir('p')/'workbuddy-business'
  self.post('/experience/business/prepare',{})
  version=json.loads((folder/'当前作业版本.json').read_text(encoding='utf-8'))
  opening='先别按别人的结论开口。这次虚构任务要问的是，哪一项材料必须先核对，才不会把演练写成已经发生的事。'
  reason='核对方法只有一条：对照本次已经接回的选题原句，缺的材料就标成还不知道。这里没有实测数字，也不能说已经研究证明。'
  identity='我是这次课堂演练里的测试学员，只说明自己在核对材料，没有可公开的成绩。'
  ending='看完先做一件事：把还没接回的材料留空，不要补成客户原话。'
  script='\n\n'.join([opening,reason,identity,ending])
  topic={'title':title,'audience':'虚构测试里的学员本人','reason':'对应这份虚构选题里唯一的核对问题','needs':[1],'framework':[{'key':'opening','label':'开头','skill':'07','text':opening},{'key':'reason','label':'支撑','skill':'04','text':reason},{'key':'identity','label':'身份','skill':'05','text':identity},{'key':'ending','label':'收尾','skill':'06','text':ending}],'prepared_script':{'script':script,'parts':[{'key':'opening','text':opening},{'key':'reason','text':reason},{'key':'identity','text':identity},{'key':'ending','text':ending}],'plan':{'opening_method':'追魂一问','proof_method':'有对比','proof_state':'method_only','muscle_state':'identity_only','muscle_gaps':['没有成绩数字'],'ending_method':'留动作','source_shas':[sha],'public_entry_quotes':[]},'generated_by':'Codex'}}
  payload={'profile_id':'p','mode':'fictional_demo','writing_material_version':version['writing_material_version'],'date':datetime.now(timezone(timedelta(hours=8))).date().isoformat(),'topics':[topic]}
  (folder/'今日选题.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
  synced=self.post('/experience/business/sync',{})
  self.assertEqual(synced.json()['errors'],[],synced.json())
  saved=next(t for t in s.listing('writing_topic') if t['title']==title)
  return saved,opening
 def test_keeping_a_reference_still_uses_the_prepared_draft(self):
  self.profile();sha=self.import_topic_card();self.post('/experience/business/prepare',{})
  first=self.post('/ideas',{'title':'一条已经留下的参考','url':'https://example.com/a','notes':'只作参考'}).json()
  saved,opening=self.sync_prepared(sha)
  self.assertEqual([item['title'] for item in saved['source_references']],['一条已经留下的参考'])
  self.assertEqual(self.client.get('/api/workflow').json()['topics'][0].get('reference_hint'),None)
  second=self.post('/ideas',{'title':'新留下的一条参考','url':'https://example.com/b','notes':'后加的'}).json()
  hinted=self.client.get('/api/workflow').json()['topics'][0]
  self.assertEqual(hinted['reference_hint'],REFERENCE_HINT)
  drafted=self.post('/workflow/topics/'+saved['id']+'/draft',{'expected_revision':saved['revision']})
  self.assertEqual(drafted.status_code,200,drafted.text)
  self.assertIn(opening,drafted.json()['script'])
  self.assertEqual(drafted.json()['stage'],'script')
  self.assertNotIn('xiaohongshu',json.dumps(drafted.json()))
  removed=self.post('/ideas/'+second['id']+'/remove')
  self.assertEqual(removed.status_code,200)
  self.assertFalse(any(item['id']==second['id'] for item in self.client.get('/api/state').json()['ideas']))
  restored=self.post('/ideas/'+second['id']+'/restore',removed.json())
  self.assertEqual(restored.status_code,200)
  self.assertTrue(any(item['id']==second['id'] for item in self.client.get('/api/state').json()['ideas']))
  self.assertEqual(s.get('writing_topic',saved['id'])['source_references'][0]['title'],first['title'])
 def test_legacy_signature_with_references_still_applies_and_real_changes_do_not(self):
  self.profile();sha=self.import_topic_card();self.post('/experience/business/prepare',{})
  self.post('/ideas',{'title':'写稿时已经在的参考','url':'https://example.com/old','notes':'旧参考'})
  saved,opening=self.sync_prepared(sha)
  memory=s.get('project','p')['sources'][0]
  ideas=[x for x in s.listing('idea') if x.get('profile_id')=='p']
  ctx=request_context(s.ROOT,memory,saved,[],[x for x in ideas if x['title']=='写稿时已经在的参考'])
  legacy=digest({k:v for k,v in ctx.items() if k!='material_signature'})
  prepared=dict(saved['prepared_script']);prepared['material_signature']=legacy;prepared.pop('reference_titles',None)
  s.patch('writing_topic',saved['id'],{'prepared_script':prepared})
  self.post('/ideas',{'title':'后来才留下的参考','url':'https://example.com/new','notes':'新参考'})
  self.assertEqual(self.client.get('/api/workflow').json()['topics'][0]['reference_hint'],REFERENCE_HINT)
  s.put('writing_feedback',{'id':'fb1','profile_id':'p','direction':'把开头改短','source_title':'虚构','status':'hypothesis_for_next_draft','created':s.now()})
  blocked=s.get('writing_topic',saved['id'])
  feedback_blocked=self.post('/workflow/topics/'+blocked['id']+'/draft',{'expected_revision':blocked['revision']})
  self.assertEqual(feedback_blocked.status_code,409)
  self.assertIn('还没接到新的写稿结果',feedback_blocked.json()['detail'])
  self.assertEqual(s.get('writing_topic',blocked['id'])['script'],'')
  s.remove('writing_feedback','fb1')
  s.patch('writing_topic',blocked['id'],{'title':'题目已经换了，不能再用旧稿'})
  moved=s.get('writing_topic',blocked['id'])
  rejected=self.post('/workflow/topics/'+moved['id']+'/draft',{'expected_revision':moved['revision']})
  self.assertEqual(rejected.status_code,409)
  self.assertEqual(s.get('writing_topic',moved['id'])['stage'],'topic')
  s.patch('writing_topic',moved['id'],{'title':saved['title']})
  current=s.get('writing_topic',saved['id'])
  drafted=self.post('/workflow/topics/'+current['id']+'/draft',{'expected_revision':current['revision']})
  self.assertEqual(drafted.status_code,200,drafted.text)
  self.assertIn(opening,drafted.json()['script'])
 def test_confirmed_topic_opens_an_editable_publish_draft_without_publishing(self):
  self.profile();sha=self.import_topic_card();self.post('/experience/business/prepare',{})
  saved,opening=self.sync_prepared(sha)
  drafted=self.post('/workflow/topics/'+saved['id']+'/draft',{'expected_revision':saved['revision']})
  self.assertEqual(drafted.status_code,200,drafted.text)
  early=self.post('/workflow/topics/'+saved['id']+'/publish-draft')
  self.assertEqual(early.status_code,409)
  confirmed=self.post('/workflow/topics/'+saved['id']+'/review',{'action':'script','script':drafted.json()['script'],'note':'','finish':True,'expected_revision':drafted.json()['revision']})
  self.assertEqual(confirmed.status_code,200)
  s.put('project',{'id':'oldvideo','title':'一条无关的旧视频','sources':[],'segments':[],'platform_copy':{'douyin':{'title':'旧标题','desc':'旧说明','tags':'旧话题'},'tencent':{'title':'旧标题','desc':'旧说明','tags':'旧话题'}},'status':'待发布','created':s.now()})
  opened=self.post('/workflow/topics/'+saved['id']+'/publish-draft')
  self.assertEqual(opened.status_code,200,opened.text)
  project=opened.json()
  self.assertNotEqual(project['id'],'oldvideo')
  self.assertEqual(project['writing_topic_id'],saved['id'])
  self.assertIn('核对',project['writing_topic_title'])
  self.assertEqual(set(project['platform_copy']),{'douyin','tencent'})
  self.assertNotIn('xiaohongshu',project['platform_copy'])
  self.assertIn(opening[:12],project['platform_copy']['douyin']['desc'])
  self.assertTrue(project['platform_copy']['douyin']['title'])
  self.assertLessEqual(len(project['platform_copy']['douyin']['title']),30)
  self.assertTrue(project['platform_copy']['tencent']['tags'])
  self.assertFalse(s.listing('batch'))
  edited={'douyin':{**project['platform_copy']['douyin'],'title':'学员改过的标题'},'tencent':project['platform_copy']['tencent']}
  patched=self.client.patch('/api/projects/'+project['id'],json={'platform_copy':edited,'expected_revision':project['revision']},headers=self.headers)
  self.assertEqual(patched.status_code,200,patched.text)
  again=self.post('/workflow/topics/'+saved['id']+'/publish-draft')
  self.assertEqual(again.json()['id'],project['id'])
  self.assertEqual(again.json()['platform_copy']['douyin']['title'],'学员改过的标题')
  self.assertEqual(s.get('project','oldvideo')['platform_copy']['douyin']['title'],'旧标题')
  self.assertFalse(s.listing('batch'))
 def test_homework_lists_connected_and_missing_cards(self):
  self.profile();self.import_topic_card()
  homework={row['key']:row for row in self.client.get('/api/workflow').json()['homework']}
  self.assertFalse(homework['客群卡']['ready'])
  self.assertFalse(homework['人设卡']['ready'])
  self.assertFalse(homework['实力原句']['ready'])
  self.assertFalse(homework['开头']['ready'])
  text='客群卡虚构正文'
  packet={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'客群卡','topic':'共用资料','files':[{'name':'audience.md','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.post('/methods/artifacts',packet)
  text='实力原句虚构正文，没有成绩数字。'
  muscle={'profile_id':'p','owner':'测试学员','business':'独立虚构业务','mode':'fictional_demo','module':'亮出绝活','topic':'共用资料','files':[{'name':'muscle.md','encoding':'text','content':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
  self.post('/methods/artifacts',muscle)
  homework={row['key']:row for row in self.client.get('/api/workflow').json()['homework']}
  self.assertTrue(homework['客群卡']['ready'])
  self.assertTrue(homework['实力原句']['ready'])
  self.assertFalse(homework['人设卡']['ready'])
  self.assertEqual(homework['实力原句']['label'],'亮出绝活')
 def test_pages_name_the_reference_the_single_primary_and_the_topic_link(self):
  src=APP/'src'
  daily=(src/'DailyHome.jsx').read_text(encoding='utf-8')
  publish=(src/'PublishingPage.jsx').read_text(encoding='utf-8')
  radar=(src/'InspirationRadar.jsx').read_text(encoding='utf-8')
  self.assertIn('参考了：',daily)
  self.assertIn('reference_hint',daily)
  self.assertIn('去蛋解方法补上',daily)
  self.assertIn('已经接上：',daily)
  self.assertIn('还没接上：',daily)
  self.assertIn('确认这版脚本',daily)
  self.assertIn('去发布上传',daily)
  self.assertIn('lead={false}',daily)
  self.assertNotIn('成片剪好了，去发布上传',daily)
  self.assertIn('回到这题',publish)
  self.assertIn('writing_topic_id',publish)
  self.assertIn('按确认稿先拟的',publish)
  self.assertIn("'/ideas/'+idea.id+'/remove'",radar)
  self.assertIn('删掉',radar)
  self.assertIn('撤销，恢复刚删掉的参考',radar)
  self.assertFalse((src/'WorkflowPanel.jsx').exists())
if __name__=='__main__':unittest.main()
