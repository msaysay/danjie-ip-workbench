import sys,json,hashlib,subprocess,tempfile,unittest
from pathlib import Path
APP=Path(__file__).resolve().parents[1]; sys.path.insert(0, str(APP))
import server as s

class PublishPlanTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.old=s.DATA,s.DB; s.DATA=Path(self.temp.name); s.DB=s.DATA/'test.sqlite3'
  with s.connect() as c: c.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
  from fastapi.testclient import TestClient
  self.client=TestClient(s.app); self.headers={'x-workbench-token':s.TOKEN}
 def tearDown(self):
  s.DATA,s.DB=self.old; self.temp.cleanup()
 def video(self, project_id):
  folder=s.project_dir(project_id)/'finished'; folder.mkdir(parents=True, exist_ok=True); target=folder/'clip.mp4'
  subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x3366aa:s=320x240:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(target)], check=True)
  raw=target.read_bytes(); info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(target)], text=True))
  return {'kind':'finished_video','file':target.relative_to(s.DATA).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'duration':float(info['format']['duration']),'edit_hash':'finished'}
 def accounts(self):
  s.put('account', {'id':'dy','platform':'douyin','alias':'dy1','label':'我的抖音','status':'已验证'})
  s.put('account', {'id':'wx','platform':'tencent','alias':'wx1','label':'我的视频号','status':'已验证'})
 def project(self, ident, copy, output, prep=None):
  s.put('project', {'id':ident,'title':'测试成片','platform_copy':copy,'output':output,'publish_preparation':prep or {}})
 def size(self, path):
  info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(path)], text=True))
  row=info['streams'][0]; return int(row['width']), int(row['height'])
 def test_missing_covers_become_midframe_thumbnails_and_stay_stable(self):
  self.accounts(); output=self.video('p')
  copy={'douyin':{'title':'失忆这一课','desc':'讲上下文','tags':'记忆'},'tencent':{'title':'失忆这一课','desc':'讲上下文','tags':'记忆','short_title':'讲清上下文窗口'}}
  self.project('p', copy, output)
  first=s.publication_plan(s.get('project','p'), ['dy','wx'])
  self.assertEqual(first['cover_source'], 'auto_frame')
  saved=s.get('project','p')
  self.assertEqual(saved['publish_preparation']['cover_state'], 'auto_frame')
  self.assertTrue(saved['cover_studio']['auto'])
  for item in first['items']:
   self.assertIn('--thumbnail-portrait', item['args']); self.assertIn('--thumbnail-landscape', item['args'])
   self.assertNotIn('--location', item['args'])
   portrait=s.DATA/item['cover_files']['cover']; landscape=s.DATA/item['cover_files']['cover_landscape']
   self.assertEqual(self.size(portrait), (1080,1440)); self.assertEqual(self.size(landscape), (1440,1080))
  second=s.publication_plan(s.get('project','p'), ['dy','wx'])
  self.assertEqual(second['cover_source'], 'auto_frame')
  self.assertEqual(second['items'], first['items'])
 def test_existing_covers_are_kept_and_cleared_covers_are_not_rebuilt(self):
  self.accounts(); output=self.video('kept')
  folder=s.project_dir('kept')/'publication'; folder.mkdir(parents=True, exist_ok=True)
  portrait=folder/'mine-portrait.jpg'; landscape=folder/'mine-landscape.jpg'
  subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=red:s=16x16','-frames:v','1',str(portrait)], check=True)
  subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=green:s=20x12','-frames:v','1',str(landscape)], check=True)
  before=hashlib.sha256(portrait.read_bytes()).hexdigest()
  rel=lambda path: path.relative_to(s.DATA).as_posix()
  copy={'douyin':{'title':'已有封面','desc':'','tags':'','cover':rel(portrait),'cover_landscape':rel(landscape)},'tencent':{'title':'已有封面','desc':'','tags':'','cover':rel(portrait),'cover_landscape':rel(landscape)}}
  self.project('kept', copy, output, {'cover_state':'video_frame'})
  plan=s.publication_plan(s.get('project','kept'), ['dy'])
  self.assertEqual(plan['cover_source'], 'existing')
  self.assertEqual(hashlib.sha256(portrait.read_bytes()).hexdigest(), before)
  self.assertEqual(self.size(s.DATA/plan['items'][0]['cover_files']['cover']), (16,16))
  output=self.video('skip'); self.project('skip', {'douyin':{'title':'不用封面','desc':'','tags':''},'tencent':{'title':'不用封面','desc':'','tags':''}}, output, {'cover_state':'cleared'})
  skipped=s.publication_plan(s.get('project','skip'), ['dy','wx'])
  self.assertEqual(skipped['cover_source'], 'cleared')
  for item in skipped['items']:
   self.assertNotIn('--thumbnail-portrait', item['args']); self.assertNotIn('--thumbnail-landscape', item['args']); self.assertEqual(item['cover_files'], {})
 def test_clear_endpoint_then_plan_does_not_invent_covers(self):
  self.accounts(); output=self.video('gone'); self.project('gone', {'douyin':{'title':'先有封面','desc':''},'tencent':{'title':'先有封面','desc':''}}, output)
  s.publication_plan(s.get('project','gone'), ['dy'])
  current=s.get('project','gone')
  cleared=self.client.post('/api/projects/gone/covers/clear', json={'expected_revision':current['revision']}, headers=self.headers)
  self.assertEqual(cleared.status_code, 200)
  fresh=s.get('project','gone')
  self.assertEqual(fresh['publish_preparation']['cover_state'], 'cleared')
  self.assertNotIn('cover', fresh['platform_copy']['douyin'])
  plan=s.publication_plan(fresh, ['wx'])
  self.assertEqual(plan['cover_source'], 'cleared')
  self.assertNotIn('--thumbnail-landscape', plan['items'][0]['args'])

if __name__=='__main__': unittest.main()
