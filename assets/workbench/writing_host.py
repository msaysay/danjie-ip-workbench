"""Guide a learner to WorkBuddy or Codex for today's topics.

The page does not ask for a model Base URL. The host writes 今日选题.json in the
business folder; sync reads it back. A missing CLI still leaves copy-and-sync.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request

from desktop_cli import desktop_cli_location
from review_engine import ZONE

EMPTY_FILE = {'exists': False, 'matchesToday': False, 'writtenToday': False, 'date': ''}


def writing_ready(topic_file, synced_today):
    if synced_today:
        return True
    file = topic_file or EMPTY_FILE
    return bool(file.get('exists') and (file.get('matchesToday') or file.get('writtenToday')))


def daily_task_prompt(folder, count, time_text, host):
    label = {'workbuddy': 'WorkBuddy', 'codex': 'Codex'}.get(host, 'WorkBuddy 或 Codex')
    return (
        f'请先手动做一次，不要假定只有 WorkBuddy 能做：这次由{label}来写。'
        f'先读取业务文件夹“{folder}”里的客户卡、人设、当前写作要求、复盘留下的改稿方向、已留下的选题参考、最近写过的题目和已有稿件。'
        '先读同目录“写稿时沿用的方法.md”和“当前作业版本.json”，按蛋蛋的客户卡与三圈选题方法，'
        f'给我{count}个贴近客户问题的选题建议，并在后台按开头（03或07）、支撑（04）、肌肉句（05）、单一收尾（06）准备完整口播。'
        '读取已经完成的作业，不重复采访或让学员重新选卡；肌肉句用已有实力原句，没有成绩就只用真实职责，不编数字。'
        '把完整稿放入prepared_script，generated_by 填写你自己的名称（WorkBuddy 或 Codex）。'
        '用户选题后就能直接改。缺真实事实就保留缺口，不编业绩或客户故事。'
        '按“选题回传格式.md”把结果保存为“今日选题.json”，date填写本次运行当天的北京时间日期，'
        'source_shas 只引用本题上下文里的作业；不要替我确认脚本，不自动发布、不投流、不发消息。'
        '任务只读写本次文件夹，保留原件。确认文件生成并且工作台同步读回后即可。'
        f'若用 WorkBuddy 的定时任务，可以再设成每天北京时间{time_text}执行。'
    )


def _linked(path: Path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def topic_file_view(folder, today):
    if folder is None:
        return dict(EMPTY_FILE)
    target = folder / '今日选题.json'
    try:
        if _linked(target) or not target.is_file():
            return dict(EMPTY_FILE)
        stat = target.stat()
        written = datetime.fromtimestamp(stat.st_mtime, ZONE).date() == today
    except OSError:
        return dict(EMPTY_FILE)
    date = ''
    matches = False
    try:
        if stat.st_size <= 1024 * 1024:
            import json
            data = json.loads(target.read_text(encoding='utf-8-sig'))
            if isinstance(data, dict) and isinstance(data.get('date'), str):
                date = datetime.fromisoformat(data['date']).date().isoformat()
                matches = date == today.isoformat()
    except (OSError, ValueError, TypeError, UnicodeError):
        date = ''
        matches = False
    return {'exists': True, 'matchesToday': matches, 'writtenToday': written, 'date': date}


def attach(app, core):
    def chosen():
        rows = [row for row in core.listing('writing_host') if row.get('id') == 'main']
        host = rows[0].get('host') if rows else ''
        return host if host in ('workbuddy', 'codex') else ''

    def active_business():
        settings = core.WORKFLOW['settings']()
        pid = settings.get('profile_id')
        if not pid:
            return settings, None, None, None
        try:
            project = core.get('project', pid)
        except HTTPException:
            return settings, None, None, None
        memory = next((item for item in project.get('sources', []) if item.get('kind') == 'business_memory'), None)
        if not memory:
            return settings, project, None, None
        expected = (core.project_dir(pid) / 'workbuddy-business')
        try:
            expected = expected.resolve()
        except OSError:
            return settings, project, memory, None
        link = next((row for row in core.listing('business_chat_link') if row.get('profile_id') == pid), None)
        folder = None
        if link:
            raw = Path(str(link.get('folder') or ''))
            try:
                if raw.exists() and not _linked(raw) and raw.resolve() == expected and expected.parent == core.project_dir(pid).resolve():
                    folder = expected
            except OSError:
                folder = None
        return settings, project, memory, folder

    def snapshot():
        today = datetime.now(ZONE).date()
        settings, _project, memory, folder = active_business()
        host = chosen()
        topic_file = topic_file_view(folder, today)
        pid = settings.get('profile_id') if memory else None
        topics = [row for row in core.listing('writing_topic') if pid and row.get('profile_id') == pid and str(row.get('created', ''))[:10] == today.isoformat()]
        synced = bool(topics)
        link = next((row for row in core.listing('business_chat_link') if pid and row.get('profile_id') == pid), None)
        topic_errors = [item for item in (link.get('errors') or []) if '今日选题' in str(item)] if link else []
        count = settings.get('count') or 5
        at = settings.get('time') or '08:30'
        prompt = daily_task_prompt(str(folder), count, at, host) if folder else ''
        if not memory:
            message = '先在设置里选择本次业务，再复制每日任务。'
        elif not folder:
            message = '点「复制每日任务提示词」时，会先准备业务文件夹。'
        else:
            message = ''
        return {
            'host': host,
            'hosts': desktop_cli_location()['hosts'],
            'businessReady': bool(memory),
            'folder': str(folder or ''),
            'topicFile': topic_file,
            'syncedToday': synced,
            'todayCount': len(topics),
            'ready': writing_ready(topic_file, synced),
            'topicErrors': topic_errors[:5],
            'prompt': prompt,
            'count': count,
            'time': at,
            'message': message,
        }

    @app.get('/api/writing/host')
    def writing_host_status():
        return snapshot()

    @app.post('/api/writing/host')
    async def writing_host_choose(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = None
        if not isinstance(data, dict):
            raise HTTPException(400, '请选择 WorkBuddy 或 Codex')
        host = data.get('host')
        if host not in ('workbuddy', 'codex'):
            raise HTTPException(400, '请选择 WorkBuddy 或 Codex')
        core.put('writing_host', {'id': 'main', 'host': host})
        return snapshot()
