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


if __name__ == '__main__':
    unittest.main()
