"""Workbench side of the StoryCue interview handoff.

Keys are forwarded to StoryCue's own setup API and are never written to the
workbench database, logs, responses, or the repository. sayFrame editing is
not called; assemble_sayframe_handoff only reserves the next payload.
"""
from __future__ import annotations

import contextvars, hashlib, json, logging, os, re, shutil, subprocess
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import requests
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from desktop_cli import desktop_cli_location

log = logging.getLogger('danjie.storycue')
SECRETS = contextvars.ContextVar('storycue_secrets', default=frozenset())
MIGRATION = '001_storycue_interview'
MIGRATION_FILE = Path(__file__).resolve().parent / 'migrations' / f'{MIGRATION}.sql'
FRAMEWORKS = (
    ('北极星', '观点破题', '用不同判断开场，以原话和证据讲清道理'),
    ('四喜', '四维信任', '兼顾破圈、人设、专业与转化'),
    ('抄近路', '方法直给', '讲清方法步骤，用具体例子帮助理解'),
    ('消费心理', '痛点解答', '从客户问题讲到答案、依据与下一步'),
    ('情绪', '情绪共鸣', '从一个真实瞬间和感受切入'),
    ('业务传记', '人物故事', '用与业务有关的经历、选择和转折建立信任'),
    ('云参访', '现场探访', '按客户关心的顺序串起可拍的现场'),
    ('业务硬控', '决策问答', '围绕选择前的疑虑做一问一答'),
)
FRAMEWORK_IDS = {row[0] for row in FRAMEWORKS}
TEST_TARGETS = {'doubao_tts', 'doubao_asr', 'text_llm', 'jev', 'desktop'}
TOPIC_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$')
MAX_SCRIPT_CHARS = 100_000
MAX_HANDOFF_BYTES = 600_000
MAX_REVISION = 1_000_000
SETUP_FIELDS = {'speechKey', 'textKey', 'llmBaseUrl', 'llmModel', 'enableJev', 'jevKey'}
DESKTOP_COMMANDS = {
    'connectWorkbuddy': 'npm run desktop:connect -- --host workbuddy',
    'connectCodex': 'npm run desktop:connect -- --host codex',
    'login': 'npm run desktop:login',
    'doctor': 'npm run desktop:doctor',
}
POPEN = subprocess.Popen
MISMATCH = '脚本已改过，请重新访谈或确认沿用。'


class SecretRedactFilter(logging.Filter):
    def filter(self, record):
        secrets = [s for s in SECRETS.get() if isinstance(s, str) and len(s) >= 8]
        if not secrets:
            return True
        record.msg = redact(record.getMessage(), secrets)
        record.args = ()
        return True


def install_redaction():
    redact_filter = SecretRedactFilter()
    root = logging.getLogger()
    if not any(isinstance(item, SecretRedactFilter) for item in root.filters):
        root.addFilter(redact_filter)
    if not any(isinstance(item, SecretRedactFilter) for item in log.filters):
        log.addFilter(redact_filter)


install_redaction()


def redact(text, secrets):
    out = str(text)
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 8 and secret in out:
            out = out.replace(secret, '[redacted]')
    return out


def scrub(value, secrets):
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, list):
        return [scrub(item, secrets) for item in value]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if re.search(r'(api[_-]?key|token|secret|password|authorization)', str(key), re.I):
                continue
            cleaned[key] = scrub(item, secrets)
        return cleaned
    return value


def secret_values(data):
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and re.search(r'key|token|secret|password', str(key), re.I):
                found.append(value)
            else:
                found.extend(secret_values(value))
    elif isinstance(data, list):
        for value in data:
            found.extend(secret_values(value))
    return found


@contextmanager
def secret_scope(values):
    previous = SECRETS.get()
    extra = {value for value in values if isinstance(value, str) and len(value) >= 8}
    SECRETS.set(frozenset(set(previous) | extra))
    try:
        yield
    finally:
        SECRETS.set(previous)


def origin():
    return os.environ.get('STORYCUE_ORIGIN', 'http://127.0.0.1:3066').rstrip('/')


def script_sha256(script):
    return hashlib.sha256(str(script).encode()).hexdigest()


def storycue_timestamp():
    # StoryCue validates createdAt with Zod datetime, which accepts a UTC Zulu stamp.
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def topic_id_ok(value):
    return isinstance(value, str) and bool(TOPIC_ID.fullmatch(value))


def startup_commands(directory):
    folder = str(directory or 'StoryCue所在目录').replace('"', '')
    windows = folder.replace('/', '\\')
    return {
        'windows': f'cd /d "{windows}" && set VOICE_RELAY_PORT=8866&& npm run dev',
        'mac': f'cd "{folder}" && VOICE_RELAY_PORT=8866 npm run dev',
        'voiceRelayPort': '8866',
    }


def offline_message(directory):
    lines = startup_commands(directory)
    return 'StoryCue 没有在本机响应。请先在它的目录启动；语音中继必须是 8866，避免和工作台 8766 冲突。Windows：' + lines['windows'] + ' Mac：' + lines['mac']


def child_env(base):
    env = {key: value for key, value in base.items() if not re.search(r'KEY|TOKEN|SECRET|PASSWORD|COOKIE', key, re.I)}
    env['VOICE_RELAY_PORT'] = '8866'
    return env


def dev_command(npm, os_name):
    if os_name == 'nt':
        return ['cmd', '/c', 'npm', 'run', 'dev']
    return [npm, 'run', 'dev']


SECTION_LABELS = {'opening': '开头', 'reason': '支撑', 'identity': '身份', 'ending': '收尾'}


def section_label(part):
    key = str(part.get('key') or '')
    label = str(part.get('label') or '').strip()
    if not label or label == key:
        return SECTION_LABELS.get(key, label or key or '段落')
    return label


def section_texts(topic):
    parts = [part for part in topic.get('framework') or [] if str(part.get('text') or '').strip()]
    script = str(topic.get('script') or '').strip()
    if parts and all(str(part.get('text') or '').strip()[:40] in script for part in parts):
        return [(section_label(part), str(part.get('text') or '').strip()) for part in parts]
    paragraphs = [part.strip() for part in re.split(r'\n\s*\n', script) if part.strip()]
    labels = ['开头', '支撑', '身份', '收尾']
    if not paragraphs:
        return [('脚本', script)]
    if len(paragraphs) >= 4:
        paragraphs = paragraphs[:3] + ['\n\n'.join(paragraphs[3:])]
        return list(zip(labels, paragraphs))
    return [(labels[index], text) for index, text in enumerate(paragraphs)]


def compress_background(topic, limit=1200):
    sections = section_texts(topic)
    def render(budgets):
        chunks = []
        for (label, text), budget in zip(sections, budgets):
            body = text if len(text) <= budget else (text[:max(0, budget - 1)].rstrip() + '…')
            chunks.append(f'{label}：{body}')
        return '\n'.join(chunks)
    full = render([10**9] * len(sections))
    if len(full) <= limit:
        return full
    overhead = sum(len(label) + 1 for label, _ in sections) + max(0, len(sections) - 1)
    usable = limit - overhead
    if usable < len(sections):
        return full[:limit - 1].rstrip() + '…'
    total = max(1, sum(len(text) for _, text in sections))
    budgets = [max(1, int(usable * len(text) / total)) for _, text in sections]
    while sum(budgets) > usable:
        budgets[budgets.index(max(budgets))] -= 1
    text = render(budgets)
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + '…'
    return text


def suggest_framework(topic):
    parts = {str(part.get('key') or ''): part for part in topic.get('framework') or []}
    opening = parts.get('opening') or {}
    skill = str(opening.get('skill') or '')
    opening_text = str(opening.get('text') or '')
    reason = str((parts.get('reason') or {}).get('text') or '')
    identity = str((parts.get('identity') or {}).get('text') or '')
    ending = str((parts.get('ending') or {}).get('text') or '')
    blob = '\n'.join([opening_text, reason, identity, ending])
    scores = {item[0]: 0 for item in FRAMEWORKS}
    why = {item[0]: [] for item in FRAMEWORKS}
    scores['北极星'] += 1
    why['北极星'].append('脚本按开头、支撑、身份、收尾四段写成，默认先按观点破题采访')
    if '03' in skill or '当头' in skill or '当头' in opening_text[:24]:
        scores['北极星'] += 3
        why['北极星'].append('开头是当头一棒这一类判断')
    if '07' in skill or '开场八式' in skill:
        scores['四喜'] += 3
        why['四喜'].append('开头用了开场八式，适合先把信任讲圆')
    if re.search(r'步骤|第一步|怎么做|具体做法', reason):
        scores['抄近路'] += 5
        why['抄近路'].append('支撑段在讲步骤和方法')
    if re.search(r'痛点|卡住|困难|顾虑', blob):
        scores['消费心理'] += 3
        why['消费心理'].append('四段里有客户卡住或顾虑')
    if re.search(r'感受|委屈|难过|那一刻|情绪', blob):
        scores['情绪'] += 4
        why['情绪'].append('四段里有具体感受')
    if re.search(r'那年|一开始|转折|我曾经|经历', opening_text + '\n' + identity):
        scores['业务传记'] += 3
        why['业务传记'].append('开头或身份段在讲本人经历')
    if re.search(r'现场|到店|镜头|参观|带你看', blob):
        scores['云参访'] += 5
        why['云参访'].append('稿里在讲可以拍的现场')
    if re.search(r'为什么找|怎么选|选择前|对比', opening_text + '\n' + ending):
        scores['业务硬控'] += 3
        why['业务硬控'].append('开头或收尾在处理选择前的比较')
    best = max(FRAMEWORKS, key=lambda item: scores[item[0]])[0]
    names = {item[0]: item[1] for item in FRAMEWORKS}
    return {'id': best, 'name': names[best], 'reason': '；'.join(why[best])}


def assemble_sayframe_handoff(topic, interview=None, *, framework='', media_path='', media_sha256=''):
    """Reserve danjie.sayframe-handoff.v1. Does not call sayFrame or read media."""
    script = str(topic.get('script') or '')
    chosen = ''
    if isinstance(interview, dict):
        chosen = str(interview.get('framework') or framework or '')
    else:
        interview = None
        chosen = str(framework or '')
    if chosen not in FRAMEWORK_IDS:
        chosen = ''
    return {
        'schema': 'danjie.sayframe-handoff.v1',
        'topicId': topic.get('id'),
        'scriptSha256': script_sha256(script),
        'mediaPath': str(media_path or ''),
        'mediaSha256': str(media_sha256 or ''),
        'framework': chosen,
        'interview': interview,
        'script': script,
    }


def ensure_schema(core):
    with core.LOCK, core.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        applied = {row[0] for row in db.execute('SELECT version FROM schema_migrations')}
        if MIGRATION in applied:
            return
        sql = '\n'.join(line for line in MIGRATION_FILE.read_text(encoding='utf-8').splitlines() if not line.strip().startswith('--'))
        for statement in [part.strip() for part in sql.split(';') if part.strip()]:
            db.execute(statement)
        db.execute('INSERT INTO schema_migrations VALUES (?,?)', (MIGRATION, core.now()))


def load_settings(core):
    rows = [row for row in core.listing('storycue_settings') if row.get('id') == 'main']
    return rows[0] if rows else {'id': 'main', 'directory': ''}


def storycue_directory(core):
    raw = str(load_settings(core).get('directory') or '').strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None
    return path.resolve()


def validate_directory(raw):
    text = str(raw or '').strip()
    if not text or len(text) > 500:
        raise HTTPException(400, '请填写 StoryCue 所在目录的完整路径。')
    if re.search(r'["\'`$&|;<>\n]', text):
        raise HTTPException(400, '目录路径里有不能放进启动命令的符号。请换一个不含引号、& 或竖线的路径。')
    path = Path(text).expanduser()
    if not path.is_dir():
        raise HTTPException(400, '这个目录不存在。请填写本机 StoryCue 项目文件夹的完整路径。')
    return path.resolve()


def token_path(directory: Path):
    for candidate in (directory / '.storycue-data' / 'bridge-token', directory / 'bridge-token'):
        if candidate.is_file():
            return candidate
    return None


def read_token(directory: Path):
    path = token_path(directory)
    if not path:
        raise HTTPException(400, '这个目录里没有 bridge-token。请先启动一次 StoryCue。令牌在 <项目>/.storycue-data/bridge-token（也就是 STORYCUE_DATA_DIR/bridge-token）。' + offline_message(directory))
    try:
        token = path.read_text(encoding='utf-8').strip()
    except OSError:
        raise HTTPException(400, 'bridge-token 读不了。请确认 StoryCue 目录权限，并重新启动一次。')
    if not re.fullmatch(r'[0-9a-f]{64}', token):
        raise HTTPException(400, 'bridge-token 格式不对。StoryCue 写入的是 64 位小写十六进制，请重新启动 StoryCue 生成该文件。')
    return token


def respond(payload, status=200):
    return JSONResponse(payload, status_code=status, headers={'Cache-Control': 'no-store'})


def public_setup(payload):
    if not isinstance(payload, dict):
        return None
    bridge = payload.get('desktopBridge') if isinstance(payload.get('desktopBridge'), dict) else {}
    return {
        'speechConfigured': bool(payload.get('speechConfigured')),
        'textConfigured': bool(payload.get('textConfigured')),
        'jevEnabled': bool(payload.get('jevEnabled')),
        'llmBaseUrl': payload.get('llmBaseUrl') if isinstance(payload.get('llmBaseUrl'), str) else '',
        'llmModel': payload.get('llmModel') if isinstance(payload.get('llmModel'), str) else '',
        'desktopBridge': {
            'configured': bool(bridge.get('configured')),
            'host': bridge.get('host') if isinstance(bridge.get('host'), str) else None,
            'model': bridge.get('model') if isinstance(bridge.get('model'), str) else None,
            'verified': bool(bridge.get('verified')),
            'entry': bridge.get('entry') if isinstance(bridge.get('entry'), str) else '',
        },
    }


def storycue_request(method, path, token, directory, body=None, timeout=20):
    try:
        response = requests.request(method, origin() + path, headers={'X-StoryCue-Bridge-Token': token, 'Accept': 'application/json'}, json=body, timeout=timeout)
    except requests.RequestException:
        log.info('storycue unreachable %s %s', method, path)
        raise HTTPException(503, offline_message(directory)) from None
    return response


def upstream_json(response, secrets):
    try:
        data = response.json()
    except Exception:
        data = {'message': 'StoryCue 没有返回可识别的结果。'}
    if not isinstance(data, dict):
        data = {'message': 'StoryCue 没有返回可识别的结果。'}
    return scrub(data, secrets)


def upstream_message(data, fallback):
    for key in ('message', 'error', 'detail'):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def require_topic(core, ident):
    topic = core.get('writing_topic', ident)
    if topic.get('stage') != 'ready' or not str(topic.get('script') or '').strip():
        raise HTTPException(409, '先确认这一版脚本，再交给 StoryCue。')
    return topic


def handoff_body(core, topic, framework):
    if framework not in FRAMEWORK_IDS:
        raise HTTPException(400, '请从 8 个访谈框架里选一个。')
    title = str(topic.get('title') or '').strip()
    if not title:
        raise HTTPException(400, '这条选题没有标题。')
    if not topic_id_ok(topic.get('id')):
        raise HTTPException(400, '这条选题的编号不能交给 StoryCue。编号只能是字母、数字、下划线和连字符，并以字母或数字开头，最长 80，这样才能作为本机文件名。')
    script = str(topic.get('script') or '')
    if len(script) > MAX_SCRIPT_CHARS:
        raise HTTPException(413, f'脚本超过 {MAX_SCRIPT_CHARS} 字。请先缩短确认稿再交给 StoryCue。背景会压到 1200 字，但整篇脚本本身也不能超过这个上限。')
    background = compress_background(topic).strip()
    if len(background) > 1200:
        raise HTTPException(413, 'background 不能超过 1200 字。请由工作台把过长脚本压缩进 background 后再交接。')
    revision = int(topic.get('revision') or 0)
    if revision < 0 or revision > MAX_REVISION:
        raise HTTPException(400, 'revision 必须是不超过 1000000 的非负整数。')
    body = {
        'schema': 'danjie.storycue-handoff.v1',
        'topicId': topic['id'],
        'revision': revision,
        'title': title[:240],
        'framework': framework,
        'background': background,
        'script': script,
        'scriptSha256': script_sha256(script),
        'demo': bool(topic.get('demo')),
        'createdAt': storycue_timestamp(),
    }
    if len(json.dumps(body, ensure_ascii=False).encode()) > MAX_HANDOFF_BYTES:
        raise HTTPException(413, '交接内容过长。请缩短脚本，或由工作台把背景压缩到 1200 字以内。')
    return body


def accepted_open_url(url, handoff_id):
    parsed = urlparse(str(url or ''))
    expected = urlparse(origin())
    if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise HTTPException(502, 'StoryCue 返回的地址不是本机，已拒绝打开。')
    if parsed.port != (expected.port or 3066):
        raise HTTPException(502, 'StoryCue 返回的端口和当前访谈服务不一致，已拒绝打开。')
    if parse_qs(parsed.query).get('handoff', [None])[0] != handoff_id:
        raise HTTPException(502, 'StoryCue 返回的交接编号和这次选题不一致，已拒绝打开。')
    return str(url)


def save_link(core, topic_id, body, open_url):
    ensure_schema(core)
    with core.LOCK, core.connect() as db:
        db.execute(
            '''INSERT INTO storycue_link (topic_id,handoff_id,revision,framework,script_sha256,background,open_url,demo,created_at,result_json,imported_at)
               VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL)
               ON CONFLICT(topic_id) DO UPDATE SET
                 handoff_id=excluded.handoff_id, revision=excluded.revision, framework=excluded.framework,
                 script_sha256=excluded.script_sha256, background=excluded.background, open_url=excluded.open_url,
                 demo=excluded.demo, created_at=excluded.created_at, result_json=NULL, imported_at=NULL''',
            (topic_id, f"{body['topicId']}-{body['revision']}", body['revision'], body['framework'], body['scriptSha256'], body['background'], open_url, 1 if body['demo'] else 0, body['createdAt']),
        )


def read_link(core, topic_id):
    ensure_schema(core)
    with core.connect() as db:
        row = db.execute('SELECT handoff_id,revision,framework,script_sha256,background,open_url,demo,created_at,result_json,imported_at FROM storycue_link WHERE topic_id=?', (topic_id,)).fetchone()
    if not row:
        return None
    keys = ['handoff_id', 'revision', 'framework', 'script_sha256', 'background', 'open_url', 'demo', 'created_at', 'result_json', 'imported_at']
    data = dict(zip(keys, row))
    data['demo'] = bool(data['demo'])
    data['result'] = json.loads(data['result_json']) if data['result_json'] else None
    return data


def validate_export(topic, payload):
    if not isinstance(payload, dict) or payload.get('schema') != 'storycue.interview-export.v1':
        raise HTTPException(400, '这不是 StoryCue 的访谈回传文件。')
    if payload.get('topicId') != topic['id']:
        raise HTTPException(409, '这份访谈结果不属于当前选题，已拒绝。')
    digest = script_sha256(str(topic.get('script') or ''))
    if payload.get('scriptSha256') != digest:
        raise HTTPException(409, MISMATCH)
    if payload.get('framework') not in FRAMEWORK_IDS:
        raise HTTPException(400, '回传里的框架不在 8 个访谈框架中。')
    if not isinstance(payload.get('demo'), bool):
        raise HTTPException(400, '回传缺少 demo 标记，已拒绝。')
    if topic.get('demo') and payload.get('demo') is not True:
        raise HTTPException(400, '这是课堂演练选题，回传结果必须标明 demo，不能当成真实访谈。')
    plan = payload.get('plan')
    questions = plan.get('questions') if isinstance(plan, dict) else None
    entries = payload.get('entries')
    if not isinstance(questions, list) or not questions or not isinstance(entries, list):
        raise HTTPException(400, '回传里没有访谈问题或回答。')
    for item in questions:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item.get(key).strip() for key in ('label', 'question')) or not isinstance(item.get('notes', ''), str):
            raise HTTPException(400, '访谈问题格式不完整。')
    for item in entries:
        if not isinstance(item, dict) or item.get('role') not in ('嘉宾', 'AI') or not isinstance(item.get('text'), str):
            raise HTTPException(400, '访谈回答格式不完整。')
        if item.get('provisional') is True:
            raise HTTPException(400, '结果里还有未确认的转写，请在 StoryCue 确认后再回传。')
    advice = payload.get('editingAdvice')
    if advice is not None and not isinstance(advice, dict):
        raise HTTPException(400, '剪辑建议格式不对。')
    if not isinstance(payload.get('exportedAt'), str) or not payload.get('handoffId'):
        raise HTTPException(400, '回传缺少交接编号或导出时间。')
    return payload


def store_result(core, topic, payload):
    checked = validate_export(topic, payload)
    stored = scrub(checked, secret_values(checked))
    link = read_link(core, topic['id'])
    ensure_schema(core)
    with core.LOCK, core.connect() as db:
        if link:
            db.execute('UPDATE storycue_link SET result_json=?, imported_at=?, framework=?, script_sha256=? WHERE topic_id=?', (json.dumps(stored, ensure_ascii=False), core.now(), stored['framework'], stored['scriptSha256'], topic['id']))
        else:
            db.execute(
                'INSERT INTO storycue_link (topic_id,handoff_id,revision,framework,script_sha256,background,open_url,demo,created_at,result_json,imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (topic['id'], str(stored.get('handoffId'))[:80], int(topic.get('revision') or 0), stored['framework'], stored['scriptSha256'], '', '', 1 if stored.get('demo') else 0, core.now(), json.dumps(stored, ensure_ascii=False), core.now()),
            )
    return stored


def panel_for(core, topic):
    link = read_link(core, topic['id'])
    suggestion = suggest_framework(topic)
    background = compress_background(topic) if str(topic.get('script') or '').strip() else ''
    interview = link.get('result') if link else None
    handoff = None
    if link and link.get('handoff_id'):
        handoff = {'handoffId': link['handoff_id'], 'revision': link['revision'], 'framework': link['framework'], 'scriptSha256': link['script_sha256'], 'openUrl': link['open_url'], 'demo': link['demo'], 'createdAt': link['created_at']}
    return {
        'ready': topic.get('stage') == 'ready' and bool(str(topic.get('script') or '').strip()),
        'demo': bool(topic.get('demo')),
        'frameworks': [{'id': item[0], 'name': item[1], 'summary': item[2]} for item in FRAMEWORKS],
        'suggested': suggestion,
        'background': background,
        'backgroundChars': len(background),
        'scriptSha256': script_sha256(str(topic.get('script') or '')) if topic.get('script') else '',
        'handoff': handoff,
        'interview': interview,
    }


def launch(directory, *, popen=None, os_name=None, env=None):
    os_name = os_name or os.name
    npm = shutil.which('npm')
    if not npm:
        raise HTTPException(400, '这台电脑没有找到 npm。请先安装 Node.js 20.9 或更新版本，再使用下面的启动命令。')
    command = dev_command(npm, os_name)
    runner = popen or POPEN
    process = runner(command, cwd=str(directory), env=child_env(env or os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
    log.info('storycue launch requested pid=%s', getattr(process, 'pid', 0))
    return getattr(process, 'pid', 0)


async def read_body(request: Request, limit=20000):
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(413, '内容过长。')
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode())
    except Exception:
        raise HTTPException(400, '请提交 JSON。')
    if not isinstance(data, dict):
        raise HTTPException(400, '请提交 JSON 对象。')
    return data


def setup_payload(data):
    payload = {}
    for key in SETUP_FIELDS:
        if key not in data:
            continue
        value = data[key]
        if key == 'enableJev':
            if not isinstance(value, bool):
                raise HTTPException(400, 'Jev 开关需要是开或关。')
            payload[key] = value
            continue
        if not isinstance(value, str) or len(value) > 500 or re.search(r'[\r\n\0]', value):
            raise HTTPException(400, '配置项不能换行，也不能超过 500 字。')
        payload[key] = value
    return payload


def call_setup_test(token, target, secrets, directory):
    response = None
    try:
        response = requests.post(origin() + '/api/trial/setup/test', headers={'X-StoryCue-Bridge-Token': token, 'Accept': 'application/json', 'Content-Type': 'application/json'}, json={'target': target}, timeout=25)
    except requests.RequestException:
        log.info('storycue test unreachable target=%s', target)
        raise HTTPException(503, offline_message(directory)) from None
    data = upstream_json(response, secrets)
    if response.status_code == 403:
        raise HTTPException(403, 'StoryCue 拒绝了本机 bridge-token。请确认选的是当前这次 StoryCue 的目录，重新启动后再读取令牌。')
    message = upstream_message(data, 'StoryCue 没有完成这项测试。')
    log.info('storycue test target=%s status=%s', target, response.status_code)
    ok = bool(data.get('ok')) and response.status_code < 400
    return {'ok': ok, 'code': data.get('code') if isinstance(data.get('code'), str) else '', 'message': message}


def attach(app, core):
    def directory_or_error():
        ensure_schema(core)
        directory = storycue_directory(core)
        if not directory:
            raise HTTPException(400, '请先填写并读取 StoryCue 所在目录。')
        return directory

    def token_for(directory):
        return read_token(directory)

    @app.get('/api/storycue/status')
    def status():
        ensure_schema(core)
        directory = storycue_directory(core)
        commands = startup_commands(directory or '')
        try:
            desktop_cli = desktop_cli_location()
        except Exception:
            log.info('desktop cli location unavailable')
            desktop_cli = {'hosts': [], 'npmRoot': '', 'npmError': '这次没能检查本机命令'}
        payload = {'directory': str(directory or ''), 'tokenReady': False, 'reachable': False, 'setup': None, 'start': commands, 'commands': DESKTOP_COMMANDS, 'desktopCli': desktop_cli, 'message': ''}
        if not directory:
            payload['message'] = '先填写 StoryCue 项目所在目录。工作台只记住这个路径，并在每次请求时读取 bridge-token。'
            return respond(payload)
        if not token_path(directory):
            payload['message'] = '还没有读到 bridge-token。' + offline_message(directory)
            return respond(payload)
        payload['tokenReady'] = True
        try:
            token = read_token(directory)
        except HTTPException as exc:
            payload['message'] = exc.detail
            return respond(payload)
        try:
            with secret_scope([token]):
                response = storycue_request('GET', '/api/trial/setup', token, directory, timeout=5)
        except HTTPException as exc:
            payload['message'] = exc.detail
            return respond(payload)
        if response.status_code == 403:
            payload['message'] = 'StoryCue 拒绝了本机 bridge-token。请确认目录对应当前启动的 StoryCue，然后重新读取。'
            return respond(payload)
        if response.status_code >= 400:
            payload['message'] = 'StoryCue 已在运行，但设置接口没有返回。请看 StoryCue 窗口里的报错。'
            return respond(payload)
        payload['reachable'] = True
        payload['setup'] = public_setup(upstream_json(response, [token]))
        payload['message'] = '已连上本机 StoryCue。Key 不会回显，也不会写入工作台。'
        return respond(payload)

    @app.post('/api/storycue/directory')
    async def save_directory(request: Request):
        data = await read_body(request)
        with secret_scope(secret_values(data)):
            directory = validate_directory(data.get('directory'))
            core.put('storycue_settings', {'id': 'main', 'directory': str(directory)})
            log.info('storycue directory saved')
        return await core_status()

    async def core_status():
        return status()

    @app.post('/api/storycue/setup')
    async def save_setup(request: Request):
        data = await read_body(request)
        secrets = secret_values(data)
        payload = setup_payload(data)
        directory = directory_or_error()
        token = token_for(directory)
        with secret_scope([*secrets, token]):
            try:
                response = requests.post(origin() + '/api/trial/setup', headers={'X-StoryCue-Bridge-Token': token, 'Accept': 'application/json', 'Content-Type': 'application/json'}, json=payload, timeout=20)
            except requests.RequestException:
                log.info('storycue setup unreachable')
                raise HTTPException(503, offline_message(directory)) from None
            body = upstream_json(response, [token, *secrets])
            if response.status_code == 403:
                raise HTTPException(403, 'StoryCue 拒绝了本机 bridge-token。请确认目录后重新读取。')
            if response.status_code >= 400 or body.get('saved') is False:
                raise HTTPException(response.status_code if 400 <= response.status_code < 500 else 502, upstream_message(body, 'StoryCue 没有保存配置。请对照每一项的说明修改后再试。'))
            log.info('storycue setup forwarded status=%s', response.status_code)
            fresh = storycue_request('GET', '/api/trial/setup', token, directory, timeout=5)
            setup = public_setup(upstream_json(fresh, [token, *secrets])) if fresh.status_code < 400 else None
        return respond({'ok': True, 'saved': True, 'setup': setup, 'message': '配置已交给 StoryCue，写在它自己的 .env.local。工作台不保存 Key。若访谈已经开着，请用 VOICE_RELAY_PORT=8866 重新启动后再试。'})

    @app.post('/api/storycue/setup/test')
    async def setup_test(request: Request):
        data = await read_body(request, limit=4000)
        target = data.get('target')
        if target not in TEST_TARGETS:
            raise HTTPException(400, '请选择要测试的一项。')
        directory = directory_or_error()
        token = token_for(directory)
        with secret_scope([token, *secret_values(data)]):
            return respond(call_setup_test(token, target, [token], directory))

    @app.post('/api/storycue/start')
    def start():
        directory = directory_or_error()
        pid = launch(directory)
        return respond({'ok': True, 'pid': pid, 'start': startup_commands(directory), 'message': '已按 VOICE_RELAY_PORT=8866 尝试启动。若页面仍连不上，请改用下面这一条命令。'})

    @app.get('/api/workflow/topics/{ident}/storycue/panel')
    def panel(ident: str):
        return respond(panel_for(core, core.get('writing_topic', ident)))

    @app.post('/api/workflow/topics/{ident}/storycue/handoff')
    async def handoff(ident: str, request: Request):
        data = await read_body(request, limit=4000)
        topic = require_topic(core, ident)
        body = handoff_body(core, topic, data.get('framework'))
        directory = directory_or_error()
        token = token_for(directory)
        with secret_scope([token]):
            try:
                response = requests.post(origin() + '/api/trial/handoff', headers={'X-StoryCue-Bridge-Token': token, 'Accept': 'application/json', 'Content-Type': 'application/json'}, json=body, timeout=20)
            except requests.RequestException:
                log.info('storycue handoff unreachable')
                raise HTTPException(503, offline_message(directory)) from None
            payload = upstream_json(response, [token])
            if response.status_code >= 400 or payload.get('ok') is not True:
                raise HTTPException(response.status_code if 400 <= response.status_code < 500 else 502, upstream_message(payload, 'StoryCue 没有接住这次访谈。'))
            expected = f"{body['topicId']}-{body['revision']}"
            if payload.get('handoffId') != expected:
                raise HTTPException(502, 'StoryCue 返回的交接编号和这次选题不一致，没有打开页面。')
            open_url = accepted_open_url(payload.get('openUrl'), expected)
            view = storycue_request('GET', '/api/trial/handoff/' + quote(expected, safe=''), token, directory)
            viewed = upstream_json(view, [token])
            if view.status_code >= 400:
                raise HTTPException(view.status_code if view.status_code < 500 else 502, upstream_message(viewed, 'StoryCue 没有读回这次交接。'))
            if viewed.get('status') == 'superseded':
                raise HTTPException(409, '这次交接已被更新的脚本取代。请用当前确认稿重新交给 StoryCue。')
            if viewed.get('handoffId') != expected or viewed.get('topicId') != body['topicId'] or 'script' in viewed:
                raise HTTPException(502, 'StoryCue 读回的交接和这次提交不一致，没有打开页面。')
            save_link(core, topic['id'], body, open_url)
            log.info('storycue handoff %s status=%s', expected, viewed.get('status'))
        return respond({'ok': True, 'handoffId': expected, 'openUrl': open_url, 'framework': body['framework'], 'scriptSha256': body['scriptSha256'], 'backgroundChars': len(body['background']), 'demo': body['demo']})

    @app.post('/api/workflow/topics/{ident}/storycue/result/pull')
    def pull(ident: str):
        topic = require_topic(core, ident)
        link = read_link(core, topic['id'])
        if not link or not link.get('handoff_id'):
            raise HTTPException(409, '还没有交给 StoryCue。请先点「交给 StoryCue 访谈」。')
        directory = directory_or_error()
        token = token_for(directory)
        path = '/api/trial/handoff/' + quote(link['handoff_id'], safe='') + '/result'
        with secret_scope([token]):
            try:
                response = storycue_request('GET', path, token, directory)
            except HTTPException:
                raise
            payload = upstream_json(response, [token])
            if response.status_code == 404:
                raise HTTPException(404, 'StoryCue 里还没有这次访谈的回传结果。可在 StoryCue 点回传，或在这里上传回传 JSON。')
            if response.status_code >= 400:
                raise HTTPException(response.status_code if response.status_code < 500 else 502, upstream_message(payload, '这次交接已过期，请重新交给 StoryCue 访谈。'))
            stored = store_result(core, topic, payload)
            log.info('storycue result pulled %s', link['handoff_id'])
        return respond({'ok': True, 'interview': stored, 'demo': bool(topic.get('demo') or stored.get('demo'))})

    @app.post('/api/workflow/topics/{ident}/storycue/result')
    async def upload_result(ident: str, request: Request):
        data = await read_body(request, limit=1_500_000)
        topic = require_topic(core, ident)
        with secret_scope(secret_values(data)):
            stored = store_result(core, topic, data)
            log.info('storycue result uploaded %s', topic['id'])
        return respond({'ok': True, 'interview': stored, 'demo': bool(topic.get('demo') or stored.get('demo'))})

    return {'suggest_framework': suggest_framework, 'compress_background': compress_background, 'assemble_sayframe_handoff': assemble_sayframe_handoff, 'script_sha256': script_sha256}
