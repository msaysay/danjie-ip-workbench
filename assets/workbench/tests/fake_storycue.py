"""Local stand-in for StoryCue's trial handoff and setup APIs.

Implements danjie.storycue-handoff.v1 / storycue.interview-export.v1 and the
setup proxy described in the workbench contract. It stores keys only in this
process's .env.local. It is not the real StoryCue app.
"""
from __future__ import annotations

import json, os, re, threading
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FRAMEWORKS = ['观点破题', '四维信任', '方法直给', '痛点解答', '情绪共鸣', '人物故事', '现场探访', '决策问答']
_LEGACY_FRAMEWORK_IDS = {
    '北极星': '观点破题',
    '四喜': '四维信任',
    '抄近路': '方法直给',
    '消费心理': '痛点解答',
    '情绪': '情绪共鸣',
    '业务传记': '人物故事',
    '云参访': '现场探访',
    '业务硬控': '决策问答',
}
TOPIC_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$')


def canonical_framework(value):
    text = str(value or '').strip()
    if text in FRAMEWORKS:
        return text
    return _LEGACY_FRAMEWORK_IDS.get(text, '')
CREATED_AT = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$')
FIELDS = {'speechKey': 'DOUBAO_API_KEY', 'textKey': 'RELAY_LLM_API_KEY', 'llmBaseUrl': 'RELAY_LLM_BASE_URL', 'llmModel': 'RELAY_LLM_MODEL', 'jevKey': 'TYPESAFE_API_KEY'}


def _now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


class FakeStoryCue:
    def __init__(self, root: Path, auto_result: bool = False, port: int = 0):
        self.root = Path(root)
        self.data = self.root / '.storycue-data'
        self.handoffs = self.data / 'handoffs'
        self.data.mkdir(parents=True, exist_ok=True)
        self.handoffs.mkdir(parents=True, exist_ok=True)
        self.token = 'ab' * 32
        token_path = self.data / 'bridge-token'
        token_path.write_text(self.token, encoding='utf-8')
        os.chmod(token_path, 0o600)
        self.auto_result = auto_result
        self.last_inbound_framework = ''
        self._lock = threading.Lock()
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(('127.0.0.1', port), handler)
        self.port = self.httpd.server_address[1]
        self.origin = f'http://127.0.0.1:{self.port}'
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def env_path(self):
        return self.root / '.env.local'

    def read_env(self):
        path = self.env_path()
        if not path.is_file():
            return {}
        out = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line or '=' not in line:
                continue
            key, value = line.split('=', 1)
            out[key] = json.loads(value)
        return out

    def write_env(self, mapping):
        path = self.env_path()
        path.write_text(''.join(f'{k}={json.dumps(v, ensure_ascii=False)}\n' for k, v in mapping.items()), encoding='utf-8')
        os.chmod(path, 0o600)

    def _handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, fmt, *args):
                return

            def _json(self, status, payload):
                raw = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(raw)

            def _authorized(self):
                import hmac
                got = self.headers.get('X-StoryCue-Bridge-Token', '')
                return hmac.compare_digest(got, owner.token)

            def _read(self):
                length = int(self.headers.get('Content-Length', '0') or 0)
                if length > 2_000_000:
                    self._json(413, {'ok': False, 'message': '内容过长'})
                    return None
                raw = self.rfile.read(length) if length else b'{}'
                try:
                    data = json.loads(raw.decode())
                except Exception:
                    self._json(400, {'ok': False, 'message': '请提交 JSON'})
                    return None
                if not isinstance(data, dict):
                    self._json(400, {'ok': False, 'message': '请提交 JSON 对象'})
                    return None
                return data

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == '/trial':
                    self._trial_page(parse_qs(parsed.query).get('handoff', [''])[0])
                    return
                if not self._authorized():
                    self._json(403, {'ok': False, 'message': 'bridge token 无效'})
                    return
                if parsed.path == '/api/trial/setup':
                    self._json(200, owner.status())
                    return
                prefix = '/api/trial/handoff/'
                if parsed.path.startswith(prefix) and not parsed.path.endswith('/result'):
                    self._read_handoff(parsed.path[len(prefix):].strip('/'))
                    return
                if parsed.path.startswith(prefix) and parsed.path.endswith('/result'):
                    handoff_id = parsed.path[len(prefix):-len('/result')].strip('/')
                    self._read_result(handoff_id)
                    return
                self._json(404, {'ok': False, 'message': '没有这个接口'})

            def do_POST(self):
                if not self._authorized():
                    self._json(403, {'ok': False, 'message': 'bridge token 无效'})
                    return
                data = self._read()
                if data is None:
                    return
                if self.path == '/api/trial/setup':
                    self._save_setup(data)
                    return
                if self.path == '/api/trial/setup/test':
                    self._test(data)
                    return
                if self.path == '/api/trial/handoff':
                    self._handoff(data)
                    return
                prefix = '/api/trial/handoff/'
                if self.path.startswith(prefix) and self.path.endswith('/result'):
                    handoff_id = self.path[len(prefix):-len('/result')].strip('/')
                    self._write_result(handoff_id, data)
                    return
                self._json(404, {'ok': False, 'message': '没有这个接口'})

            def _save_setup(self, data):
                speech = str(data.get('speechKey') or '')
                if speech.startswith('echo-'):
                    self._json(400, {'error': '拒绝保存：' + speech})
                    return
                with owner._lock:
                    current = owner.read_env()
                    for field, env_name in FIELDS.items():
                        value = data.get(field)
                        if isinstance(value, str) and value:
                            current[env_name] = value
                    if 'enableJev' in data:
                        current['STORYCUE_JEV_ENABLED'] = '1' if data.get('enableJev') else '0'
                    owner.write_env(current)
                self._json(200, {'saved': True, 'restartVoice': True})

            def _test(self, data):
                target = data.get('target')
                env = owner.read_env()
                speech = env.get('DOUBAO_API_KEY', '')
                speech_help = '请到火山引擎控制台的「语音技术」创建 API Key，并为该 Key 开通大模型流式语音识别和语音合成。不要填写火山方舟的文本模型 Key，也不要只填 AppID + Access Token。语音控制台和方舟不是同一个 Key。'
                if target in ('doubao_tts', 'doubao_asr'):
                    if not speech:
                        self._json(200, {'ok': False, 'code': 'not_configured', 'message': '还没有豆包语音凭据。' + speech_help})
                        return
                    if speech.startswith('app-'):
                        self._json(200, {'ok': False, 'code': 'app_id_token_only', 'message': '当前只有 AppID 和 Access Token。大模型流式识别不接受这一对。请到语音技术控制台创建 API Key。'})
                        return
                    if 'ark-' in speech:
                        self._json(200, {'ok': False, 'code': 'ark_key_misused', 'message': '这个 Key 可以访问火山方舟，但豆包语音拒绝了它。语音识别和合成要用「语音技术」控制台的 API Key，不能把方舟文本模型 Key 填到豆包语音。'})
                        return
                    name = '语音合成' if target == 'doubao_tts' else '语音控制台 Key 正确，流式识别'
                    self._json(200, {'ok': True, 'code': 'ok', 'message': f'{name}已接通。'})
                    return
                if target == 'text_llm':
                    if not (env.get('RELAY_LLM_API_KEY') and env.get('RELAY_LLM_BASE_URL') and env.get('RELAY_LLM_MODEL')):
                        self._json(200, {'ok': False, 'code': 'not_configured', 'message': '即时追问还没配齐。请填写同一服务商的 HTTPS Base URL、API Key 和模型名。示例方舟地址是 https://ark.cn-beijing.volces.com/api/v3 。'})
                        return
                    self._json(200, {'ok': True, 'code': 'ok', 'message': '即时追问模型已接通。'})
                    return
                if target == 'jev':
                    if env.get('STORYCUE_JEV_ENABLED') != '1':
                        self._json(200, {'ok': True, 'code': 'disabled', 'message': 'Jev 未启用。这一步可以跳过，访谈会用停顿自动接话。'})
                        return
                    key = env.get('TYPESAFE_API_KEY', '')
                    if not key:
                        self._json(200, {'ok': False, 'code': 'not_configured', 'message': '已打开增强语义，但还没有 Jev Key。请填写 Key，或关闭该选项。'})
                        return
                    if '451' in key:
                        self._json(200, {'ok': False, 'code': 'region_unavailable', 'message': '当前地区无法使用 Jev（HTTP 451）。请关闭增强语义，访谈会改用自动停顿接话。'})
                        return
                    self._json(200, {'ok': True, 'code': 'ok', 'message': 'Jev 可用。'})
                    return
                if target == 'desktop':
                    path = owner.data / 'desktop-verification.json'
                    if not path.is_file():
                        self._json(200, {'ok': False, 'code': 'not_connected', 'message': '尚未连接 WorkBuddy 或 Codex。请在 StoryCue 项目目录运行 npm run desktop:connect -- --host workbuddy（Codex 用 --host codex），然后运行 npm run desktop:doctor。'})
                        return
                    try:
                        saved = json.loads(path.read_text(encoding='utf-8'))
                        checked = datetime.fromisoformat(saved.get('checkedAt'))
                        fresh = saved.get('verified') is True and datetime.now(timezone.utc) - checked.astimezone(timezone.utc) < timedelta(hours=24)
                    except Exception:
                        fresh = False
                    if fresh:
                        self._json(200, {'ok': True, 'code': 'verified', 'message': '本机桌面 AI 已通过最近 24 小时的检查。'})
                        return
                    self._json(200, {'ok': False, 'code': 'not_verified', 'message': '桌面 AI 尚未通过检查，或上次通过已超过 24 小时。请在项目目录运行 npm run desktop:doctor。若提示未登录，先运行 npm run desktop:login，再重新 doctor。'})
                    return
                self._json(400, {'ok': False, 'code': 'bad_target', 'message': 'target 必须是 doubao_tts、doubao_asr、text_llm、jev 或 desktop。'})

            def _handoff(self, data):
                raw_len = int(self.headers.get('Content-Length', '0') or 0)
                if raw_len > 600_000:
                    self._json(413, {'ok': False, 'error': '交接内容过长。请缩短脚本，或由工作台把背景压缩到 1200 字以内。'})
                    return
                if data.get('schema') != 'danjie.storycue-handoff.v1':
                    self._json(400, {'ok': False, 'error': 'schema 必须是 danjie.storycue-handoff.v1。'})
                    return
                topic_id = data.get('topicId')
                revision = data.get('revision')
                owner.last_inbound_framework = data.get('framework')
                framework = canonical_framework(data.get('framework'))
                script = data.get('script')
                background = data.get('background')
                if not isinstance(topic_id, str) or not TOPIC_ID.fullmatch(topic_id):
                    self._json(400, {'ok': False, 'error': 'topicId 只能包含字母、数字、下划线和连字符，最长 80，以便作为本机文件名。'})
                    return
                if not CREATED_AT.fullmatch(str(data.get('createdAt') or '')):
                    self._json(400, {'ok': False, 'error': '交接字段不符合 danjie.storycue-handoff.v1。请检查 topicId、revision、title、framework、background、script、scriptSha256、demo 和 createdAt。'})
                    return
                if not isinstance(revision, int) or framework not in FRAMEWORKS:
                    self._json(400, {'ok': False, 'error': '选题、版本或框架不对'})
                    return
                data = {**data, 'framework': framework}
                if isinstance(script, str) and len(script) > 100_000:
                    self._json(413, {'ok': False, 'error': 'script 超过 100000 字。请由工作台压缩进不超过 1200 字的 background，StoryCue 不保存超长脚本。'})
                    return
                if not isinstance(script, str) or not isinstance(background, str) or len(background) > 1200 or len(str(data.get('title') or '')) > 240:
                    self._json(400, {'ok': False, 'error': '标题、背景或脚本超出约定'})
                    return
                import hashlib
                digest = hashlib.sha256(script.encode()).hexdigest()
                if data.get('scriptSha256') != digest:
                    self._json(400, {'ok': False, 'message': 'scriptSha256 和脚本不一致'})
                    return
                handoff_id = f'{topic_id}-{revision}'
                with owner._lock:
                    for path in owner.handoffs.glob('*.json'):
                        if path.name.endswith('.result.json'):
                            continue
                        try:
                            old = json.loads(path.read_text(encoding='utf-8'))
                        except Exception:
                            continue
                        if old.get('topicId') == topic_id and old.get('handoffId') != handoff_id:
                            old['superseded'] = True
                            old['status'] = 'superseded'
                            path.write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
                    payload = {**data, 'handoffId': handoff_id, 'status': 'active', 'superseded': False}
                    (owner.handoffs / f'{handoff_id}.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
                    if owner.auto_result:
                        (owner.handoffs / f'{handoff_id}.result.json').write_text(json.dumps(sample_result(payload), ensure_ascii=False), encoding='utf-8')
                self._json(200, {'ok': True, 'handoffId': handoff_id, 'openUrl': f'{owner.origin}/trial?handoff={handoff_id}'})

            def _read_handoff(self, handoff_id):
                source = owner.handoffs / f'{handoff_id}.json'
                if not source.is_file():
                    self._json(404, {'ok': False, 'error': '找不到这次交接。'})
                    return
                saved = json.loads(source.read_text(encoding='utf-8'))
                self._json(200, {
                    'ok': True,
                    'handoffId': saved.get('handoffId'),
                    'topicId': saved.get('topicId'),
                    'revision': saved.get('revision'),
                    'title': saved.get('title'),
                    'framework': canonical_framework(saved.get('framework')),
                    'background': saved.get('background'),
                    'scriptSha256': saved.get('scriptSha256'),
                    'demo': saved.get('demo'),
                    'createdAt': saved.get('createdAt'),
                    'status': saved.get('status') or ('superseded' if saved.get('superseded') else 'active'),
                })

            def _read_result(self, handoff_id):
                source = owner.handoffs / f'{handoff_id}.json'
                result = owner.handoffs / f'{handoff_id}.result.json'
                if not source.is_file():
                    self._json(404, {'ok': False, 'message': '没有这次交接'})
                    return
                saved = json.loads(source.read_text(encoding='utf-8'))
                if saved.get('superseded'):
                    self._json(409, {'ok': False, 'message': '这次交接已被新版本取代，请重新访谈。'})
                    return
                if not result.is_file():
                    self._json(404, {'ok': False, 'message': '还没有回传结果'})
                    return
                self._json(200, json.loads(result.read_text(encoding='utf-8')))

            def _write_result(self, handoff_id, data):
                source = owner.handoffs / f'{handoff_id}.json'
                if not source.is_file():
                    self._json(404, {'ok': False, 'message': '没有这次交接'})
                    return
                (owner.handoffs / f'{handoff_id}.result.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                self._json(200, {'ok': True})

            def _trial_page(self, handoff_id):
                path = owner.handoffs / f'{handoff_id}.json'
                if not path.is_file():
                    body = '<p>没有找到这次交接。</p>'
                else:
                    saved = json.loads(path.read_text(encoding='utf-8'))
                    demo = '课堂演练，待本人核对。' if saved.get('demo') else '沿用已确认脚本。'
                    body = f'<p>{_esc(demo)}</p><h1>{_esc(saved.get("title") or "")}</h1><p>框架：{_esc(canonical_framework(saved.get("framework")))}</p><p>交接编号：{_esc(handoff_id)}</p>'
                page = f'<!doctype html><meta charset="utf-8"><title>StoryCue 访谈</title><main><p>StoryCue 已接到这次交接。这一页是本机约定检查用的替身，用来确认工作台打开了返回的地址。</p>{body}</main>'
                raw = page.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return Handler

    def status(self):
        env = self.read_env()
        verified = False
        host = None
        try:
            saved = json.loads((self.data / 'desktop-verification.json').read_text(encoding='utf-8'))
            checked = datetime.fromisoformat(saved.get('checkedAt'))
            verified = saved.get('verified') is True and datetime.now(timezone.utc) - checked.astimezone(timezone.utc) < timedelta(hours=24)
            host = saved.get('host')
        except Exception:
            verified = False
        return {
            'speechConfigured': bool(env.get('DOUBAO_API_KEY')),
            'textConfigured': bool(env.get('RELAY_LLM_API_KEY')),
            'jevEnabled': env.get('STORYCUE_JEV_ENABLED') == '1',
            'llmBaseUrl': env.get('RELAY_LLM_BASE_URL') or 'https://ark.cn-beijing.volces.com/api/v3',
            'llmModel': env.get('RELAY_LLM_MODEL') or 'doubao-seed-2-0-lite-260428',
            'desktopBridge': {'configured': verified, 'host': host, 'model': 'fake-model' if verified else None, 'verified': verified, 'entry': 'official-cli' if verified else ''},
        }


def sample_result(handoff):
    guest = '先核对选题原句还在不在，缺的材料继续留空。这是课堂演练，不是已经发生的采访。'
    return {
        'schema': 'storycue.interview-export.v1',
        'handoffId': handoff['handoffId'],
        'topicId': handoff['topicId'],
        'scriptSha256': handoff['scriptSha256'],
        'framework': handoff['framework'],
        'plan': {
            'focus': '课堂演练：只核对这一版虚构脚本里已经写明的材料。',
            'questions': [
                {'label': '观点入口', 'question': '这次虚构任务里，你最想先核对的判断是什么？', 'notes': '只沿稿里已有的句子追问。'},
                {'label': '支撑经历', 'question': '哪一句是稿里已经写上的依据，哪一句还是空的？', 'notes': '没有材料就保持缺口。'},
                {'label': '金句提炼', 'question': '如果只留一句核对提醒，你会怎么说？', 'notes': '不另写口号。'},
                {'label': '转化承接', 'question': '看完的人下一步只做哪一件核对？', 'notes': '不写报名或联系方式。'},
            ],
        },
        'entries': [
            {'id': 'q1', 'role': 'AI', 'text': '这次虚构任务里，你最想先核对的判断是什么？', 'at': _now()},
            {'id': 'a1', 'role': '嘉宾', 'text': guest, 'at': _now()},
        ],
        'editingAdvice': {
            'mainline': '课堂演练只保留“先核对、缺的留空”这一条主线。',
            'clips': [{
                'title': '先核对再开口',
                'rationale': '嘉宾原话已经把演练边界说清。',
                'readiness': '可整理',
                'segments': [{'purpose': '开场观点', 'entryIds': ['a1'], 'note': '保留“课堂演练”这几个字。'}],
                'keyPhrases': [{'entryId': 'a1', 'phrase': '缺的材料继续留空'}],
                'missing': ['没有真实客户原话'],
                'followUps': ['还有哪一项材料这次故意没写？'],
            }],
            'cautions': ['虚构演练，不能当成真实访谈或已拍摄。'],
        },
        'exportedAt': _now(),
        'demo': bool(handoff.get('demo')),
    }


def _esc(value):
    return (str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--port', type=int, default=3066)
    parser.add_argument('--auto-result', action='store_true')
    parser.add_argument('--verified', action='store_true')
    args = parser.parse_args()
    service = FakeStoryCue(Path(args.root), auto_result=args.auto_result, port=args.port)
    if args.verified:
        (service.data / 'desktop-verification.json').write_text(json.dumps({'verified': True, 'checkedAt': datetime.now(timezone.utc).isoformat(), 'host': 'codex'}), encoding='utf-8')
    print(json.dumps({'origin': service.origin, 'directory': str(service.root), 'tokenReady': True}), flush=True)
    try:
        service.thread.join()
    except KeyboardInterrupt:
        service.stop()
