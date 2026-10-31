"""Install optional publisher, analytics, or transcribe dependencies.

Publisher and analytics each get a virtual environment whose Python satisfies
that vendor package's requires-python and can create a venv (ensurepip).
The current interpreter is kept when it qualifies, so an offline student
package keeps working when this script is already running under the bundled
Python 3.12. Otherwise the workbench portable runtime is used
(.runtime/python, or the matching assets/runtimes archive), then
python3.12 / python3.11 / python3.10 on PATH. Nothing is created when no
candidate qualifies.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
APP = PKG / 'assets' / 'workbench'
VERSION_PROBE = 'import sys; print("%d.%d.%d" % sys.version_info[:3])'
VENV_PROBE = 'import venv, ensurepip'
_REQUIRES_LINE = re.compile(r'''(?m)^requires-python\s*=\s*(['"])([^'"]+)\1\s*$''')
_CLAUSE = re.compile(r'^(>=|<=|==|!=|~=|>|<)\s*(\d+(?:\.\d+){0,2})$')
_PREFERRED_MINORS = (12, 11, 10)


def run(args, **kwargs):
    subprocess.run([str(item) for item in args], check=True, cwd=APP, **kwargs)


def format_version(version):
    return '.'.join(str(part) for part in version)


def parse_requires_python(spec):
    clauses = []
    for raw in spec.split(','):
        clause = raw.strip()
        if not clause:
            continue
        match = _CLAUSE.fullmatch(clause)
        if not match:
            raise ValueError(f'无法解析 requires-python 条款：{clause}')
        release = tuple(int(part) for part in match.group(2).split('.'))
        clauses.append((match.group(1), release))
    if not clauses:
        raise ValueError('requires-python 为空')
    return clauses


def _compare(left, right):
    size = max(len(left), len(right))
    padded_left = left + (0,) * (size - len(left))
    padded_right = right + (0,) * (size - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


def version_satisfies(version, spec):
    version = tuple(version[:3])
    for operator, release in parse_requires_python(spec):
        compared = _compare(version, release)
        if operator == '>=' and compared < 0:
            return False
        if operator == '>' and compared <= 0:
            return False
        if operator == '<=' and compared > 0:
            return False
        if operator == '<' and compared >= 0:
            return False
        if operator == '==' and compared != 0:
            return False
        if operator == '!=' and compared == 0:
            return False
        if operator == '~=':
            if len(release) < 2:
                raise ValueError('~= 至少需要两个版本号')
            if compared < 0 or version[:len(release) - 1] != release[:-1]:
                return False
    return True


def read_requires_python(repo):
    path = Path(repo) / 'pyproject.toml'
    if not path.is_file():
        raise SystemExit(f'找不到 {path}，无法确认 requires-python。')
    match = _REQUIRES_LINE.search(path.read_text(encoding='utf-8'))
    if not match:
        raise SystemExit(f'{path} 没有 requires-python，不能猜测解释器版本。')
    spec = match.group(2).strip()
    try:
        parse_requires_python(spec)
    except ValueError as exc:
        raise SystemExit(f'{path} 的 requires-python 无法解析（{spec}）：{exc}') from exc
    return spec


def interpreter_version(executable):
    try:
        completed = subprocess.run(
            [str(executable), '-c', VERSION_PROBE],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    parts = completed.stdout.strip().split('.')
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def interpreter_supports_venv(executable):
    try:
        subprocess.run(
            [str(executable), '-c', VENV_PROBE],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def venv_python(folder):
    return Path(folder) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def portable_layouts(windows):
    if windows:
        return [Path('python.exe')]
    return [Path('bin') / 'python3', Path('bin') / 'python']


def runtime_platform_for(system, machine):
    # Same names as assets/runtime-manifest.json and the launch scripts.
    # There is no Linux archive; Windows always uses the x64 bundle.
    if system in ('win32', 'cygwin', 'nt'):
        return 'windows-x64'
    if system == 'darwin':
        if machine.lower() in ('arm64', 'aarch64'):
            return 'mac-arm64'
        if machine.lower() in ('x86_64', 'amd64'):
            return 'mac-x64'
    return None


def runtime_platform():
    return runtime_platform_for(sys.platform, platform.machine())


def extracted_portable_python(package_root):
    root = Path(package_root) / '.runtime' / 'python'
    for relative in portable_layouts(os.name == 'nt'):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def safe_tar_member(name):
    if not name or name.startswith(('/', '\\')) or '\\' in name:
        return False
    return '..' not in Path(name).parts


def safe_link(member):
    if not (member.issym() or member.islnk()):
        return True
    link = member.linkname or ''
    if not link or link.startswith(('/', '\\')) or '\\' in link:
        return False
    return '..' not in Path(link).parts


def assert_archive_safe(archive):
    with tarfile.open(archive, 'r:gz') as packed:
        for member in packed.getmembers():
            if not safe_tar_member(member.name) or not safe_link(member):
                raise SystemExit(f'便携运行时压缩包包含不安全路径：{member.name}')


def extract_runtime_archive(archive, destination):
    assert_archive_safe(archive)
    destination.mkdir(parents=True, exist_ok=True)
    tar_bin = shutil.which('tar')
    if tar_bin:
        subprocess.run([tar_bin, '-xzf', str(archive), '-C', str(destination)], check=True)
        return
    with tarfile.open(archive, 'r:gz') as packed:
        kwargs = {}
        if 'filter' in tarfile.TarFile.extractall.__code__.co_varnames:
            kwargs['filter'] = 'data'
        packed.extractall(destination, **kwargs)


def ensure_portable_python(package_root=None, platform_name=None):
    package_root = Path(package_root or PKG)
    existing = extracted_portable_python(package_root)
    if existing:
        return existing
    if platform_name is None:
        platform_name = runtime_platform()
    if not platform_name:
        return None
    archive = package_root / 'assets' / 'runtimes' / f'{platform_name}.tar.gz'
    if not archive.is_file():
        return None
    print(f'正在解压本包便携 Python：{archive.name}', flush=True)
    try:
        extract_runtime_archive(archive, package_root / '.runtime')
    except (subprocess.CalledProcessError, tarfile.TarError, OSError) as exc:
        print(f'便携运行时无法解压，将继续寻找其他 Python：{exc}', flush=True)
        return None
    return extracted_portable_python(package_root)


def iter_path_interpreters():
    seen = set()
    names = [f'python3.{minor}' for minor in _PREFERRED_MINORS] + ['python3', 'python']
    for name in names:
        found = shutil.which(name)
        if not found:
            continue
        resolved = str(Path(found).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        yield Path(found)
    if os.name != 'nt' or not shutil.which('py'):
        return
    for minor in _PREFERRED_MINORS:
        try:
            completed = subprocess.run(
                ['py', f'-3.{minor}', '-c', 'import sys; print(sys.executable)'],
                check=True, capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        found = completed.stdout.strip()
        if not found:
            continue
        resolved = str(Path(found).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        yield Path(found)


def refusal_message(spec, feature, checked):
    command = 'publish' if feature == 'publish' else 'analytics'
    details = '\n'.join(f'- {line}' for line in checked) or '- 没有可检查的解释器'
    return (
        f'此扩展要求 Python 满足 {spec}，并且自带 venv/ensurepip。\n'
        f'已检查：\n{details}\n'
        '没有创建虚拟环境。只存在解释器文件不会让 /api/health 的 publisher 变为 true。\n'
        '可以任选一种方式后重新运行 '
        f'`python scripts/install_optional.py {command}`：\n'
        '1. 用学员包里的便携 Python 3.12 执行（Windows：启动-Windows.cmd；Mac：启动-Mac.command）。'
        '已解压的解释器在 .runtime/python。\n'
        '2. 安装包若已带 assets/runtimes/windows-x64.tar.gz、mac-arm64.tar.gz 或 mac-x64.tar.gz，'
        '重新运行会解压当前系统对应的那一份。清单里没有 Linux 便携运行时。\n'
        '3. 安装仍满足上述范围的 Python 3.12、3.11 或 3.10，并让 python3.12 出现在 PATH 中'
        '（Windows 也可用 py -3.12）。Debian/Ubuntu 还需要虚拟环境包，例如：'
        'sudo apt install python3.12-venv。'
    )


def choose_base_python(spec, feature='publish', package_root=None, current=None, current_version=None,
                        portable_finder=None, path_finder=None, version_of=None, supports_venv_of=None):
    package_root = Path(package_root or PKG)
    version_of = version_of or interpreter_version
    supports_venv_of = supports_venv_of or interpreter_supports_venv
    path_finder = path_finder or iter_path_interpreters
    if current is None:
        current = Path(sys.executable)
        if current_version is None:
            current_version = tuple(sys.version_info[:3])
    elif current_version is None:
        current_version = version_of(current)
    if portable_finder is None:
        def portable_finder():
            return ensure_portable_python(package_root)

    checked = []
    seen = set()

    def consider(label, path, version):
        resolved = str(Path(path).resolve())
        if resolved in seen:
            return None
        seen.add(resolved)
        if version is None:
            checked.append(f'{label}：无法读取 Python 版本（{path}）')
            return None
        if not version_satisfies(version, spec):
            checked.append(f'{label}：Python {format_version(version)}（{path}）不满足 {spec}')
            return None
        if not supports_venv_of(path):
            checked.append(
                f'{label}：Python {format_version(version)}（{path}）不能创建带 pip 的虚拟环境（缺少 venv/ensurepip）'
            )
            return None
        print(f'{label}可用：{path}（Python {format_version(version)}）', flush=True)
        return Path(path)

    selected = consider('当前解释器', current, current_version)
    if selected:
        return selected
    portable = portable_finder()
    if portable is None:
        platform_name = runtime_platform()
        if platform_name is None:
            checked.append('便携运行时：assets/runtime-manifest.json 没有当前系统的包（仅 Windows 与 Mac）')
        else:
            archive = package_root / 'assets' / 'runtimes' / f'{platform_name}.tar.gz'
            checked.append(f'便携运行时：没有已解压的 .runtime/python，也没有 {archive}')
    else:
        selected = consider('便携运行时', portable, version_of(portable))
        if selected:
            return selected
    found_on_path = False
    for candidate in path_finder():
        found_on_path = True
        selected = consider('PATH', candidate, version_of(candidate))
        if selected:
            return selected
    if not found_on_path:
        checked.append('PATH：没有 python3.12、python3.11、python3.10、python3 或 python')
    raise SystemExit(refusal_message(spec, feature, checked))


def _remove_tree(folder):
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        raise SystemExit(f'无法删除不兼容的虚拟环境 {folder}：{exc}') from exc


def ensure_venv(venv, base, spec, env=None):
    venv = Path(venv)
    python = venv_python(venv)
    if python.is_file():
        version = interpreter_version(python)
        if version and version_satisfies(version, spec):
            print(f'沿用已有虚拟环境：{python}（Python {format_version(version)}）', flush=True)
            return python
        print(f'已有虚拟环境不符合 {spec}，将重建：{venv}', flush=True)
        _remove_tree(venv)
    elif venv.exists():
        _remove_tree(venv)
    print(f'创建虚拟环境：{venv}', flush=True)
    try:
        subprocess.run([str(base), '-m', 'venv', str(venv)], check=True, env=env)
    except (OSError, subprocess.CalledProcessError) as exc:
        shutil.rmtree(venv, ignore_errors=True)
        raise SystemExit(f'无法用 {base} 创建虚拟环境：{exc}') from exc
    if not python.is_file():
        shutil.rmtree(venv, ignore_errors=True)
        raise SystemExit(f'虚拟环境已创建，但没有找到 {python}')
    version = interpreter_version(python)
    if not version or not version_satisfies(version, spec):
        found = format_version(version) if version else '未知'
        shutil.rmtree(venv, ignore_errors=True)
        raise SystemExit(f'新建虚拟环境的 Python 是 {found}，不满足 {spec}，已删除该环境。')
    return python


def ensure_feature_venv(repo, feature='publish', **choose_kwargs):
    spec = read_requires_python(repo)
    base = choose_base_python(spec, feature=feature, **choose_kwargs)
    return ensure_venv(Path(repo) / '.venv', base, spec)


def install_feature(feature, env=None, repo=None):
    if repo is None:
        repo = APP / 'vendor' / ('social-auto-upload' if feature == 'publish' else 'douyin-mcp')
    repo = Path(repo)
    label = '发布器' if feature == 'publish' else '数据模块'
    python = ensure_feature_venv(repo, feature=feature)
    try:
        run([python, '-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple', '-e', repo], env=env)
    except subprocess.CalledProcessError as exc:
        extra = ' /api/health 的 publisher 只有在该环境能导入 social-auto-upload 时才为 true。' if feature == 'publish' else ''
        raise SystemExit(
            f'{label}的可编辑安装失败（退出码 {exc.returncode}）。'
            f'虚拟环境里的 Python 还在，并不表示已经安装成功。{extra}'
        ) from exc
    if feature == 'publish':
        if not (repo / 'conf.py').exists():
            shutil.copyfile(repo / 'conf.example.py', repo / 'conf.py')
        for name in ['cookies', 'logs', 'media', 'videos', 'db']:
            (repo / name).mkdir(exist_ok=True)
    browser = 'patchright' if feature == 'publish' else 'playwright'
    run([python, '-m', browser, 'install', 'chromium'], env=env)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('feature', choices=['publish', 'analytics', 'transcribe'])
    args = parser.parse_args(argv)
    print('此扩展需要联网下载开源依赖；不会登录账号或发布。', flush=True)
    env = {**os.environ, 'PYTHONUTF8': '1', 'PLAYWRIGHT_BROWSERS_PATH': str(APP / 'data' / 'browsers')}
    try:
        if args.feature == 'transcribe':
            run([sys.executable, '-I', '-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple', 'faster-whisper>=1.1,<2'], env=env)
            run([sys.executable, '-c', "from huggingface_hub import snapshot_download;snapshot_download('Systran/faster-whisper-small')"], env=env)
        else:
            install_feature(args.feature, env=env)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f'扩展安装未完成（退出码 {exc.returncode}）。上面的命令输出是失败原因。') from exc
    print('扩展安装完成。请由学员本人登录自己的账号。')


if __name__ == '__main__':
    main()
