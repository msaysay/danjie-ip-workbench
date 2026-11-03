import hashlib, json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import server as s


def analysis(title='先核对材料'):
    return {
        'summary': '这条只说了先核对材料',
        'points': ['先核对，再对外说'],
        'limits': ['没有讲做法和结果'],
        'platform_copy': {
            'douyin': {'title': title, 'desc': '成片里只说了先核对', 'tags': '核对'},
            'tencent': {'title': title, 'short_title': '先把材料核对完', 'desc': '成片里只说了先核对', 'tags': '核对'},
        },
    }


def host_body(ident, sha, transcript='先核对材料再对外说。', title='先核对材料'):
    return {
        'project_id': ident,
        'video_sha256': sha,
        'generated_by': 'Codex',
        'transcript': transcript,
        'understanding': analysis(title),
    }


class PublishUnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA, s.DB
        s.DATA = Path(self.temp.name)
        s.DB = s.DATA / 'test.sqlite3'
        with s.connect() as db:
            db.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
        self.client = TestClient(s.app)
        self.headers = {'x-workbench-token': s.TOKEN}
        self.located = {'hosts': [
            {'id': 'workbuddy', 'label': 'WorkBuddy', 'found': True, 'path': '/tmp/codebuddy', 'command': 'codebuddy'},
            {'id': 'codex', 'label': 'Codex', 'found': False, 'path': '', 'command': 'codex'},
        ]}

    def tearDown(self):
        s.DATA, s.DB = self.old
        self.temp.cleanup()

    def post(self, path, data=None):
        return self.client.post('/api' + path, json=data, headers=self.headers)

    def video(self, ident):
        folder = s.project_dir(ident) / 'finished'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / 'clip.mp4'
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=0x3366aa:s=320x240:d=1', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(target)], check=True)
        raw = target.read_bytes()
        info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(target)], text=True))
        return {'kind': 'finished_video', 'file': target.relative_to(s.DATA).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(), 'duration': float(info['format']['duration']), 'edit_hash': 'finished'}

    def project(self, ident='clip1', **extra):
        output = extra.pop('output', None) or self.video(ident)
        s.put('project', {'id': ident, 'title': '测试成片', 'platform_copy': {'douyin': {'title': '学员写的标题', 'desc': '', 'tags': '', 'schedule': '2026-12-01 10:00'}, 'tencent': {'title': '学员写的标题', 'desc': '', 'tags': '', 'schedule': '2026-12-01 10:00'}}, 'output': output, 'publish_preparation': {'cover_state': 'cleared'}, **extra})
        return s.get('project', ident)

    def wait_job(self, job_id):
        deadline = time.time() + 20
        last = None
        while time.time() < deadline:
            last = next(row for row in s.listing('job') if row['id'] == job_id)
            if last['state'] != 'running':
                return last
            time.sleep(0.05)
        self.fail('job did not finish: ' + json.dumps(last, ensure_ascii=False))

    def test_missing_whisper_hands_off_without_blocking(self):
        project = self.project()
        env = {'WORKBENCH_MODEL': '', 'WORKBENCH_MODEL_BASE_URL': ''}
        with patch.dict(os.environ, env, clear=False), patch('semantic_delivery.whisper_available', return_value=False), patch('publish_understanding.desktop_cli_location', return_value=self.located):
            s.put('writing_host', {'id': 'main', 'host': 'codex'})
            response = self.post('/projects/clip1/prepare-delivery')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body['handoff'])
        self.assertEqual(body['reason'], 'both')
        self.assertEqual(body['host'], 'codex')
        self.assertNotIn('state', body)
        self.assertNotIn('install_optional', body['message'])
        self.assertIn('不是抖音或视频号的扫码', body['message'])
        self.assertIn('不会发布', body['message'])
        self.assertFalse(any(row.get('target') == 'clip1' and row.get('state') == 'running' for row in s.listing('job')))
        task = s.DATA / body['file']
        text = task.read_text(encoding='utf-8')
        self.assertIn(str((s.DATA / project['output']['file']).resolve()), text)
        self.assertIn('发布理解.json', text)
        self.assertIn('发布理解回传格式.md', text)
        self.assertIn(project['output']['sha256'], text)
        self.assertIn('不发布', text)
        self.assertIn('小红书', text)
        self.assertNotIn('install_optional', text)
        self.assertIn('Codex', text)
        copied = self.post('/projects/clip1/publish-task')
        self.assertEqual(copied.status_code, 200, copied.text)
        self.assertIn(str((s.DATA / project['output']['file']).resolve()), copied.json()['prompt'])
        self.assertIn('不是抖音或视频号扫码', copied.json()['prompt'])

    def test_either_gap_hands_off_without_transcribing(self):
        self.project('gap')

        def boom(*args, **kwargs):
            raise AssertionError('should not transcribe')

        with patch('semantic_delivery.whisper_available', return_value=False), patch('semantic_delivery.transcribe_offline', boom), patch('publish_understanding.desktop_cli_location', return_value=self.located), patch.dict(os.environ, {'WORKBENCH_MODEL': 'demo-writer', 'WORKBENCH_MODEL_BASE_URL': 'http://127.0.0.1:9'}):
            missing_asr = self.post('/projects/gap/prepare-delivery')
        self.assertEqual(missing_asr.status_code, 200, missing_asr.text)
        self.assertTrue(missing_asr.json()['handoff'])
        self.assertEqual(missing_asr.json()['reason'], 'asr')
        self.assertIn('没有离线听写', missing_asr.json()['message'])
        with patch('semantic_delivery.whisper_available', return_value=True), patch('semantic_delivery.transcribe_offline', boom), patch('publish_understanding.desktop_cli_location', return_value=self.located), patch.dict(os.environ, {'WORKBENCH_MODEL': '', 'WORKBENCH_MODEL_BASE_URL': ''}):
            missing_model = self.post('/projects/gap/prepare-delivery')
        self.assertTrue(missing_model.json()['handoff'])
        self.assertEqual(missing_model.json()['reason'], 'model')
        self.assertIn('自动写作还没接通', missing_model.json()['message'])
        self.assertFalse(any(row.get('target') == 'gap' and row.get('state') == 'running' for row in s.listing('job')))

    def test_whisper_present_still_prepares_locally(self):
        project = self.project('heard')
        sha = project['output']['sha256']
        speech = '先核对材料再对外说。'
        env = {'WORKBENCH_MODEL': 'demo-writer', 'WORKBENCH_MODEL_BASE_URL': 'http://127.0.0.1:9'}
        called = {}

        def fake_transcribe(core, row):
            called['transcribe'] = row['id']
            return speech, {'kind': 'offline_asr', 'video_sha256': sha, 'segments': [{'start': 0, 'end': 1, 'text': speech}], 'needs_review': True}

        def fake_model(task, data):
            called['model'] = data['transcript']
            return analysis()

        with patch.dict(os.environ, env), patch('semantic_delivery.whisper_available', return_value=True), patch('semantic_delivery.transcribe_offline', fake_transcribe), patch('semantic_delivery.call_model', fake_model):
            started = self.post('/projects/heard/prepare-delivery')
            self.assertEqual(started.status_code, 200, started.text)
            self.assertEqual(started.json().get('state'), 'running')
            self.assertNotIn('handoff', started.json())
            finished = self.wait_job(started.json()['id'])
        self.assertEqual(finished['state'], 'completed', finished.get('message'))
        self.assertEqual(called['transcribe'], 'heard')
        self.assertEqual(called['model'], speech)
        saved = s.get('project', 'heard')
        self.assertEqual(saved['publish_preparation']['understanding']['summary'], '这条只说了先核对材料')
        self.assertEqual(saved['publish_preparation']['transcript_source']['kind'], 'offline_asr')
        self.assertEqual(saved['platform_copy']['douyin']['title'], '先核对材料')
        self.assertEqual(saved['platform_copy']['douyin']['schedule'], '2026-12-01 10:00')
        self.assertIsNone(saved.get('publish_host_task'))
        self.assertFalse(s.listing('batch'))

    def test_existing_transcript_does_not_need_whisper(self):
        project = self.project('known')
        sha = project['output']['sha256']
        speech = '先核对材料再对外说。'
        project['publish_preparation'] = {'video_sha256': sha, 'transcript': speech, 'transcript_source': {'kind': 'existing_exact_video', 'video_sha256': sha}, 'cover_state': 'cleared'}
        s.put('project', project)
        env = {'WORKBENCH_MODEL': 'demo-writer', 'WORKBENCH_MODEL_BASE_URL': 'http://127.0.0.1:9'}

        def fake_model(task, data):
            self.assertEqual(data['transcript'], speech)
            return analysis()

        def boom(*args, **kwargs):
            raise AssertionError('should not transcribe')

        with patch.dict(os.environ, env), patch('semantic_delivery.whisper_available', return_value=False), patch('semantic_delivery.transcribe_offline', boom), patch('semantic_delivery.call_model', fake_model):
            started = self.post('/projects/known/prepare-delivery')
            self.assertEqual(started.json().get('state'), 'running', started.text)
            finished = self.wait_job(started.json()['id'])
        self.assertEqual(finished['state'], 'completed', finished.get('message'))
        saved = s.get('project', 'known')
        self.assertEqual(saved['publish_preparation']['transcript_source']['kind'], 'existing_exact_video')
        self.assertEqual(saved['platform_copy']['tencent']['title'], '先核对材料')

    def test_host_sync_round_trip_validates_and_keeps_covers(self):
        project = self.project('sync1')
        sha = project['output']['sha256']
        with patch('publish_understanding.desktop_cli_location', return_value=self.located), patch('semantic_delivery.whisper_available', return_value=False), patch.dict(os.environ, {'WORKBENCH_MODEL': '', 'WORKBENCH_MODEL_BASE_URL': ''}):
            opened = self.post('/projects/sync1/prepare-delivery')
        self.assertTrue(opened.json()['handoff'])
        folder = s.project_dir('sync1') / 'publication' / 'workbuddy-copy'
        (folder / '发布理解.json').write_text(json.dumps(host_body('sync1', sha), ensure_ascii=False), encoding='utf-8')
        synced = self.post('/projects/sync1/publish-understanding/sync')
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertTrue(synced.json()['synced'])
        self.assertIn('不会自动发布', synced.json()['message'])
        saved = s.get('project', 'sync1')
        self.assertEqual(saved['publish_preparation']['understanding']['summary'], '这条只说了先核对材料')
        self.assertEqual(saved['publish_preparation']['transcript'], '先核对材料再对外说。')
        self.assertEqual(saved['publish_preparation']['transcript_source']['kind'], 'host_understanding')
        self.assertEqual(saved['publish_preparation']['understanding']['generated_by'], 'Codex')
        self.assertEqual(saved['platform_copy']['douyin']['title'], '先核对材料')
        self.assertEqual(saved['platform_copy']['tencent']['short_title'], '先把材料核对完')
        self.assertEqual(saved['platform_copy']['douyin']['schedule'], '2026-12-01 10:00')
        self.assertEqual(saved['publish_preparation']['cover_state'], 'cleared')
        self.assertNotIn('xiaohongshu', saved['platform_copy'])
        self.assertIsNone(saved.get('publish_host_task'))
        self.assertFalse(s.listing('batch'))
        invented = dict(host_body('sync1', sha))
        invented['understanding'] = analysis('3天学会核对')
        (folder / '发布理解.json').write_text(json.dumps(invented, ensure_ascii=False), encoding='utf-8')
        rejected = self.post('/projects/sync1/publish-understanding/sync')
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn('数字', rejected.json()['detail'])
        self.assertEqual(s.get('project', 'sync1')['platform_copy']['douyin']['title'], '先核对材料')
        foreign = host_body('sync1', sha)
        foreign['understanding']['platform_copy']['xiaohongshu'] = {'title': '不该有', 'desc': '', 'tags': ''}
        (folder / '发布理解.json').write_text(json.dumps(foreign, ensure_ascii=False), encoding='utf-8')
        blocked = self.post('/projects/sync1/publish-understanding/sync')
        self.assertEqual(blocked.status_code, 400, blocked.text)
        self.assertIn('小红书', blocked.json()['detail'])
        self.assertNotIn('xiaohongshu', s.get('project', 'sync1')['platform_copy'])
        outside = Path(self.temp.name) / 'outside.json'
        outside.write_text(json.dumps(host_body('sync1', sha), ensure_ascii=False), encoding='utf-8')
        target = folder / '发布理解.json'
        target.unlink()
        target.symlink_to(outside)
        linked = self.post('/projects/sync1/publish-understanding/sync')
        self.assertEqual(linked.status_code, 400, linked.text)
        self.assertIn('没有读到', linked.json()['detail'])
        self.assertEqual(s.get('project', 'sync1')['platform_copy']['douyin']['title'], '先核对材料')

    def test_host_cannot_replace_an_exact_transcript_or_publish(self):
        project = self.project('locked')
        sha = project['output']['sha256']
        speech = '先核对材料再对外说。'
        project['publish_preparation'] = {'video_sha256': sha, 'transcript': speech, 'transcript_source': {'kind': 'offline_asr', 'video_sha256': sha}, 'cover_state': 'cleared'}
        s.put('project', project)
        folder = s.project_dir('locked') / 'publication' / 'workbuddy-copy'
        folder.mkdir(parents=True)
        mismatched = host_body('locked', sha, transcript='这是另一套完全不同的台词。')
        (folder / '发布理解.json').write_text(json.dumps(mismatched, ensure_ascii=False), encoding='utf-8')
        rejected = self.post('/projects/locked/publish-understanding/sync')
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn('另一套台词', rejected.json()['detail'])
        self.assertEqual(s.get('project', 'locked')['platform_copy']['douyin']['title'], '学员写的标题')
        forced = host_body('locked', sha, transcript=speech)
        forced['publish'] = True
        (folder / '发布理解.json').write_text(json.dumps(forced, ensure_ascii=False), encoding='utf-8')
        denied = self.post('/projects/locked/publish-understanding/sync')
        self.assertEqual(denied.status_code, 400, denied.text)
        self.assertIn('确认发布', denied.json()['detail'])
        self.assertFalse(s.listing('batch'))


if __name__ == '__main__':
    unittest.main()
