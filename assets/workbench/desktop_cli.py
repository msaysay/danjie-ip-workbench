"""Locate Codex and CodeBuddy on this computer without running them.

StoryCue status and the writing-host wizard share this probe. It looks on PATH,
common install directories, and the global npm packages `@openai/codex` and
`@tencent-ai/codebuddy-code`. A missing CLI is a normal result.

Opening a login window is separate: it starts a visible terminal. WorkBuddy's
`codebuddy` command only opens a browser after the person picks a site in that
window. This is not the Douyin or Channels QR login.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

HOST_SPECS = (
    {
        'id': 'workbuddy',
        'label': 'WorkBuddy',
        'command': 'codebuddy',
        'package': '@tencent-ai/codebuddy-code',
        'install_url': 'https://www.codebuddy.cn/docs/cli/installation',
        'app_url': 'https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Automation-Guide',
    },
    {
        'id': 'codex',
        'label': 'Codex',
        'command': 'codex',
        'package': '@openai/codex',
        'install_url': 'https://developers.openai.com/codex/cli',
        'app_url': 'https://developers.openai.com/codex/cli',
    },
)


def _package_json(root: Path, package: str) -> Path:
    return root.joinpath(*package.split('/'), 'package.json')


def candidate_bins(command: str, home: Path):
    names = [command, command + '.cmd', command + '.exe']
    roots = [
        home / '.local' / 'bin',
        home / '.npm-global' / 'bin',
        home / 'AppData' / 'Roaming' / 'npm',
        home / 'AppData' / 'Local' / 'codebuddy' / 'bin',
    ]
    for root in roots:
        for name in names:
            yield root / name


def read_npm_root(runner=None):
    npm = shutil.which('npm')
    if not npm:
        return None, ''
    runner = runner or subprocess.run
    try:
        done = runner([npm, 'root', '-g'], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None, 'npm 没有在时限内返回全局目录'
    if getattr(done, 'returncode', 1) != 0:
        return None, 'npm 没有返回全局目录'
    lines = [line.strip() for line in str(getattr(done, 'stdout', '') or '').splitlines() if line.strip()]
    if not lines:
        return None, 'npm 没有返回全局目录'
    return Path(lines[-1]), ''


def desktop_cli_location(*, which=None, home=None, npm_root=None, is_file=None, npm_runner=None):
    which = which or shutil.which
    home = Path(home) if home is not None else Path.home()
    is_file = is_file or (lambda path: Path(path).is_file())
    npm_error = ''
    if npm_root is None:
        npm_root_path, npm_error = read_npm_root(npm_runner)
    elif npm_root:
        npm_root_path = Path(npm_root)
    else:
        npm_root_path = None
    hosts = []
    for spec in HOST_SPECS:
        via = []
        path = ''
        found_which = which(spec['command']) if which else None
        if found_which:
            via.append('path')
            path = str(found_which)
        if not path:
            for candidate in candidate_bins(spec['command'], home):
                try:
                    present = bool(is_file(candidate))
                except OSError:
                    present = False
                if present:
                    via.append('path')
                    path = str(candidate)
                    break
        package_found = False
        if npm_root_path is not None:
            try:
                package_found = bool(is_file(_package_json(npm_root_path, spec['package'])))
            except OSError:
                package_found = False
            if package_found:
                via.append('npm')
        hosts.append({
            'id': spec['id'],
            'label': spec['label'],
            'command': spec['command'],
            'package': spec['package'],
            'installUrl': spec['install_url'],
            'appUrl': spec['app_url'],
            'found': bool(via),
            'via': via,
            'path': path,
            'packageFound': package_found,
        })
    return {'hosts': hosts, 'npmRoot': str(npm_root_path or ''), 'npmError': npm_error}


def login_launch_plan(host_id, command_path, platform):
    """Plan a visible terminal for writing-host login. Does not start it."""
    if host_id not in ('workbuddy', 'codex'):
        return {'opened': False, 'argv': [], 'message': '请选择 WorkBuddy 或 Codex。这是写稿登录，不是抖音或视频号扫码。'}
    command_path = str(command_path or '')
    manual = 'codebuddy' if host_id == 'workbuddy' else 'codex login'
    if not command_path:
        return {
            'opened': False,
            'argv': [],
            'message': f'还没找到命令。请自己打开终端，运行 {manual}。写稿登录不会出现在发布页的二维码里。',
        }
    if host_id == 'codex':
        args = [command_path, 'login']
        message = '已尝试打开 Codex 登录。浏览器由这条命令弹出。这不是抖音或视频号扫码。'
    else:
        args = [command_path]
        message = '已尝试打开 WorkBuddy 的命令窗口。请选择「国内站」并回车，浏览器才会出现。选之前没有浏览器。这不是发布账号扫码。'
    if platform == 'win32':
        argv = ['cmd', '/c', 'start', '写稿登录', 'cmd', '/k', *args]
    elif platform == 'darwin':
        script = ' '.join(shlex.quote(part) for part in args)
        escaped = script.replace('\\', '\\\\').replace('"', '\\"')
        argv = ['osascript', '-e', f'tell application "Terminal" to do script "{escaped}"']
    else:
        quoted = ' '.join(shlex.quote(part) for part in args)
        argv = ['x-terminal-emulator', '-e', 'bash', '-lc', quoted]
    return {'opened': True, 'argv': argv, 'message': message}


def start_login_window(argv, runner=None):
    runner = runner or subprocess.Popen
    return runner(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
