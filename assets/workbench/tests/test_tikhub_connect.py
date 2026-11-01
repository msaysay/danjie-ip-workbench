import json, os, sys, tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import classroom_research as research
import server as s


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self.ok = status < 400
        self.text = json.dumps(body)

    def json(self):
        return json.loads(self.text)


class TikHubConnectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA, s.DB
        s.DATA = Path(self.temp.name)
        s.DB = s.DATA / 'test.sqlite3'
        with s.connect() as c:
            c.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
        self.client = TestClient(s.app)
        self.headers = {'x-workbench-token': s.TOKEN}
        self.requests = research.requests.request

    def tearDown(self):
        research.requests.request = self.requests
        s.DATA, s.DB = self.old
        self.temp.cleanup()

    def post(self, path, data):
        return self.client.post('/api' + path, json=data, headers=self.headers)

    def test_status_links_do_not_need_a_real_key(self):
        hub = research.TikHub(Path(self.temp.name) / 'connections')
        body = hub.status()
        self.assertFalse(body['configured'])
        self.assertIn('ref=u58I2I4n', body['register_url'])
        self.assertTrue(body['console_url'].endswith('/dashboard/api'))
        self.assertIn('docs.tikhub.io', body['docs_url'])
        self.assertIn('tikhub.io', body['site_url'])
        if sys.platform != 'darwin' and os.name != 'nt':
            self.assertEqual(body['storage'], 'dev_plaintext')
            self.assertIn('开发', body['storage_note'])
        remote = self.client.get('/api/classroom/status').json()['research']
        self.assertIn('ref=u58I2I4n', remote['register_url'])
        self.assertIn('console_url', remote)

    def test_fake_key_failure_is_readable_and_success_stores_suffix_only(self):
        folder = Path(self.temp.name) / 'connections'
        hub = research.TikHub(folder)

        def unauthorized(*args, **kwargs):
            return Response(401, {'detail': {'message_zh': '无效'}})

        research.requests.request = unauthorized
        with self.assertRaises(ValueError) as failure:
            hub.connect('fake-key-123456')
        self.assertIn('密钥不对', str(failure.exception))
        self.assertFalse(hub.file.exists())

        def ok(*args, **kwargs):
            return Response(200, {'code': 200, 'data': {}})

        research.requests.request = ok
        secret = 'fake-key-123456'
        status = hub.connect(secret)
        self.assertTrue(status['configured'])
        self.assertEqual(status['suffix'], secret[-4:])
        self.assertNotIn(secret, json.dumps(status))
        if sys.platform != 'darwin' and os.name != 'nt':
            raw = hub.file.read_bytes()
            self.assertTrue(raw.startswith(research.DEV_PLAIN))
            self.assertEqual(research.protect(raw, True).decode(), secret)

    def test_quota_and_network_errors_do_not_retry(self):
        hub = research.TikHub(Path(self.temp.name) / 'connections')

        def quota(*args, **kwargs):
            return Response(402, {'detail': {'message_zh': '余额不足，本次不会被扣费'}})

        research.requests.request = quota
        with self.assertRaises(ValueError) as failure:
            hub.call('user_info', {}, key='fake-key-123456')
        text = str(failure.exception)
        self.assertIn('额度不够', text)
        self.assertIn('不会自动重试', text)
        self.assertIn('不扣费', text)

        def down(*args, **kwargs):
            raise research.requests.RequestException('timed out')

        research.requests.request = down
        with self.assertRaises(ValueError) as failure:
            hub.call('user_info', {}, key='fake-key-123456')
        self.assertIn('连不上 TikHub', str(failure.exception))

    def test_learner_cannot_create_or_login_a_xiaohongshu_publish_account(self):
        created = self.post('/accounts', {'platform': 'xiaohongshu', 'alias': 'xhs_test', 'label': '笔记'})
        self.assertEqual(created.status_code, 400)
        self.assertIn('不提供发布到小红书', created.json()['detail'])
        douyin = self.post('/accounts', {'platform': 'douyin', 'alias': 'dy_test', 'label': '抖音'})
        self.assertEqual(douyin.status_code, 200)
        s.put('account', {'id': 'xh1', 'platform': 'xiaohongshu', 'alias': 'xhs_old', 'label': '旧账号', 'status': '未验证'})
        login = self.post('/accounts/xh1/login', {})
        self.assertEqual(login.status_code, 400)
        self.assertIn('不提供发布到小红书', login.json()['detail'])
        platforms = self.client.get('/api/state').json()['platforms']
        self.assertNotIn('xiaohongshu', platforms)
        self.assertIn('douyin', platforms)
        self.assertIn('tencent', platforms)
        prompt = (APP / 'server.py').read_text(encoding='utf-8')
        self.assertNotIn('抖音、视频号、小红书', prompt)
        routes = research.ROUTES
        self.assertIn('xiaohongshu_search', routes)
        self.assertIn('xiaohongshu_account', routes)
        self.assertIn('xiaohongshu_user_search', routes)


    def test_weibo_account_id_comes_from_user_url(self):
        rows = research.normalize({'results': [{
            'id': 'post1', 'text': '开店前先核对哪一项材料',
            'user_url': 'https://weibo.com/u/99887766', 'user': {'screen_name': '演示作者'},
        }]}, 'weibo', 'keyword', '开店')
        self.assertEqual(rows[0]['account_key'], '99887766')
        self.assertEqual(rows[0]['author'], '演示作者')
        bare = research.normalize({'results': [{
            'id': 'post2', 'text': '另一条微博内容',
            'user_url': 'https://www.weibo.com/112233', 'user': {'screen_name': '另一个'},
        }]}, 'weibo', 'keyword', '开店')
        self.assertEqual(bare[0]['account_key'], '112233')

    def test_account_search_uses_user_lists_and_platform_ids(self):
        hub = s.CLASSROOM['tikhub']
        old_status, old_call = hub.status, hub.call
        box = {}
        hub.status = lambda: {'configured': True, 'suffix': 'demo'}
        hub.call = lambda route, payload, key=None: box['payload']
        try:
            box['payload'] = {'data': {'filters': [{'id': 'all', 'name': '全部'}], 'users': [{'nickname': '笔记作者', 'user_id': 'xhs-user-1'}]}}
            found = self.post('/experience/research/accounts/search', {'platform': 'xiaohongshu', 'keyword': '笔记'})
            self.assertEqual(found.status_code, 200, found.text)
            self.assertEqual([(item['name'], item['account_key']) for item in found.json()['items']], [('笔记作者', 'xhs-user-1')])

            box['payload'] = {'data': {'user_list': [{'nickname': '抖音作者', 'sec_uid': 'MS4wLjABAAAAdemo'}, {'nickname': '短号', 'user_id': '123'}]}}
            found = self.post('/experience/research/accounts/search', {'platform': 'douyin', 'keyword': '作者'})
            self.assertEqual(found.status_code, 200, found.text)
            self.assertEqual([(item['name'], item['account_key']) for item in found.json()['items']], [('抖音作者', 'MS4wLjABAAAAdemo')])

            box['payload'] = {'data': {'items': [
                {'title': '<em>演示</em>公众号', 'jumpInfo': {'userName': 'gh_demo123'}},
                {'title': '不是号', 'jumpInfo': {'userName': 'not_a_account'}},
            ]}}
            found = self.post('/experience/research/accounts/search', {'platform': 'wechat', 'keyword': '演示'})
            self.assertEqual(found.status_code, 200, found.text)
            self.assertEqual([(item['name'], item['account_key']) for item in found.json()['items']], [('演示公众号', 'gh_demo123')])

            box['payload'] = {'data': {'items': [
                {'title': '我的视频号', 'jumpInfo': {'userName': 'v2_abc@finder'}},
                {'title': '普通用户', 'jumpInfo': {'userName': 'gh_notfinder'}},
            ]}}
            found = self.post('/experience/research/accounts/search', {'platform': 'tencent', 'keyword': '视频号'})
            self.assertEqual(found.status_code, 200, found.text)
            self.assertEqual([(item['name'], item['account_key']) for item in found.json()['items']], [('我的视频号', 'v2_abc@finder')])
        finally:
            hub.status, hub.call = old_status, old_call


if __name__ == '__main__':
    unittest.main()
