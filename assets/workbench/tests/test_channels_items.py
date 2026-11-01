"""Fixture checks for 视频号作品解析.

Live WeChat login is not available in CI. The HTML fixtures follow the assistant
UI observed in 2026-10: 昨日数据 stays on the home shell, and works sit in
wujie-app's open shadow root as .post-feed-item cards. Declarative
template shadowrootmode="open" stands in for element.shadowRoot.

Manual check with a real cookie, using the publisher Python:

  python -X utf8 assets/workbench/channels_data.py <账号 alias>

Expect state verified and one item per visible work (title, counts, object id
when the page exposes it). An account page that really says 暂无作品 stays
verified_empty. Do not treat a run that only returns 昨日数据 as success.
"""
import sys,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
from channels_parse import build_result,snapshot_from_html,works_from_cards
from classroom_api import daily_reports
from review_engine import build_review

FIXTURES=Path(__file__).resolve().parent/'fixtures'
ZONE=timezone(timedelta(hours=8))

def load(name,pierce_shadow=True):
 return snapshot_from_html((FIXTURES/name).read_text(encoding='utf-8'),pierce_shadow)

class ChannelsItemTests(unittest.TestCase):
 def test_light_dom_misses_shadow_works_and_shadow_walk_reads_them(self):
  missed=build_result(load('channels_shadow_feed.html',False),'acct')
  self.assertEqual(missed['state'],'verified_overview')
  self.assertEqual(missed['items'],[])
  self.assertEqual(missed['overview']['new_views'],1280)
  found=build_result(load('channels_shadow_feed.html',True),'acct')
  self.assertEqual(found['state'],'verified')
  self.assertEqual(len(found['items']),2)
  first=next(item for item in found['items'] if item['post_id']=='export/UzFfBgAAExampleToken')
  self.assertEqual(first['title'],'老房翻新先看水电')
  self.assertEqual(first['identity_source'],'platform_object_id')
  self.assertEqual([first[key] for key in ('views','likes','comments','shares','saves')],[12000,88,3,2,9])
  self.assertEqual(first['published_at'],'2026-10-28T18:20:00+08:00')
  second=next(item for item in found['items'] if item['title']=='客户问报价怎么回')
  self.assertTrue(second['post_id'].startswith('local:'))
  self.assertEqual(second['identity_source'],'local_title_and_publish_time')
  self.assertEqual([second[key] for key in ('views','likes','comments','shares','saves')],[560,21,4,1,6])
  self.assertEqual(found['overview']['net_followers'],4)

 def test_home_recent_card_uses_visible_labels(self):
  result=build_result(load('channels_home_card.html'),'acct')
  self.assertEqual(len(result['items']),1)
  item=result['items'][0]
  self.assertEqual(item['title'],'近期这条讲报价')
  self.assertEqual([item[key] for key in ('views','likes','comments','shares','saves')],[80,7,1,2,4])

 def test_legacy_table_keeps_real_rows_and_skips_rows_without_an_id(self):
  result=build_result(load('channels_legacy_table.html'),'acct')
  self.assertEqual(len(result['items']),1)
  self.assertEqual(result['items'][0]['post_id'],'export/Abc123token')
  self.assertEqual(result['items'][0]['views'],100)

 def test_empty_page_stays_empty_and_overview_without_works_does_not_invent_items(self):
  empty=build_result(load('channels_empty.html'),'acct')
  self.assertEqual(empty['state'],'verified_empty')
  self.assertEqual(empty['items'],[])
  self.assertEqual(empty['overview']['new_views'],12)
  overview=build_result(load('channels_overview_only.html'),'acct')
  self.assertEqual(overview['state'],'verified_overview')
  self.assertEqual(overview['items'],[])

 def test_vue_post_supplies_object_id_and_zero_is_a_real_count(self):
  stamp=datetime(2026,10,28,18,20,tzinfo=ZONE)
  cards=[{'kind':'post-feed-item','title':'','posted_at':'','text':'','url':None,'attrs':{},'metrics':[],'vue':{'objectId':'export/UzFfBgAA','description':'10月高频词打卡','createTime':int(stamp.timestamp()),'readCount':10,'likeCount':1,'commentCount':0,'forwardCount':2,'favCount':3}}]
  item=works_from_cards(cards,'acct')[0]
  self.assertEqual(item['post_id'],'export/UzFfBgAA')
  self.assertEqual(item['title'],'10月高频词打卡')
  self.assertEqual(item['comments'],0)
  self.assertEqual(item['published_at'],stamp.replace(microsecond=0).isoformat())

 def test_classroom_report_and_review_count_imported_tencent_works(self):
  found=build_result(load('channels_shadow_feed.html'),'acct')
  item=next(row for row in found['items'] if row['views']==12000)
  metric={**item,'platform':'tencent','metric_scope':'lifetime','observed_at':'2026-10-30T12:00:00+08:00','snapshot_source':'browser_list'}
  report=daily_reports([metric],[])[0]
  self.assertEqual(report['platform_counts']['tencent'],1)
  self.assertEqual(report['works'],1)
  review=build_review([metric],days=3,now='2026-10-30T12:00:00+08:00')
  self.assertEqual(review['counts']['reviewable'],1)
  self.assertEqual(review['posts'][0]['platform'],'tencent')
  self.assertEqual(review['posts'][0]['views'],12000)

 def test_browser_script_walks_shadow_and_vue_post(self):
  source=(APP/'channels_data.py').read_text(encoding='utf-8')
  self.assertIn('shadowRoot',source)
  self.assertIn('__vue__',source)
  self.assertIn('.post-feed-item',source)
  self.assertNotIn('逐条作品明细仍待适配',source)

if __name__=='__main__':
 unittest.main()
