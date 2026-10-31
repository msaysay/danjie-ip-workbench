import json, os, sys, tempfile, time, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import desktop_cli
import server as s
import writing_host

ZONE = timezone(timedelta(hours=8))


def today():
    return datetime.now(ZONE).date().isoformat()


class DesktopCliTests(unittest.TestCase):
    def test_path_and_npm_package_are_reported_without_running_the_cli(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(root, ignore_errors=True))
        home = root / 'home'
        npm = root / 'npm'
        (npm / '@openai' / 'codex').mkdir(parents=True)
        (npm / '@openai' / 'codex' / 'package.json').write_text('{"name":"@openai/codex"}', encoding='utf-8')
        binary = home / '.local' / 'bin' / 'codebuddy'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\n', encoding='utf-8')

        def which(name):
            return '/usr/bin/codex' if name == 'codex' else None

        found = desktop_cli.desktop_cli_location(which=which, home=home, npm_root=npm)
        by_id = {item['id']: item for item in found['hosts']}
        self.assertEqual(by_id['codex']['package'], '@openai/codex')
        self.assertEqual(by_id['codex']['via'], ['path', 'npm'])
        self.assertTrue(by_id['codex']['found'])
        self.assertEqual(by_id['codex']['path'], '/usr/bin/codex')
        self.assertEqual(by_id['workbuddy']['package'], '@tencent-ai/codebuddy-code')
        self.assertEqual(by_id['workbuddy']['via'], ['path'])
        self.assertEqual(by_id['workbuddy']['path'], str(binary))
        self.assertNotIn('npm', by_id['workbuddy']['via'])

    def test_missing_cli_is_a_normal_result(self):
        found = desktop_cli.desktop_cli_location(which=lambda name: None, home=Path('/no/such/home'), npm_root='')
        self.assertEqual([item['found'] for item in found['hosts']], [False, False])
        self.assertEqual(found['npmError'], '')


class WritingHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA, s.DB
        s.DATA = Path(self.temp.name)
        s.DB = s.DATA / 'test.sqlite3'
        with s.connect() as db:
            db.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
        self.client = TestClient(s.app)
        self.headers = {'x-workbench-token': s.TOKEN}

    def tearDown(self):
        s.DATA, s.DB = self.old
        self.temp.cleanup()

    def post(self, path, data):
        return self.client.post('/api' + path, json=data, headers=self.headers)

    def profile(self):
        memory = {'kind': 'business_memory', 'schema': 'danjie-business-memory/1', 'id': 'memory', 'owner': '测试学员', 'business': '独立虚构业务', 'mode': 'fictional_demo', 'assets': [], 'notes': []}
        s.put('project', {'id': 'p', 'title': '测试业务', 'sources': [memory], 'segments': []})
        s.put('workflow_settings', {'id': 'main', 'profile_id': 'p', 'time': '08:30', 'count': 5, 'enabled': False})
        return memory

    def test_blank_status_offers_both_hosts_and_does_not_ask_for_a_base_url(self):
        status = self.client.get('/api/writing/host').json()
        self.assertEqual(status['host'], '')
        self.assertEqual([item['id'] for item in status['hosts']], ['workbuddy', 'codex'])
        self.assertEqual(status['hosts'][0]['package'], '@tencent-ai/codebuddy-code')
        self.assertEqual(status['hosts'][1]['package'], '@openai/codex')
        self.assertFalse(status['ready'])
        self.assertEqual(status['prompt'], '')
        self.assertNotIn('Base URL', json.dumps(status, ensure_ascii=False))
        storycue = self.client.get('/api/storycue/status').json()
        self.assertEqual([item['id'] for item in storycue['desktopCli']['hosts']], ['workbuddy', 'codex'])

    def test_host_choice_survives_and_rejects_other_values(self):
        denied = self.post('/writing/host', {'host': 'browser'})
        self.assertEqual(denied.status_code, 400)
        saved = self.post('/writing/host', {'host': 'codex'})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['host'], 'codex')
        self.assertEqual(self.client.get('/api/writing/host').json()['host'], 'codex')

    def test_manual_file_without_cli_can_sync_and_turn_ready(self):
        self.profile()
        self.post('/writing/host', {'host': 'workbuddy'})
        prepared = self.post('/experience/business/prepare', {})
        self.assertEqual(prepared.status_code, 200)
        folder = s.project_dir('p') / 'workbuddy-business'
        before = self.client.get('/api/writing/host').json()
        self.assertIn(str(folder.resolve()), before['prompt'])
        self.assertIn('今日选题.json', before['prompt'])
        self.assertIn('generated_by', before['prompt'])
        self.assertIn('这次由WorkBuddy来写', before['prompt'])
        self.assertNotIn('Base URL', before['prompt'])
        self.assertNotIn('WORKBENCH_MODEL', before['prompt'])
        self.assertFalse(before['ready'])
        topic = {'title': '先核对哪一项材料', 'audience': '虚构学员', 'reason': '对应这份虚构核对问题', 'needs': [1], 'framework': [
            {'key': 'opening', 'text': '开头要先核对材料，不要把演练写成已经发生的事。'},
            {'key': 'reason', 'text': '对照已经接回的原句，缺的就标成还不知道。'},
            {'key': 'identity', 'text': '我是这次课堂演练里的测试学员，只说明自己在核对材料。'},
            {'key': 'ending', 'text': '看完先把还没接回的材料留空。'},
        ]}
        payload = {'profile_id': 'p', 'mode': 'fictional_demo', 'date': today(), 'topics': [topic]}
        target = folder / '今日选题.json'
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        parked = self.client.get('/api/writing/host').json()
        self.assertTrue(parked['topicFile']['exists'])
        self.assertTrue(parked['topicFile']['matchesToday'])
        self.assertTrue(parked['ready'])
        self.assertFalse(parked['syncedToday'])
        synced = self.post('/experience/business/sync', {})
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertEqual(synced.json()['errors'], [])
        after = self.client.get('/api/writing/host').json()
        self.assertTrue(after['syncedToday'])
        self.assertEqual(after['todayCount'], 1)
        self.assertTrue(after['ready'])
        self.assertEqual(s.listing('writing_topic')[0]['stage'], 'topic')

    def test_yesterday_file_is_not_treated_as_today(self):
        self.profile()
        self.post('/experience/business/prepare', {})
        folder = s.project_dir('p') / 'workbuddy-business'
        yesterday = (datetime.now(ZONE).date() - timedelta(days=1)).isoformat()
        target = folder / '今日选题.json'
        target.write_text(json.dumps({'date': yesterday, 'topics': []}, ensure_ascii=False), encoding='utf-8')
        stamp = time.time() - 3 * 24 * 3600
        os.utime(target, (stamp, stamp))
        status = self.client.get('/api/writing/host').json()
        self.assertTrue(status['topicFile']['exists'])
        self.assertFalse(status['topicFile']['matchesToday'])
        self.assertFalse(status['topicFile']['writtenToday'])
        self.assertFalse(status['ready'])

    def test_symlink_topic_file_is_ignored(self):
        self.profile()
        self.post('/experience/business/prepare', {})
        folder = s.project_dir('p') / 'workbuddy-business'
        outside = Path(self.temp.name) / 'outside.json'
        outside.write_text('{"date":"%s"}' % today(), encoding='utf-8')
        (folder / '今日选题.json').symlink_to(outside)
        status = self.client.get('/api/writing/host').json()
        self.assertFalse(status['topicFile']['exists'])
        self.assertFalse(status['ready'])

    def test_ready_rule_accepts_sync_or_todays_file(self):
        self.assertFalse(writing_host.writing_ready({'exists': False}, False))
        self.assertTrue(writing_host.writing_ready({'exists': True, 'matchesToday': False, 'writtenToday': False}, True))
        self.assertTrue(writing_host.writing_ready({'exists': True, 'matchesToday': True, 'writtenToday': False}, False))
        self.assertTrue(writing_host.writing_ready({'exists': True, 'matchesToday': False, 'writtenToday': True}, False))
        self.assertFalse(writing_host.writing_ready({'exists': True, 'matchesToday': False, 'writtenToday': False}, False))


if __name__ == '__main__':
    unittest.main()
