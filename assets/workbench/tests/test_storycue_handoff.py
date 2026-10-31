import sys, json, os, logging, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient
APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server as s
import storycue_api
import requests
from fake_storycue import FakeStoryCue

SPEECH = 'vk-storycue-speech-DO-NOT-LEAK'
TEXT = 'vk-storycue-text-DO-NOT-LEAK'
ECHO = 'echo-vk-storycue-LEAK-this-key'


class StoryCueHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA, s.DB
        s.DATA = Path(self.temp.name)
        s.DB = s.DATA / 'test.sqlite3'
        with s.connect() as db:
            db.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
        self.fake = FakeStoryCue(Path(self.temp.name) / 'storycue')
        self.old_origin = os.environ.get('STORYCUE_ORIGIN')
        os.environ['STORYCUE_ORIGIN'] = self.fake.origin
        self.client = TestClient(s.app)
        self.headers = {'x-workbench-token': s.TOKEN}
        self.logs = []
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.logs.append(record.getMessage())
        logging.getLogger().addHandler(self.handler)
        logging.getLogger().setLevel(logging.INFO)

    def tearDown(self):
        logging.getLogger().removeHandler(self.handler)
        self.fake.stop()
        if self.old_origin is None:
            os.environ.pop('STORYCUE_ORIGIN', None)
        else:
            os.environ['STORYCUE_ORIGIN'] = self.old_origin
        s.DATA, s.DB = self.old
        self.temp.cleanup()

    def post(self, path, data):
        return self.client.post('/api' + path, json=data, headers=self.headers)

    def profile(self):
        memory = {'kind': 'business_memory', 'schema': 'danjie-business-memory/1', 'id': 'memory', 'owner': '测试学员（模拟）', 'business': '独立虚构业务', 'mode': 'fictional_demo', 'assets': [], 'notes': []}
        s.put('project', {'id': 'p', 'title': '测试业务', 'sources': [memory], 'segments': []})
        s.put('workflow_settings', {'id': 'main', 'profile_id': 'p', 'time': '08:30', 'count': 5, 'enabled': False})

    def ready(self, script, parts=None, demo=True):
        self.profile()
        framework = parts or [
            {'key': 'opening', 'label': '开头', 'skill': '03', 'text': '先别按别人的结论开口。这次虚构任务要先核对材料。'},
            {'key': 'reason', 'label': '支撑', 'skill': '04', 'text': '核对方法只有一条：对照已接回的选题原句，缺的就留空。'},
            {'key': 'identity', 'label': '身份', 'skill': '05', 'text': '我是这次课堂演练里的测试学员，没有可公开的成绩。'},
            {'key': 'ending', 'label': '收尾', 'skill': '06', 'text': '看完先做一件事：把还没接回的材料留空。'},
        ]
        return s.put('writing_topic', {'id': 'topic1', 'title': '本次虚构任务应该先核对哪项材料？', 'audience': '虚构测试里的学员本人', 'reason': '课堂演练', 'framework': framework, 'script': script, 'stage': 'ready', 'confirmed': True, 'demo': demo, 'history': [], 'profile_id': 'p', 'created': s.now()})

    def use_directory(self):
        response = self.post('/storycue/directory', {'directory': str(self.fake.root), 'speechKey': SPEECH})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['tokenReady'])
        self.assertNotIn(SPEECH, response.text)
        return response

    def saved_bytes(self):
        blob = b''
        for path in [s.DB, Path(str(s.DB) + '-wal'), Path(str(s.DB) + '-shm')]:
            if path.exists():
                blob += path.read_bytes()
        return blob

    def assert_absent(self, secret, response=None):
        if response is not None:
            self.assertNotIn(secret, response.text)
        self.assertNotIn(secret.encode(), self.saved_bytes())
        self.assertNotIn(secret, '\n'.join(self.logs))

    def test_migration_creates_storycue_link(self):
        self.use_directory()
        with s.connect() as db:
            versions = [row[0] for row in db.execute('SELECT version FROM schema_migrations')]
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertIn('001_storycue_interview', versions)
        self.assertIn('storycue_link', tables)

    def test_directory_keeps_only_the_path_and_status_hides_the_token(self):
        response = self.use_directory()
        self.assertIn(str(self.fake.root), response.json()['directory'])
        self.assertNotIn(self.fake.token, response.text)
        self.assertIn('VOICE_RELAY_PORT=8866', response.json()['start']['windows'])
        self.assertIn('npm run dev', response.json()['start']['mac'])
        self.assertEqual(response.json()['commands']['doctor'], 'npm run desktop:doctor')
        self.assert_absent(SPEECH, response)
        with s.connect() as db:
            body = db.execute("SELECT body FROM records WHERE kind='storycue_settings'").fetchone()[0]
        self.assertNotIn(SPEECH, body)
        self.assertIn(str(self.fake.root), body)

    def test_setup_proxy_writes_storycue_env_only_and_redacts_echoed_keys(self):
        self.use_directory()
        (self.fake.data / 'desktop-verification.json').write_text(json.dumps({'verified': True, 'checkedAt': datetime.now(timezone.utc).isoformat(), 'host': 'codex'}), encoding='utf-8')
        saved = self.post('/storycue/setup', {'speechKey': SPEECH, 'textKey': TEXT, 'llmBaseUrl': 'https://ark.cn-beijing.volces.com/api/v3', 'llmModel': 'doubao-seed-2-0-lite-260428', 'enableJev': False, 'jevKey': ''})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()['saved'])
        self.assert_absent(SPEECH, saved)
        self.assert_absent(TEXT, saved)
        env = self.fake.read_env()
        self.assertEqual(env['DOUBAO_API_KEY'], SPEECH)
        self.assertEqual(env['RELAY_LLM_API_KEY'], TEXT)
        self.assertEqual(oct(self.fake.env_path().stat().st_mode & 0o777), '0o600')
        speech = self.post('/storycue/setup/test', {'target': 'doubao_tts'})
        asr = self.post('/storycue/setup/test', {'target': 'doubao_asr'})
        text = self.post('/storycue/setup/test', {'target': 'text_llm'})
        jev = self.post('/storycue/setup/test', {'target': 'jev'})
        desktop = self.post('/storycue/setup/test', {'target': 'desktop'})
        self.assertTrue(speech.json()['ok'] and asr.json()['ok'] and text.json()['ok'] and jev.json()['ok'] and desktop.json()['ok'])
        self.assertEqual(speech.json()['code'], 'ok')
        self.assertIn('语音', speech.json()['message'])
        self.assertEqual(jev.json()['code'], 'disabled')
        self.assertIn('未启用', jev.json()['message'])
        wrong = self.post('/storycue/setup', {'speechKey': 'ark-not-a-voice-key-123456', 'textKey': TEXT, 'llmBaseUrl': 'https://ark.cn-beijing.volces.com/api/v3', 'llmModel': 'doubao-seed-2-0-lite-260428', 'enableJev': False})
        self.assertEqual(wrong.status_code, 200, wrong.text)
        rejected = self.post('/storycue/setup/test', {'target': 'doubao_tts'})
        self.assertFalse(rejected.json()['ok'])
        self.assertEqual(rejected.json()['code'], 'ark_key_misused')
        self.assertIn('方舟', rejected.json()['message'])
        echoed = self.post('/storycue/setup', {'speechKey': ECHO, 'textKey': TEXT, 'llmBaseUrl': 'https://ark.cn-beijing.volces.com/api/v3', 'llmModel': 'm', 'enableJev': False})
        self.assertGreaterEqual(echoed.status_code, 400)
        self.assertIn('[redacted]', echoed.text)
        self.assert_absent(ECHO, echoed)

    def test_unreachable_storycue_and_launch_do_not_carry_keys(self):
        self.use_directory()
        os.environ['STORYCUE_ORIGIN'] = 'http://127.0.0.1:9'
        try:
            missing = self.post('/storycue/setup/test', {'target': 'desktop'})
        finally:
            os.environ['STORYCUE_ORIGIN'] = self.fake.origin
        self.assertEqual(missing.status_code, 503)
        self.assertIn('VOICE_RELAY_PORT=8866', missing.text)
        self.assertIn('npm run dev', missing.text)
        self.assertIn('set VOICE_RELAY_PORT=8866&& npm run dev', missing.text)
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured['cmd'] = cmd
            captured['env'] = kwargs['env']
            class Process:
                pid = 4321
            return Process()

        old = storycue_api.POPEN
        os.environ['DOUBAO_API_KEY'] = SPEECH
        storycue_api.POPEN = fake_popen
        try:
            started = self.post('/storycue/start', {})
        finally:
            storycue_api.POPEN = old
            os.environ.pop('DOUBAO_API_KEY', None)
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(captured['env']['VOICE_RELAY_PORT'], '8866')
        self.assertNotIn('DOUBAO_API_KEY', captured['env'])
        self.assertNotIn(SPEECH, captured['env'].values())
        self.assertTrue(any(part == 'dev' for part in captured['cmd']))
        old_post = storycue_api.requests.post

        def boom(*args, **kwargs):
            raise requests.RequestException('failed ' + SPEECH)

        storycue_api.requests.post = boom
        try:
            failed = self.post('/storycue/setup', {'speechKey': SPEECH, 'textKey': TEXT, 'llmBaseUrl': 'https://ark.cn-beijing.volces.com/api/v3', 'llmModel': 'm', 'enableJev': False})
        finally:
            storycue_api.requests.post = old_post
        self.assertEqual(failed.status_code, 503)
        self.assert_absent(SPEECH, failed)

    def test_background_sha_handoff_and_framework_suggestion(self):
        long = '核' * 500
        parts = [
            {'key': 'opening', 'label': '开头', 'skill': '03', 'text': '当头先核对。' + long},
            {'key': 'reason', 'label': '支撑', 'skill': '04', 'text': '第一步的具体做法是留空。' + long},
            {'key': 'identity', 'label': '身份', 'skill': '05', 'text': '我是演练学员。' + long},
            {'key': 'ending', 'label': '收尾', 'skill': '06', 'text': '看完就停。' + long},
        ]
        script = '\n\n'.join(part['text'] for part in parts)
        topic = self.ready(script, parts)
        background = storycue_api.compress_background(topic)
        self.assertLessEqual(len(background), 1200)
        self.assertIn('开头', background)
        self.assertIn('支撑', background)
        self.assertEqual(storycue_api.suggest_framework(topic)['id'], '抄近路')
        plain = self.ready('先别按别人的结论开口。\n\n核对方法只有一条。\n\n我是测试学员。\n\n把缺口留空。')
        self.assertEqual(storycue_api.suggest_framework(plain)['id'], '北极星')
        self.use_directory()
        before = s.get('writing_topic', 'topic1')['revision']
        sent = self.post('/workflow/topics/topic1/storycue/handoff', {'framework': '北极星'})
        self.assertEqual(sent.status_code, 200, sent.text)
        body = sent.json()
        self.assertEqual(body['handoffId'], 'topic1-' + str(before))
        self.assertEqual(body['scriptSha256'], storycue_api.script_sha256(plain['script']))
        self.assertLessEqual(body['backgroundChars'], 1200)
        self.assertTrue(body['demo'])
        self.assertTrue(body['openUrl'].endswith('/trial?handoff=' + body['handoffId']))
        self.assertEqual(s.get('writing_topic', 'topic1')['revision'], before)
        stored = json.loads((self.fake.handoffs / (body['handoffId'] + '.json')).read_text(encoding='utf-8'))
        self.assertTrue(stored['createdAt'].endswith('Z'))
        self.assertEqual(stored['schema'], 'danjie.storycue-handoff.v1')
        self.assertLessEqual(len(stored['background']), 1200)
        self.assertEqual(stored['scriptSha256'], body['scriptSha256'])
        missing = self.post('/workflow/topics/topic1/storycue/result/pull', {})
        self.assertEqual(missing.status_code, 404)
        sample = json.loads((self.fake.handoffs / (body['handoffId'] + '.json')).read_text(encoding='utf-8'))
        from fake_storycue import sample_result
        result = sample_result(sample)
        seeded = requests.post(self.fake.origin + '/api/trial/handoff/' + body['handoffId'] + '/result', headers={'X-StoryCue-Bridge-Token': self.fake.token}, json=result, timeout=5)
        self.assertEqual(seeded.status_code, 200, seeded.text)
        pulled = self.post('/workflow/topics/topic1/storycue/result/pull', {})
        self.assertEqual(pulled.status_code, 200, pulled.text)
        self.assertIn('缺的材料继续留空', pulled.text)
        self.assertTrue(pulled.json()['demo'])
        self.assertTrue(pulled.json()['interview']['demo'])
        panel = self.client.get('/api/workflow/topics/topic1/storycue/panel').json()
        self.assertEqual(panel['interview']['entries'][1]['role'], '嘉宾')
        s.patch('writing_topic', 'topic1', {'script': plain['script'] + '\n\n这句话把确认稿改掉了。', 'stage': 'ready'})
        rejected = self.post('/workflow/topics/topic1/storycue/result/pull', {})
        self.assertEqual(rejected.status_code, 409)
        self.assertIn('脚本已改过，请重新访谈或确认沿用', rejected.text)
        with s.connect() as db:
            kept = db.execute('SELECT result_json FROM storycue_link WHERE topic_id=?', ('topic1',)).fetchone()[0]
        self.assertIn('缺的材料继续留空', kept)
        foreign = dict(result)
        foreign['topicId'] = 'someone-else'
        foreign['scriptSha256'] = storycue_api.script_sha256(s.get('writing_topic', 'topic1')['script'])
        mismatched = self.post('/workflow/topics/topic1/storycue/result', foreign)
        self.assertEqual(mismatched.status_code, 409)
        self.assertIn('不属于当前选题', mismatched.text)
        unmarked = dict(result)
        unmarked['demo'] = False
        unmarked['scriptSha256'] = storycue_api.script_sha256(s.get('writing_topic', 'topic1')['script'])
        unmarked['topicId'] = 'topic1'
        demo_rejected = self.post('/workflow/topics/topic1/storycue/result', unmarked)
        self.assertEqual(demo_rejected.status_code, 400)
        self.assertIn('demo', demo_rejected.text)

    def test_sayframe_payload_includes_interview_only_when_present(self):
        topic = self.ready('课堂演练的确认稿。')
        empty = storycue_api.assemble_sayframe_handoff(topic, framework='北极星')
        self.assertEqual(empty['schema'], 'danjie.sayframe-handoff.v1')
        self.assertIsNone(empty['interview'])
        self.assertEqual(empty['script'], topic['script'])
        self.assertEqual(empty['framework'], '北极星')
        self.assertEqual(empty['mediaPath'], '')
        interview = {'schema': 'storycue.interview-export.v1', 'framework': '四喜', 'topicId': topic['id'], 'demo': True}
        full = storycue_api.assemble_sayframe_handoff(topic, interview)
        self.assertEqual(full['interview']['framework'], '四喜')
        self.assertEqual(full['script'], topic['script'])
        self.assertNotIn('http', json.dumps(full))

    def test_topic_id_and_overlong_script_are_rejected_before_storycue(self):
        self.profile()
        s.put('writing_topic', {'id': '-bad', 'title': '编号不合格', 'audience': '学员', 'framework': [], 'script': '确认稿', 'stage': 'ready', 'confirmed': True, 'demo': True, 'history': [], 'profile_id': 'p', 'created': s.now()})
        self.use_directory()
        rejected = self.post('/workflow/topics/-bad/storycue/handoff', {'framework': '北极星'})
        self.assertEqual(rejected.status_code, 400)
        self.assertIn('字母、数字', rejected.text)
        self.assertFalse(list(self.fake.handoffs.glob('*.json')))
        huge = '稿' * 100_001
        s.put('writing_topic', {'id': 'huge1', 'title': '太长', 'audience': '学员', 'framework': [{'key': 'opening', 'label': '开头', 'skill': '03', 'text': '开头'}, {'key': 'reason', 'label': '支撑', 'skill': '04', 'text': '支撑'}, {'key': 'identity', 'label': '身份', 'skill': '05', 'text': '身份'}, {'key': 'ending', 'label': '收尾', 'skill': '06', 'text': '收尾'}], 'script': huge, 'stage': 'ready', 'confirmed': True, 'demo': True, 'history': [], 'profile_id': 'p', 'created': s.now()})
        too_long = self.post('/workflow/topics/huge1/storycue/handoff', {'framework': '北极星'})
        self.assertEqual(too_long.status_code, 413, too_long.text)
        self.assertIn('100000', too_long.text)
        self.assertFalse((self.fake.handoffs / 'huge1-1.json').exists())

    def test_unconfirmed_script_is_not_handed_off(self):
        self.profile()
        s.put('writing_topic', {'id': 'draft1', 'title': '还没确认', 'audience': '学员', 'framework': [], 'script': '草稿', 'stage': 'script', 'confirmed': False, 'demo': True, 'history': [], 'profile_id': 'p', 'created': s.now()})
        self.use_directory()
        response = self.post('/workflow/topics/draft1/storycue/handoff', {'framework': '北极星'})
        self.assertEqual(response.status_code, 409)
        self.assertIn('先确认', response.text)


if __name__ == '__main__':
    unittest.main()
