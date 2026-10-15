# -*- coding: utf-8 -*-
"""Portable ZIP (tools/build_portable.py, tools/build_release.py): runs without Python installed.
Offline: nothing is downloaded, the runtime and packages are small fakes.

    python -m unittest tests.test_portable -v
"""
import io
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import build_portable  # noqa: E402
import build_release  # noqa: E402

SORTER = REPO / 'programs' / 'AOI_Photo_Sorter'


def make_wheel(path, files):
    with zipfile.ZipFile(str(path), 'w') as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return path


def make_sdist(path, files):
    with tarfile.open(str(path), 'w:gz') as archive:
        for name, text in files.items():
            data = text.encode('utf-8')
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


class TargetTest(unittest.TestCase):
    def test_markers_are_evaluated_for_windows(self):
        applies = lambda line: build_portable.applies(build_portable.Requirement(line))
        self.assertTrue(applies('pythonnet; sys_platform == "win32"'))
        self.assertFalse(applies('pyobjc-core>=9.0; sys_platform == "darwin"'))
        self.assertFalse(applies('QtPy; extra == "qt"'))
        self.assertFalse(applies('importlib_resources; python_version < "3.9"'))
        self.assertTrue(applies('proxy_tools'))

    def test_sorter_is_portable_and_requirements_resolve_for_windows(self):
        data = json.loads((SORTER / 'app_files' / 'app_manifest.json').read_text(encoding='utf-8'))
        self.assertTrue(data.get('portable'))
        names = [item.name for item in build_portable.read_requirements(SORTER / 'app_files' / 'requirements.txt')
                 if build_portable.applies(item)]
        self.assertEqual(names, ['pywebview', 'pythonnet', 'Pillow'])


class UnpackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='portable_test_'))
        self.site = self.tmp / 'site-packages'

    def test_wheel_requirements_skip_other_platforms_and_extras(self):
        metadata = ('Metadata-Version: 2.1\nName: pywebview\nVersion: 6.2.1\n'
                    'Requires-Dist: pythonnet; sys_platform == "win32"\n'
                    'Requires-Dist: pyobjc-core>=9.0; sys_platform == "darwin"\n'
                    'Requires-Dist: proxy_tools\nRequires-Dist: PyQt6; extra == "qt"\n\nRequires-Dist: body text\n')
        wheel = make_wheel(self.tmp / 'pywebview-6.2.1-py3-none-any.whl',
                           {'pywebview-6.2.1.dist-info/METADATA': metadata, 'webview/__init__.py': ''})
        self.assertEqual([item.name for item in build_portable.wheel_requirements(wheel)], ['pythonnet', 'proxy_tools'])

    def test_unpack_wheel_with_data_dir(self):
        wheel = make_wheel(self.tmp / 'demo-1.0-py3-none-any.whl', {
            'demo/__init__.py': 'A = 1\n', 'demo-1.0.dist-info/METADATA': 'Name: demo\n',
            'demo-1.0.data/purelib/demo_extra.py': 'B = 2\n', 'demo-1.0.data/scripts/demo-cli': 'x'})
        build_portable.unpack_wheel(wheel, self.site)
        self.assertTrue((self.site / 'demo' / '__init__.py').is_file())
        self.assertTrue((self.site / 'demo_extra.py').is_file())
        self.assertTrue((self.site / 'demo-1.0.dist-info' / 'METADATA').is_file())
        self.assertFalse(any('scripts' in str(path) or 'demo-cli' in str(path) for path in self.site.rglob('*')))

    def test_unpack_pure_python_sdist(self):
        sdist = make_sdist(self.tmp / 'proxy_tools-0.1.0.tar.gz', {
            'proxy_tools-0.1.0/setup.py': 'raise SystemExit("never run")\n',
            'proxy_tools-0.1.0/proxy_tools/__init__.py': 'def module_property(f):\n    return f\n',
            'proxy_tools-0.1.0/proxy_tools.egg-info/top_level.txt': 'proxy_tools\n',
            'proxy_tools-0.1.0/README.rst': 'x'})
        build_portable.unpack_sdist(sdist, self.site)
        self.assertEqual(sorted(str(path.relative_to(self.site)) for path in self.site.rglob('*') if path.is_file()),
                         [str(Path('proxy_tools') / '__init__.py')])

    def test_sdist_with_c_code_or_dependencies_is_refused(self):
        compiled = make_sdist(self.tmp / 'fast-1.0.tar.gz', {
            'fast-1.0/fast/__init__.py': '', 'fast-1.0/fast/_speed.c': '',
            'fast-1.0/fast.egg-info/top_level.txt': 'fast\n'})
        with self.assertRaises(SystemExit):
            build_portable.unpack_sdist(compiled, self.site)
        needs = make_sdist(self.tmp / 'needs-1.0.tar.gz', {
            'needs-1.0/needs/__init__.py': '', 'needs-1.0/needs.egg-info/top_level.txt': 'needs\n',
            'needs-1.0/needs.egg-info/requires.txt': 'requests\n'})
        with self.assertRaises(SystemExit):
            build_portable.unpack_sdist(needs, self.site)

    def test_unpack_python_keeps_interpreter_and_drops_build_files(self):
        nupkg = make_wheel(self.tmp / 'python.nupkg', {
            'python.nuspec': '', 'tools/python.exe': 'x', 'tools/pythonw.exe': 'x', 'tools/python312.dll': 'x',
            'tools/Lib/os.py': '', 'tools/Lib/site-packages/pip/__init__.py': '', 'tools/include/Python.h': '',
            'tools/libs/python312.lib': '', 'tools/Lib/ensurepip/__init__.py': '', 'tools/DLLs/_ctypes.pyd': 'x'})
        runtime = self.tmp / 'runtime'
        build_portable.unpack_python(nupkg, runtime)
        files = sorted(str(path.relative_to(runtime)).replace('\\', '/') for path in runtime.rglob('*') if path.is_file())
        self.assertEqual(files, ['DLLs/_ctypes.pyd', 'Lib/os.py', 'python.exe', 'python312.dll', 'pythonw.exe'])


class ReleaseZipTest(unittest.TestCase):
    def test_portable_launcher_only_starts_the_bundled_python(self):
        data = json.loads((SORTER / 'app_files' / 'app_manifest.json').read_text(encoding='utf-8'))
        text = (SORTER / (data['release'] + '.vbs')).read_bytes().decode('cp949')
        self.assertIn('runtime\\pythonw.exe', text)
        self.assertIn('""" -E -s """', text)
        # nothing that installs, downloads or reads the registry (what antivirus heuristics look for)
        for word in ('winget', 'winmgmts', 'http', 'setup_env', 'Download', 'RegRead', 'DeleteFile'):
            self.assertNotIn(word, text)
        self.assertEqual(text, build_release.PORTABLE_TEMPLATE.read_text(encoding='utf-8').replace(
            '{{APP_ID}}', data['app_id']).replace('{{TITLE}}', data['title']).replace('\n', '\r\n'))

    def test_release_zip_carries_the_runtime(self):
        tmp = Path(tempfile.mkdtemp(prefix='portable_zip_'))
        fake = tmp / 'runtime'
        (fake / 'Lib' / 'site-packages' / 'webview').mkdir(parents=True)
        for name in ('pythonw.exe', 'python.exe', 'Lib/site-packages/webview/__init__.py'):
            (fake / name).write_text('x', encoding='utf-8')
        with mock.patch.object(build_release, 'REPO', tmp), \
                mock.patch.object(build_portable, 'build_runtime', return_value=fake) as built:
            target = build_release.build_zip(SORTER)
        built.assert_called_once()
        release = json.loads((SORTER / 'app_files' / 'app_manifest.json').read_text(encoding='utf-8'))['release']
        names = zipfile.ZipFile(str(target)).namelist()
        for name in ('runtime/pythonw.exe', 'runtime/Lib/site-packages/webview/__init__.py',
                     'app_files/app.py', release + '.vbs'):
            self.assertIn(release + '/' + name, names)


if __name__ == '__main__':
    unittest.main()
