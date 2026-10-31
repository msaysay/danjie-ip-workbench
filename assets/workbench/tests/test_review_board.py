import sys,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
from review_board import ZONE,build_review_board,clean_prefs

NOW=datetime(2026,10,31,12,tzinfo=ZONE)

def snap(day,post,views,platform='douyin',likes=None,comments=None,shares=None,published=None,title=None,observed_at=None):
 return {'id':f'{platform}-{post}-{day}-{views}','platform':platform,'post_id':post,'metric_scope':'lifetime','observed_at':observed_at or f'{day}T09:00:00+08:00','published_at':published,'title':title or post,'views':views,'likes':likes,'comments':comments,'shares':shares}

class ReviewBoardTests(unittest.TestCase):
 def board(self,rows,days=7,platform='all',accounts=None,prefs=None,projects=None):
  return build_review_board(rows,projects or [],accounts or [],prefs or {},days=days,platform=platform,now=NOW)

 def test_empty_has_no_invented_numbers(self):
  board=self.board([])
  self.assertEqual(board['comparison']['snapshot_days'],0)
  self.assertIn('先同步一次',board['comparison']['tip'])
  self.assertIsNone(board['overview']['posts']['value'])
  self.assertIsNone(board['overview']['views']['value'])
  self.assertIsNone(board['overview']['interactions']['value'])
  self.assertFalse(board['engagement']['available'])
  self.assertEqual([item['views'] for item in board['platforms']],[None,None])
  self.assertEqual(board['highlights']['top'],[])
  self.assertEqual(board['placeholders'][0]['label'],'小红书')
  self.assertEqual(len(board['actions']['templates']),6)

 def test_one_snapshot_stays_cumulative(self):
  board=self.board([snap('2026-10-31','a',80,likes=3,comments=1,shares=0,published='2026-10-30T20:00:00+08:00',title='复盘 · 只同步了一次')])
  self.assertEqual(board['comparison']['mode'],'cumulative')
  self.assertEqual(board['comparison']['snapshot_days'],1)
  self.assertIn('再同步一次',board['comparison']['tip'])
  self.assertEqual(board['overview']['views']['value'],80)
  self.assertEqual(board['overview']['views']['basis'],'cumulative')
  self.assertIsNone(board['overview']['views']['direction'])
  self.assertEqual(board['works'][0]['views_delta'],None)
  self.assertEqual(board['works'][0]['title'],'只同步了一次')
  self.assertEqual(board['highlights']['basis'],'cumulative')
  self.assertEqual(board['highlights']['top'][0]['views'],80)
  self.assertTrue(board['engagement']['available'])
  self.assertEqual(board['engagement']['likes']['value'],3)

 def test_same_day_resync_does_not_invent_a_delta(self):
  rows=[snap('2026-10-31','a',10,observed_at='2026-10-31T08:00:00+08:00'),snap('2026-10-31','a',40,observed_at='2026-10-31T11:00:00+08:00',published='2026-10-31T07:00:00+08:00')]
  board=self.board(rows)
  self.assertEqual(board['comparison']['snapshot_days'],1)
  self.assertEqual(board['overview']['views']['value'],40)
  self.assertIsNone(board['works'][0]['views_delta'])

 def test_two_snapshots_make_a_seven_day_delta_without_a_prior_arrow(self):
  rows=[snap('2026-10-24','a',100,likes=1,comments=1,shares=1,published='2026-10-20T09:00:00+08:00'),snap('2026-10-31','a',160,likes=4,comments=2,shares=3,published='2026-10-20T09:00:00+08:00',title='一条老视频')]
  board=self.board(rows)
  self.assertEqual(board['comparison']['mode'],'period_delta')
  self.assertEqual(board['comparison']['coverage'],'window')
  self.assertEqual(board['overview']['views']['value'],60)
  self.assertIsNone(board['overview']['views']['prior'])
  self.assertIsNone(board['overview']['views']['direction'])
  self.assertIn('再早一次同步',board['comparison']['tip'])
  self.assertEqual(board['overview']['interactions']['value'],6)
  self.assertEqual(board['works'][0]['views_delta'],60)
  self.assertEqual(board['cadence']['posts'],0)
  self.assertIn('最长连续',board['cadence']['note'])

 def test_prior_period_arrow_uses_three_boundaries(self):
  rows=[]
  for day,views in [('2026-10-17',100),('2026-10-24',150),('2026-10-31',400)]:
   rows.append(snap(day,'a',views,published='2026-10-10T09:00:00+08:00'))
  board=self.board(rows)
  self.assertEqual(board['overview']['views']['value'],250)
  self.assertEqual(board['overview']['views']['prior'],50)
  self.assertEqual(board['overview']['views']['direction'],'up')
  self.assertIsNone(board['comparison']['tip'])

 def test_partial_span_is_labeled_and_not_called_a_full_week(self):
  rows=[snap('2026-10-30','a',10,published='2026-10-30T09:00:00+08:00'),snap('2026-10-31','a',25,published='2026-10-30T09:00:00+08:00')]
  board=self.board(rows)
  self.assertEqual(board['comparison']['coverage'],'partial')
  self.assertEqual(board['comparison']['span_days'],1)
  self.assertEqual(board['overview']['views']['value'],15)
  self.assertIn('相隔1天',board['comparison']['tip'])
  self.assertIsNone(board['overview']['views']['direction'])

 def test_wide_gap_is_not_used_as_the_seven_day_delta(self):
  rows=[snap('2026-10-01','a',10),snap('2026-10-31','a',90)]
  board=self.board(rows)
  self.assertEqual(board['comparison']['coverage'],'too_wide')
  self.assertIsNone(board['works'][0]['views_delta'])
  self.assertEqual(board['overview']['views']['basis'],'cumulative')
  self.assertEqual(board['overview']['views']['value'],90)
  self.assertIn('相隔超过',board['comparison']['tip'])

 def test_decreased_views_are_not_turned_into_a_gain(self):
  rows=[snap('2026-10-24','a',100),snap('2026-10-31','a',80)]
  board=self.board(rows)
  self.assertIsNone(board['works'][0]['views_delta'])
  self.assertEqual(board['overview']['views']['value'],80)
  self.assertEqual(board['overview']['views']['basis'],'cumulative')
  self.assertIn('没有算成增加',board['comparison']['tip'])

 def test_missing_engagement_collapses(self):
  rows=[snap('2026-10-24','a',10),snap('2026-10-31','a',20)]
  board=self.board(rows)
  self.assertFalse(board['engagement']['available'])
  self.assertIsNone(board['overview']['interactions']['value'])

 def test_platform_drilldown_keeps_both_shares(self):
  rows=[snap('2026-10-24','a',10,platform='douyin',published='2026-10-26T09:00:00+08:00',title='抖音题'),snap('2026-10-31','a',40,platform='douyin',published='2026-10-26T09:00:00+08:00',title='抖音题'),snap('2026-10-24','b',10,platform='tencent',published='2026-10-27T09:00:00+08:00',title='视频号题'),snap('2026-10-31','b',20,platform='tencent',published='2026-10-27T09:00:00+08:00',title='视频号题')]
  board=self.board(rows,platform='douyin')
  self.assertEqual(board['overview']['views']['value'],30)
  self.assertEqual(board['overview']['posts']['value'],1)
  self.assertEqual(board['works'][0]['platform'],'douyin')
  self.assertEqual([item['platform'] for item in board['platforms']],['douyin','tencent'])
  self.assertEqual(board['platforms'][0]['view_share'],0.75)
  self.assertEqual(board['platforms'][1]['view_share'],0.25)
  self.assertEqual(board['highlights']['top'][0]['title'],'抖音题')

 def test_yesterday_delta_and_post_arrow(self):
  rows=[snap('2026-10-29','a',5,published='2026-10-29T10:00:00+08:00'),snap('2026-10-30','a',12,published='2026-10-29T10:00:00+08:00'),snap('2026-10-30','b',1,published='2026-10-30T11:00:00+08:00',title='昨天新发')]
  board=self.board(rows,days=1)
  self.assertEqual(board['period']['end'],'2026-10-30')
  self.assertEqual(board['overview']['views']['value'],7)
  self.assertEqual(board['overview']['posts']['value'],1)
  self.assertEqual(board['overview']['posts']['prior'],1)
  self.assertEqual(board['overview']['posts']['direction'],'flat')

 def test_account_daily_is_not_added_into_post_views(self):
  rows=[snap('2026-10-24','a',10,platform='tencent'),snap('2026-10-31','a',18,platform='tencent')]
  accounts=[{'id':'tencent:acc:2026-10-30','platform':'tencent','account_label':'主号','day':'2026-10-30','values':{'new_views':999,'net_followers':2,'new_comments':1}}]
  board=self.board(rows,accounts=accounts)
  self.assertEqual(board['overview']['views']['value'],8)
  self.assertEqual(board['account_daily'][0]['new_views'],999)

 def test_undated_posts_are_not_counted_as_zero_cadence(self):
  board=self.board([snap('2026-10-31','a',5)])
  self.assertIsNone(board['cadence']['posts'])
  self.assertIn('没有发布时间',board['cadence']['note'])

 def test_window_metrics_are_ignored(self):
  row=snap('2026-10-31','a',5);row['metric_scope']='window'
  board=self.board([row])
  self.assertEqual(board['comparison']['snapshot_days'],0)

 def test_weekly_goal_and_checked_actions_round_trip_in_payload(self):
  prefs=clean_prefs({'weekly_goal':4,'checked':['fill-gap','sync-again']})
  board=self.board([snap('2026-10-28','a',1,published='2026-10-28T09:00:00+08:00'),snap('2026-10-31','a',2,published='2026-10-28T09:00:00+08:00')],prefs=prefs)
  self.assertEqual(board['cadence']['weekly_goal'],4)
  self.assertEqual(board['cadence']['week_posts'],1)
  self.assertEqual(board['actions']['checked'],['fill-gap','sync-again'])
  self.assertEqual(board['cadence']['week_start'],'2026-10-26')

 def test_clean_prefs_rejects_unknown_actions_and_blank_goal(self):
  self.assertIsNone(clean_prefs({'weekly_goal':None,'checked':[]})['weekly_goal'])
  with self.assertRaises(ValueError):clean_prefs({'checked':['invent-a-number']})
  with self.assertRaises(ValueError):clean_prefs({'weekly_goal':0})

class ReviewBoardApiTests(unittest.TestCase):
 def setUp(self):
  import tempfile
  import server as s
  self.s=s;self.temp=tempfile.TemporaryDirectory();self.old=s.DATA,s.DB;s.DATA=Path(self.temp.name);s.DB=s.DATA/'test.sqlite3'
  with s.connect() as c:c.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
  from fastapi.testclient import TestClient
  self.client=TestClient(s.app);self.headers={'x-workbench-token':s.TOKEN}
 def tearDown(self):
  self.s.DATA,self.s.DB=self.old;self.temp.cleanup()
 def test_board_endpoint_and_prefs_persist_locally(self):
  today=datetime.now(ZONE).date();start=(today-timedelta(days=7)).isoformat();end=today.isoformat();published=(today-timedelta(days=5)).isoformat()+'T09:00:00+08:00'
  self.s.put('metric',snap(start,'a',10,published=published))
  self.s.put('metric',snap(end,'a',22,published=published,title='样本题'))
  first=self.client.get('/api/classroom/reports/board?days=7&platform=all')
  self.assertEqual(first.status_code,200)
  body=first.json()
  self.assertEqual(body['overview']['views']['value'],12)
  for key in ['overview','cadence','platforms','highlights','engagement','actions','works']:self.assertIn(key,body)
  saved=self.client.post('/api/classroom/reports/board?days=7',json={'weekly_goal':3,'checked':['extend-top']},headers=self.headers)
  self.assertEqual(saved.status_code,200)
  self.assertEqual(saved.json()['cadence']['weekly_goal'],3)
  self.assertEqual(saved.json()['actions']['checked'],['extend-top'])
  again=self.client.get('/api/classroom/reports/board').json()
  self.assertEqual(again['actions']['checked'],['extend-top'])
  self.assertEqual(self.client.get('/api/classroom/reports').json()['board']['overview']['views']['value'],12)
  self.assertEqual(self.client.get('/api/classroom/reports/board?days=2').status_code,400)
  self.assertEqual(self.client.post('/api/classroom/reports/board',json={'weekly_goal':99},headers=self.headers).status_code,400)

if __name__=='__main__':unittest.main()
