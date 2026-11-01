import importlib.util,unittest
from pathlib import Path

SAU=Path(__file__).resolve().parents[1]/'vendor'/'social-auto-upload'
spec=importlib.util.spec_from_file_location('publish_guards', SAU/'uploader'/'publish_guards.py')
guards=importlib.util.module_from_spec(spec); spec.loader.exec_module(guards)

class L:
 def __init__(self, nodes): self.nodes=list(nodes)
 @property
 def first(self): return L(self.nodes[:1])
 def nth(self, index): return L(self.nodes[index:index+1] if 0<=index<len(self.nodes) else [])
 async def count(self): return len(self.nodes)
 async def is_visible(self): return bool(self.nodes and self.nodes[0].get('visible', True))
 async def inner_text(self): return self.nodes[0].get('text','') if self.nodes else ''
 async def click(self, **kwargs):
  if not self.nodes: raise RuntimeError('empty')
  node=self.nodes[0]; node['clicks']=node.get('clicks',0)+1
  if node.get('on_click'): node['on_click'](node)
 async def get_attribute(self, name):
  if not self.nodes: return None
  return (self.nodes[0].get('attrs') or {}).get(name)
 async def is_disabled(self): return bool(self.nodes and self.nodes[0].get('disabled'))
 async def evaluate(self, script):
  if not self.nodes: return False
  node=self.nodes[0]
  if 'disabled' in script: return bool(node.get('disabled'))
  if 'checked' in script: return bool(node.get('checked'))
  return False
 async def wait_for(self, **kwargs):
  if not self.nodes or not self.nodes[0].get('visible', True): raise TimeoutError('hidden')
 async def fill(self, value):
  if self.nodes: self.nodes[0]['text']=value
 def locator(self, sel):
  if not self.nodes: return L([])
  kids=self.nodes[0].get('children') or {}
  matches=[key for key in kids if key in sel]
  if not matches: return L([])
  return L(kids[max(matches, key=len)])

class Keyboard:
 def __init__(self): self.pressed=[]
 async def press(self, key): self.pressed.append(key)

class Page:
 def __init__(self):
  self.selectors={}; self.texts=[]; self.roles=[]; self.keyboard=Keyboard()
 async def wait_for_timeout(self, ms): return None
 def locator(self, sel): return L(self.selectors.get(sel, []))
 def get_by_text(self, text, exact=True):
  found=[node for node in self.texts if node.get('text')==text or (not exact and text in node.get('text',''))]
  return L(found)
 def get_by_role(self, role, name=None, exact=True):
  return L([node for node in self.roles if node.get('role')==role and (name is None or node.get('name')==name)])

class PublishGuardTests(unittest.IsolatedAsyncioTestCase):
 def test_blank_location_text_and_no_geolocation(self):
  self.assertTrue(guards.location_text_is_blank(''))
  self.assertTrue(guards.location_text_is_blank('不显示位置'))
  self.assertTrue(guards.location_text_is_blank('位置 不显示位置'))
  self.assertTrue(guards.location_text_is_blank('输入地理位置'))
  self.assertFalse(guards.location_text_is_blank('德宏傣族自治州'))
  self.assertFalse(guards.location_text_is_blank('位置 德宏傣族自治州'))
  self.assertFalse(guards.grants_geolocation(''))
  self.assertFalse(guards.grants_geolocation('上海'))
 def test_uploaders_clear_location_and_require_both_statements(self):
  douyin=(SAU/'uploader'/'douyin_uploader'/'main.py').read_text(encoding='utf-8')
  tencent=(SAU/'uploader'/'tencent_uploader'/'main.py').read_text(encoding='utf-8')
  self.assertNotIn('permissions=["geolocation"]', douyin)
  self.assertNotIn('不勾原创', tencent)
  video=douyin.split('async def upload(self, playwright: Playwright)')[1].split('class DouYinNote')[0]
  self.assertIn('permissions=[]', video)
  self.assertIn('await self.apply_original_claim(page)', video)
  self.assertIn('await self.set_location(page, self.location)', video)
  self.assertIn('内容由AI生成', douyin)
  upload=tencent.split('async def upload(self, playwright: Playwright)')[1].split('async def tencent_upload_video')[0]
  self.assertLess(upload.find('apply_location'), upload.find('submit_publish'))
  self.assertIn('apply_tencent_ai_label', tencent)
  self.assertIn('claim_original', tencent)
 async def test_channels_location_is_cleared_and_verified(self):
  page=Page(); display={'text':'德宏傣族自治州','visible':True,'clicks':0}; option={'text':'不显示位置','visible':False}
  def show(_): option['visible']=True
  def choose(_): display['text']='不显示位置'
  display['on_click']=show; option['on_click']=choose
  page.selectors['.post-position-wrap .position-display']=[display]; page.texts.append(option)
  await guards.clear_tencent_location(page)
  self.assertEqual(display['text'], '不显示位置'); self.assertEqual(display['clicks'], 1)
 async def test_channels_location_failure_stops_publish(self):
  page=Page(); display={'text':'德宏傣族自治州','visible':True}; option={'text':'不显示位置','visible':True}
  page.selectors['.post-position-wrap .position-display']=[display]; page.texts.append(option)
  with self.assertRaises(RuntimeError) as caught: await guards.clear_tencent_location(page)
  self.assertIn('德宏傣族自治州', str(caught.exception))
 async def test_channels_blank_location_is_left_alone(self):
  page=Page(); display={'text':'不显示位置','visible':True,'clicks':0}
  page.selectors['.post-position-wrap .position-display']=[display]
  await guards.clear_tencent_location(page)
  self.assertEqual(display['clicks'], 0)
 async def test_channels_missing_location_row_stops_publish(self):
  with self.assertRaises(RuntimeError) as caught: await guards.clear_tencent_location(Page())
  self.assertIn('位置栏', str(caught.exception))
 async def test_douyin_location_clear_waits_until_placeholder_returns(self):
  page=Page(); placeholder={'text':'输入地理位置','visible':False,'children':{}}
  clear={'visible':True,'on_click':lambda _node: placeholder.__setitem__('visible', True)}
  select={'visible':True,'children':{'semi-select-clear':[clear]}}
  placeholder['children']['semi-select']=[select]
  page.selectors['div.semi-select span:has-text("输入地理位置")']=[placeholder]
  await guards.clear_douyin_location(page)
  self.assertTrue(placeholder['visible']); self.assertEqual(clear.get('clicks'), 1)
 async def test_douyin_location_that_stays_filled_stops_publish(self):
  page=Page(); placeholder={'text':'输入地理位置','visible':False,'children':{'semi-select':[{'visible':True,'children':{}}]}}
  page.selectors['div.semi-select span:has-text("输入地理位置")']=[placeholder]
  with self.assertRaises(RuntimeError) as caught: await guards.clear_douyin_location(page)
  self.assertIn('没有清掉', str(caught.exception))
 async def test_original_claim_must_stay_checked(self):
  page=Page(); box={'role':'checkbox','name':'声明原创','checked':False,'on_click':lambda node: node.__setitem__('checked', True)}
  page.roles.append(box)
  await guards.apply_original_claim(page, platform_name='视频号')
  self.assertTrue(box['checked']); self.assertEqual(box['clicks'], 1)
 async def test_original_claim_already_checked_is_not_clicked_again(self):
  page=Page(); box={'role':'checkbox','name':'声明原创','checked':True,'clicks':0,'on_click':lambda node: node.__setitem__('checked', False)}
  page.roles.append(box)
  await guards.apply_original_claim(page, platform_name='抖音')
  self.assertEqual(box['clicks'], 0); self.assertTrue(box['checked'])
 async def test_original_claim_disabled_or_unselected_stops_publish(self):
  disabled=Page(); box={'role':'checkbox','name':'视频为原创','disabled':True,'clicks':0}
  disabled.roles.append(box)
  with self.assertRaises(RuntimeError) as caught: await guards.apply_original_claim(disabled, platform_name='视频号')
  self.assertIn('不可用', str(caught.exception)); self.assertEqual(box['clicks'], 0)
  missed=Page()
  with self.assertRaises(RuntimeError) as caught: await guards.apply_original_claim(missed, platform_name='抖音')
  self.assertIn('声明原创', str(caught.exception))
  stuck=Page(); stubborn={'role':'checkbox','name':'声明原创','checked':False}
  stuck.roles.append(stubborn)
  with self.assertRaises(RuntimeError) as caught: await guards.apply_original_claim(stuck, platform_name='视频号')
  self.assertIn('没有保持勾选', str(caught.exception))
 async def test_channels_ai_label_must_replace_the_placeholder(self):
  page=Page(); option={'text':'含AI生成内容','visible':False}
  entry={'text':'选择视频标注','visible':True,'on_click':lambda _node: option.__setitem__('visible', True)}
  def choose(_node):
   entry['visible']=False; option['visible']=True
  option['on_click']=choose
  page.texts.extend([entry, option])
  await guards.apply_tencent_ai_label(page)
  self.assertFalse(entry['visible']); self.assertTrue(option['visible'])
 async def test_channels_ai_label_failure_stops_publish(self):
  page=Page(); page.texts.append({'text':'选择视频标注','visible':True})
  with self.assertRaises(RuntimeError) as caught: await guards.apply_tencent_ai_label(page)
  self.assertIn('含AI生成内容', str(caught.exception))

if __name__=='__main__': unittest.main()
