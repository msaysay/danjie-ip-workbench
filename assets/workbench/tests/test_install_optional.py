import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
PKG = APP.parents[1]
sys.path.insert(0, str(APP))
_SPEC = importlib.util.spec_from_file_location('install_optional_under_test', PKG / 'scripts' / 'install_optional.py')
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

import server as workbench_server
from fastapi.testclient import TestClient


def write_fake_python(path, version, log_path, allow_venv=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''#!{sys.executable}
import sys
from pathlib import Path
log = Path({str(log_path)!r})
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as handle:
    handle.write(repr(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args[:1] == ["-c"]:
    code = args[1]
    if "ensurepip" in code:
        raise SystemExit(0 if {allow_venv!r} else 1)
    if "version_info" in code:
        print({version!r})
        raise SystemExit(0)
    raise SystemExit(1)
if args[:2] == ["-m", "venv"] and {allow_venv!r}:
    dest = Path(args[2])
    binary = dest / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(Path(sys.argv[0]).read_text(encoding="utf-8"), encoding="utf-8")
    binary.chmod(0o755)
    raise SystemExit(0)
raise SystemExit(1)
''',
        encoding='utf-8',
    )
    path.chmod(0o755)
    return path


class RequiresPythonTests(unittest.TestCase):
    def test_vendor_packages_declare_the_expected_ranges(self):
        self.assertEqual(mod.read_requires_python(APP / 'vendor' / 'social-auto-upload'), '>=3.10,<3.13')
        self.assertEqual(mod.read_requires_python(APP / 'vendor' / 'douyin-mcp'), '>=3.11')

    def test_publisher_range_rejects_313_and_accepts_310_through_312(self):
        spec = '>=3.10,<3.13'
        self.assertTrue(mod.version_satisfies((3, 10, 0), spec))
        self.assertTrue(mod.version_satisfies((3, 12, 16), spec))
        self.assertFalse(mod.version_satisfies((3, 9, 18), spec))
        self.assertFalse(mod.version_satisfies((3, 13, 0), spec))
        self.assertTrue(mod.version_satisfies((3, 11, 0), '>=3.11'))
        self.assertFalse(mod.version_satisfies((3, 10, 12), '>=3.11'))
        self.assertTrue(mod.version_satisfies((3, 12, 8), '~=3.12'))
        self.assertTrue(mod.version_satisfies((3, 13, 0), '~=3.12'))
        self.assertFalse(mod.version_satisfies((3, 11, 0), '~=3.12'))
        self.assertFalse(mod.version_satisfies((3, 13, 0), '~=3.12.1'))
        self.assertTrue(mod.version_satisfies((3, 12, 1), '>=3.10, <3.13'))

    def test_unparsed_requires_python_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.parse_requires_python('>=3.10, *')


class InterpreterSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fake(self, name, version, allow_venv=True):
        return write_fake_python(self.root / name, version, self.root / f'{name}.log', allow_venv=allow_venv)

    def repo(self, spec='>=3.10,<3.13'):
        folder = self.root / 'vendor-repo'
        folder.mkdir()
        (folder / 'pyproject.toml').write_text(f'requires-python = "{spec}"\n', encoding='utf-8')
        return folder

    def test_current_interpreter_wins_when_it_already_qualifies(self):
        current = self.fake('py312', '3.12.16')

        def fail_portable():
            raise AssertionError('portable runtime should not be consulted')

        def fail_path():
            raise AssertionError('PATH should not be consulted')

        chosen = mod.choose_base_python(
            '>=3.10,<3.13', current=current, portable_finder=fail_portable, path_finder=fail_path,
        )
        self.assertEqual(chosen, current)

    def test_python_313_does_not_create_publisher_venv_when_312_exists(self):
        current = self.fake('py313', '3.13.1')
        preferred = self.fake('py312', '3.12.8')
        folder = self.repo()
        python = mod.ensure_feature_venv(
            folder, current=current, portable_finder=lambda: None, path_finder=lambda: [preferred],
        )
        self.assertEqual(mod.interpreter_version(python), (3, 12, 8))
        log = (self.root / 'py313.log').read_text(encoding='utf-8')
        self.assertNotIn("'-m', 'venv'", log)
        self.assertIn('version_info', log)

    def test_incompatible_existing_venv_is_rebuilt_with_the_selected_python(self):
        stale = self.fake('py313', '3.13.0')
        base = self.fake('py312', '3.12.4')
        folder = self.repo()
        target = mod.venv_python(folder / '.venv')
        target.parent.mkdir(parents=True)
        target.write_text(stale.read_text(encoding='utf-8'), encoding='utf-8')
        target.chmod(0o755)
        python = mod.ensure_venv(folder / '.venv', base, '>=3.10,<3.13')
        self.assertEqual(mod.interpreter_version(python), (3, 12, 4))
        self.assertNotIn("'-m', 'venv'", (self.root / 'py313.log').read_text(encoding='utf-8'))

    def test_venv_directory_without_python_is_rebuilt(self):
        base = self.fake('py312', '3.12.4')
        folder = self.repo()
        broken = folder / '.venv' / 'bin'
        broken.mkdir(parents=True)
        (broken / 'README').write_text('no interpreter', encoding='utf-8')
        python = mod.ensure_venv(folder / '.venv', base, '>=3.10,<3.13')
        self.assertTrue(python.is_file())
        self.assertEqual(mod.interpreter_version(python), (3, 12, 4))
        self.assertFalse((broken / 'README').exists())

    def test_compatible_venv_is_reused(self):
        base = self.fake('py-base', '3.12.1')
        folder = self.repo()
        existing = mod.venv_python(folder / '.venv')
        write_fake_python(existing, '3.12.1', self.root / 'existing.log')
        python = mod.ensure_venv(folder / '.venv', base, '>=3.10,<3.13')
        self.assertEqual(python, existing)
        self.assertFalse((self.root / 'py-base.log').exists())

    def test_portable_runtime_is_preferred_over_path_when_current_is_too_new(self):
        current = self.fake('py313', '3.13.2')
        portable = self.fake('portable', '3.12.16')
        other = self.fake('path312', '3.12.0')
        calls = []

        def portable_finder():
            calls.append('portable')
            return portable

        def path_finder():
            calls.append('path')
            return [other]

        chosen = mod.choose_base_python(
            '>=3.10,<3.13', current=current, portable_finder=portable_finder, path_finder=path_finder,
        )
        self.assertEqual(chosen, portable)
        self.assertEqual(calls, ['portable'])

    def test_analytics_can_keep_313_but_not_310(self):
        current = self.fake('py313', '3.13.0')
        chosen = mod.choose_base_python(
            '>=3.11', feature='analytics', current=current,
            portable_finder=lambda: None, path_finder=lambda: [],
        )
        self.assertEqual(chosen, current)
        older = self.fake('py310', '3.10.12')
        newer = self.fake('py311', '3.11.9')
        chosen = mod.choose_base_python(
            '>=3.11', feature='analytics', current=older,
            portable_finder=lambda: None, path_finder=lambda: [newer],
        )
        self.assertEqual(chosen, newer)

    def test_missing_interpreter_refuses_without_creating_a_venv(self):
        current = self.fake('py313', '3.13.1')
        folder = self.repo()
        with self.assertRaises(SystemExit) as caught:
            mod.ensure_feature_venv(folder, current=current, portable_finder=lambda: None, path_finder=lambda: [])
        message = str(caught.exception)
        self.assertIn('>=3.10,<3.13', message)
        self.assertIn('python3.12', message)
        self.assertIn('.runtime/python', message)
        self.assertIn('启动-Windows.cmd', message)
        self.assertIn('启动-Mac.command', message)
        self.assertIn('python3.12-venv', message)
        self.assertFalse((folder / '.venv').exists())

    def test_version_match_without_ensurepip_is_not_used(self):
        current = self.fake('py312', '3.12.3', allow_venv=False)
        folder = self.repo()
        with self.assertRaises(SystemExit) as caught:
            mod.ensure_feature_venv(folder, current=current, portable_finder=lambda: None, path_finder=lambda: [])
        self.assertIn('ensurepip', str(caught.exception))
        self.assertFalse((folder / '.venv').exists())

    def test_path_search_prefers_312_then_311_then_310(self):
        bindir = self.root / 'bin'
        bindir.mkdir()
        for name in ['python3.10', 'python3', 'python3.12']:
            binary = bindir / name
            binary.write_text('#!/bin/sh\n', encoding='utf-8')
            binary.chmod(0o755)
        old = os.environ.get('PATH')
        os.environ['PATH'] = str(bindir)
        try:
            found = [item.name for item in mod.iter_path_interpreters()]
        finally:
            if old is None:
                os.environ.pop('PATH', None)
            else:
                os.environ['PATH'] = old
        self.assertEqual(found[:3], ['python3.12', 'python3.10', 'python3'])

    def test_layouts_match_the_launch_scripts(self):
        self.assertEqual(mod.portable_layouts(True), [Path('python.exe')])
        self.assertEqual(mod.portable_layouts(False), [Path('bin/python3'), Path('bin/python')])
        self.assertEqual(mod.runtime_platform_for('win32', 'amd64'), 'windows-x64')
        self.assertEqual(mod.runtime_platform_for('darwin', 'arm64'), 'mac-arm64')
        self.assertEqual(mod.runtime_platform_for('darwin', 'aarch64'), 'mac-arm64')
        self.assertEqual(mod.runtime_platform_for('darwin', 'x86_64'), 'mac-x64')
        self.assertIsNone(mod.runtime_platform_for('linux', 'x86_64'))


class PortableArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, members):
        path = self.root / 'assets' / 'runtimes' / 'mac-arm64.tar.gz'
        path.parent.mkdir(parents=True)
        with tarfile.open(path, 'w:gz') as packed:
            for name, body in members:
                data = body.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                packed.addfile(info, io.BytesIO(data))
        return path

    def test_matching_archive_is_extracted_into_runtime_python(self):
        self.archive([('python/bin/python3', 'print("runtime")\n')])
        found = mod.ensure_portable_python(self.root, platform_name='mac-arm64')
        self.assertEqual(found, self.root / '.runtime' / 'python' / 'bin' / 'python3')
        self.assertTrue(found.is_file())

    def test_existing_runtime_is_not_overwritten(self):
        existing = self.root / '.runtime' / 'python' / 'bin' / 'python3'
        existing.parent.mkdir(parents=True)
        existing.write_text('already', encoding='utf-8')
        archive = self.root / 'assets' / 'runtimes' / 'mac-arm64.tar.gz'
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'not a tarball')
        found = mod.ensure_portable_python(self.root, platform_name='mac-arm64')
        self.assertEqual(found, existing)
        self.assertEqual(existing.read_text(encoding='utf-8'), 'already')

    def test_unsafe_archive_is_refused(self):
        archive = self.archive([('../outside.txt', 'escape')])
        outside = self.root / 'outside.txt'
        with self.assertRaises(SystemExit):
            mod.extract_runtime_archive(archive, self.root / '.runtime')
        self.assertFalse(outside.exists())


class InstallCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / 'social-auto-upload'
        self.repo.mkdir()
        (self.repo / 'pyproject.toml').write_text('requires-python = ">=3.10,<3.13"\n', encoding='utf-8')
        (self.repo / 'conf.example.py').write_text('BASE = 1\n', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_publish_install_uses_the_venv_python_and_stops_when_pip_fails(self):
        calls = []

        def fake_ensure(repo, feature='publish', **kwargs):
            return repo / '.venv' / 'bin' / 'python'

        def fake_run(args, **kwargs):
            calls.append([str(item) for item in args])
            raise subprocess.CalledProcessError(1, args)

        with patch.object(mod, 'ensure_feature_venv', fake_ensure), patch.object(mod, 'run', fake_run):
            with self.assertRaises(SystemExit) as caught:
                mod.install_feature('publish', repo=self.repo)
        self.assertEqual(calls[0][0], str(self.repo / '.venv' / 'bin' / 'python'))
        self.assertIn('-e', calls[0])
        self.assertIn(str(self.repo), calls[0])
        self.assertIn('publisher', str(caught.exception))
        self.assertFalse((self.repo / 'conf.py').exists())

    def test_successful_publish_install_prepares_conf_and_patchright(self):
        calls = []

        def fake_ensure(repo, feature='publish', **kwargs):
            return repo / '.venv' / 'bin' / 'python'

        def fake_run(args, **kwargs):
            calls.append([str(item) for item in args])

        with patch.object(mod, 'ensure_feature_venv', fake_ensure), patch.object(mod, 'run', fake_run):
            mod.install_feature('publish', repo=self.repo)
        self.assertEqual((self.repo / 'conf.py').read_text(encoding='utf-8'), 'BASE = 1\n')
        self.assertTrue((self.repo / 'cookies').is_dir())
        self.assertIn('patchright', calls[1])
        self.assertIn('chromium', calls[1])

    def test_analytics_uses_playwright_and_does_not_copy_publisher_config(self):
        calls = []

        def fake_ensure(repo, feature='publish', **kwargs):
            return repo / '.venv' / 'bin' / 'python'

        def fake_run(args, **kwargs):
            calls.append([str(item) for item in args])

        with patch.object(mod, 'ensure_feature_venv', fake_ensure), patch.object(mod, 'run', fake_run):
            mod.install_feature('analytics', repo=self.repo)
        self.assertIn('playwright', calls[1])
        self.assertFalse((self.repo / 'conf.py').exists())

    def test_transcribe_stays_on_the_current_interpreter(self):
        calls = []

        def fake_run(args, **kwargs):
            calls.append([str(item) for item in args])

        with patch.object(mod, 'run', fake_run):
            mod.main(['transcribe'])
        self.assertEqual(calls[0][0], sys.executable)
        self.assertIn('faster-whisper>=1.1,<2', calls[0])

    def test_main_publish_delegates_and_does_not_finish_when_install_fails(self):
        def boom(feature, env=None, repo=None):
            raise SystemExit('可编辑安装失败')

        with patch.object(mod, 'install_feature', boom):
            with self.assertRaises(SystemExit) as caught:
                mod.main(['publish'])
        self.assertIn('可编辑安装失败', str(caught.exception))


class PublisherHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = workbench_server.DATA, workbench_server.DB, workbench_server.SAUPY
        workbench_server.DATA = Path(self.temp.name)
        workbench_server.DB = workbench_server.DATA / 'test.sqlite3'
        with workbench_server.connect() as connection:
            connection.execute('CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
        self.client = TestClient(workbench_server.app)

    def tearDown(self):
        workbench_server.DATA, workbench_server.DB, workbench_server.SAUPY = self.old
        self.temp.cleanup()

    def test_missing_binary_is_not_ready(self):
        workbench_server.SAUPY = Path(self.temp.name) / 'missing' / 'bin' / 'python'
        body = self.client.get('/api/health').json()
        self.assertFalse(body['publisher'])
        self.assertIn('请先安装发布器依赖', body['publisher_message'])
        self.assertIn('install_optional.py publish', body['publisher_message'])
        self.assertNotIn('发布器目录还在', body['publisher_message'])
        state = self.client.get('/api/state').json()
        self.assertFalse(state['publisher'])
        self.assertIn('install_optional.py publish', state['publisher_message'])

    def test_venv_directory_without_python_says_how_to_rebuild(self):
        workbench_server.SAUPY = Path(self.temp.name) / '.venv' / 'bin' / 'python'
        workbench_server.SAUPY.parent.parent.mkdir()
        body = self.client.get('/api/health').json()
        self.assertFalse(body['publisher'])
        self.assertIn('发布器目录还在', body['publisher_message'])
        self.assertIn('没有 Python', body['publisher_message'])
        self.assertIn('删掉坏环境再重建', body['publisher_message'])
        created = self.client.post(
            '/api/accounts',
            json={'platform': 'douyin', 'alias': 'acct_1', 'label': '测试'},
            headers={'x-workbench-token': workbench_server.TOKEN},
        )
        denied = self.client.post(
            '/api/accounts/' + created.json()['id'] + '/login',
            headers={'x-workbench-token': workbench_server.TOKEN},
        )
        self.assertEqual(denied.status_code, 409)
        self.assertIn('请先安装发布器依赖', denied.json()['detail'])
        self.assertIn('没有 Python', denied.json()['detail'])

    def test_existing_python_without_the_package_is_not_ready(self):
        workbench_server.SAUPY = Path(sys.executable)
        body = self.client.get('/api/health').json()
        self.assertFalse(body['publisher'])
        created = self.client.post(
            '/api/accounts',
            json={'platform': 'douyin', 'alias': 'acct_1', 'label': '测试'},
            headers={'x-workbench-token': workbench_server.TOKEN},
        )
        self.assertEqual(created.status_code, 200, created.text)
        denied = self.client.post(
            '/api/accounts/' + created.json()['id'] + '/login',
            headers={'x-workbench-token': workbench_server.TOKEN},
        )
        self.assertEqual(denied.status_code, 409)

    def test_probe_imports_the_distribution_outside_the_vendor_tree(self):
        log = Path(self.temp.name) / 'probe.log'
        script = Path(self.temp.name) / 'bin' / 'python'
        script.parent.mkdir()
        script.write_text(
            f'''#!{sys.executable}
import os, sys
from pathlib import Path
Path({str(log)!r}).write_text(os.getcwd() + "\\n" + repr(sys.argv[1:]), encoding="utf-8")
raise SystemExit(1)
''',
            encoding='utf-8',
        )
        script.chmod(0o755)
        workbench_server.SAUPY = script
        self.assertFalse(workbench_server.publisher_ready())
        text = log.read_text(encoding='utf-8')
        self.assertEqual(Path(text.splitlines()[0]).resolve(), workbench_server.ROOT.resolve())
        self.assertIn('-I', text)
        self.assertIn(workbench_server.PUBLISHER_PROBE, text)
        self.assertNotIn(str(workbench_server.SAU), text.splitlines()[0])

    def test_real_venv_reports_ready_only_after_the_package_imports(self):
        folder = Path(self.temp.name) / 'publisher-venv'
        try:
            subprocess.run([sys.executable, '-m', 'venv', str(folder)], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            self.skipTest(exc.stderr or 'venv unavailable')
        python = folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        workbench_server.SAUPY = python
        self.assertFalse(self.client.get('/api/health').json()['publisher'])
        site = subprocess.check_output(
            [str(python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'],
            text=True,
        ).strip()
        package = Path(site) / 'sau_commands'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('', encoding='utf-8')
        dist = Path(site) / 'social_auto_upload-0.1.0.dist-info'
        dist.mkdir()
        (dist / 'METADATA').write_text(
            'Metadata-Version: 2.1\nName: social-auto-upload\nVersion: 0.1.0\n',
            encoding='utf-8',
        )
        self.assertTrue(self.client.get('/api/health').json()['publisher'])
        shutil.rmtree(package)
        shutil.rmtree(dist)
        self.assertFalse(workbench_server.publisher_ready())


class RealInterpreterTests(unittest.TestCase):
    def test_this_machine_can_build_a_publisher_venv_when_a_match_exists(self):
        spec = '>=3.10,<3.13'
        try:
            base = mod.choose_base_python(spec, feature='publish')
        except SystemExit as exc:
            self.skipTest(str(exc))
        version = mod.interpreter_version(base)
        self.assertTrue(mod.version_satisfies(version, spec))
        with tempfile.TemporaryDirectory() as temp:
            python = mod.ensure_venv(Path(temp) / '.venv', base, spec)
            created = mod.interpreter_version(python)
        self.assertTrue(mod.version_satisfies(created, spec))
        self.assertLess(created[:2], (3, 13))


if __name__ == '__main__':
    unittest.main()
