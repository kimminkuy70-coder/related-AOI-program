# -*- coding: utf-8 -*-
"""AOI Photo Sorter: engine, cache, session, outputs and the loopback server.

    AOI_TOOLS_HOME=/tmp/aoi_test python -m unittest tests.test_photo_sorter -v
"""
import http.client
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP_DIR = REPO / 'programs' / 'AOI_Photo_Sorter' / 'app_files'
os.environ.setdefault('AOI_TOOLS_HOME', tempfile.mkdtemp(prefix='aoi_tools_test_'))


def load_modules():
    """engine/server/app of the Photo Sorter as fresh modules (other programs use the same names)."""
    for name in ('app', 'engine', 'server', 'runtime'):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(APP_DIR))
    try:
        return types.SimpleNamespace(engine=importlib.import_module('engine'), server=importlib.import_module('server'),
                                     app=importlib.import_module('app'))
    finally:
        sys.path.remove(str(APP_DIR))
        for name in ('app', 'engine', 'server', 'runtime'):
            sys.modules.pop(name, None)


M = load_modules()
engine, server = M.engine, M.server


def cfg(**overrides):
    data = dict(engine.DEFAULT_SETTINGS)
    data.update(retry_delays=[0.01, 0.01])
    data.update(overrides)
    return data


class FakeReader:
    """Network share stand-in: per-file latency, optional bandwidth, failures, call log."""

    def __init__(self, latency=0.0, bandwidth=None, fail=()):
        self.latency, self.bandwidth, self.fail = latency, bandwidth, set(fail)
        self.calls, self.lock = [], threading.Lock()
        self.active = self.peak = 0

    def __call__(self, path):
        name = os.path.basename(path)
        with self.lock:
            self.calls.append(name)
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.latency)
            if name in self.fail:
                raise OSError(5, 'Access is denied')
            data = ('photo:' + name).encode() * 10
            if self.bandwidth:
                time.sleep(len(data) / self.bandwidth)
            return data
        finally:
            with self.lock:
                self.active -= 1


class Share(FakeReader):
    """FakeReader whose whole folder can go away: reads and the folder probe both fail."""
    online = True

    def __call__(self, path):
        if not self.online:
            raise OSError(64, 'The specified network name is no longer available')
        return super().__call__(path)

    def probe(self):
        if not self.online:
            raise OSError(64, 'The specified network name is no longer available')


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_filters_and_explorer_order(self):
        for name in ('IMG_10.jpg', 'IMG_2.jpg', 'img_1.JPG', 'notes.txt', 'x.tif', 'B.png', 'c.bmp', 'd.jpeg', 'e.tiff'):
            Path(self.dir, name).write_bytes(b'1234')
        os.mkdir(os.path.join(self.dir, 'sub.jpg'))  # a folder named like a photo is skipped
        names, sizes = engine.scan(self.dir)
        self.assertEqual(names, ['B.png', 'c.bmp', 'd.jpeg', 'e.tiff', 'img_1.JPG', 'IMG_2.jpg', 'IMG_10.jpg', 'x.tif'])
        self.assertEqual(sizes, [4] * 8)

    def test_ten_thousand_photos(self):
        for i in range(10000):
            Path(self.dir, 'P_%d.jpg' % i).write_bytes(b'x')
        started = time.monotonic()
        seen = []
        names, _ = engine.scan(self.dir, progress=seen.append)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(len(names), 10000)
        self.assertEqual(names[:3], ['P_0.jpg', 'P_1.jpg', 'P_2.jpg'])
        self.assertEqual(names[-1], 'P_9999.jpg')
        self.assertEqual(seen[-1], 10000)


class CacheTest(unittest.TestCase):
    def make(self, n=300, sizes=None, reader=None, **overrides):
        names = ['%04d.jpg' % i for i in range(n)]
        reader = reader or FakeReader()
        # '/share' does not exist here: the folder probe says it is reachable
        cache = engine.ImageCache('/share', names, sizes or [100] * n, cfg(**overrides), reader=reader, probe=lambda: None)
        self.addCleanup(cache.close)
        return cache, reader

    def test_window_by_count_and_eviction(self):
        cache, _ = self.make(ahead_count=20, behind_count=5)
        self.assertTrue(wait_until(lambda: cache.stats()['cached'] == 21))
        cache.set_cursor(100)
        self.assertTrue(wait_until(lambda: cache.stats()['ready_ahead'] == 20 and cache.stats()['cached'] == 26))
        self.assertEqual(sorted(cache._data), list(range(95, 121)))  # 5 behind, current, 20 ahead

    def test_window_by_bytes(self):
        mb = engine.MB
        cache, _ = self.make(n=100, sizes=[mb] * 100, ahead_bytes=5 * mb, behind_bytes=2 * mb)
        cache.set_cursor(50)
        self.assertTrue(wait_until(lambda: cache.stats()['cached'] == 8))
        self.assertEqual(sorted(cache._data), list(range(48, 56)))
        self.assertLessEqual(cache.stats()['cached_bytes'], 8 * len(b'photo:0000.jpg' * 10))

    def test_nearest_first_forward_first(self):
        reader = FakeReader(latency=0.002)
        names = ['%04d.jpg' % i for i in range(100)]
        cache = engine.ImageCache('/share', names, [1] * 100, cfg(read_threads=1, ahead_count=15, behind_count=8), reader=reader, cursor=50)
        self.addCleanup(cache.close)
        self.assertTrue(wait_until(lambda: len(reader.calls) >= 24))
        order = [int(name[:4]) for name in reader.calls]
        self.assertEqual(order[:24], [50] + list(range(51, 61)) + [49, 48, 47, 46, 45] + list(range(61, 66)) + [44, 43, 42])

    def test_urgent_request_outside_window(self):
        reader = FakeReader(latency=0.02)
        cache, _ = self.make(reader=reader, read_threads=1, ahead_count=200)
        started = time.monotonic()
        data, mime = cache.get(290)
        self.assertLess(time.monotonic() - started, 0.2)  # not behind the 200 queued photos
        self.assertEqual((data[:14], mime), (b'photo:0290.jpg', 'image/jpeg'))

    def test_file_error_is_kept_until_refresh(self):
        """One unreadable file while the folder answers: a real failure of that photo."""
        reader = FakeReader(fail={'0003.jpg'})
        cache, _ = self.make(reader=reader)
        with self.assertRaises(engine.ReadError) as caught:
            cache.get(3)
        self.assertFalse(caught.exception.offline)
        self.assertEqual(cache.read_counts[3], 3)  # first try + 2 retries
        self.assertFalse(cache.stats()['offline'])
        reader.fail.clear()
        epoch = cache.stats()['epoch']
        cache.refresh()  # F5
        self.assertEqual(cache.get(3)[0][:14], b'photo:0003.jpg')
        self.assertEqual(cache.stats()['epoch'], epoch + 1)

    def test_network_outage_pauses_and_recovers_by_itself(self):
        share = Share()
        names = ['%04d.jpg' % i for i in range(300)]
        cache = engine.ImageCache('/share', names, [100] * 300, cfg(ahead_count=20, behind_count=5), reader=share,
                                  probe=share.probe, probe_interval=0.05)
        self.addCleanup(cache.close)
        self.assertTrue(wait_until(lambda: cache.stats()['ready_ahead'] == 20))
        share.online = False
        self.assertEqual(cache.get(10)[0][:14], b'photo:0010.jpg')  # still in RAM
        cache.set_cursor(100)
        self.assertTrue(wait_until(lambda: cache.stats()['offline'], 5))
        started = time.monotonic()
        with self.assertRaises(engine.ReadError) as caught:
            cache.get(100)
        self.assertTrue(caught.exception.offline)
        self.assertLess(time.monotonic() - started, 0.05)  # fails at once, no 60 s wait
        self.assertEqual(cache.stats()['errors'], 0)  # nothing is marked as a bad photo
        calls = len(share.calls)
        time.sleep(0.3)
        self.assertEqual(len(share.calls), calls)  # prefetching paused: no hammering of a dead share
        epoch = cache.stats()['epoch']
        share.online = True
        self.assertTrue(wait_until(lambda: not cache.stats()['offline'], 5))
        self.assertEqual(cache.get(100)[0][:14], b'photo:0100.jpg')
        self.assertTrue(wait_until(lambda: cache.stats()['ready_ahead'] == 20))
        self.assertGreater(cache.stats()['epoch'], epoch)

    def test_refresh_while_still_offline_goes_offline_again(self):
        share = Share()
        share.online = False
        names = ['%04d.jpg' % i for i in range(50)]
        cache = engine.ImageCache('/share', names, [100] * 50, cfg(), reader=share, probe=share.probe, probe_interval=60)
        self.addCleanup(cache.close)
        self.assertTrue(wait_until(lambda: cache.stats()['offline'], 5))
        cache.refresh()
        self.assertFalse(cache.stats()['offline'])
        self.assertTrue(wait_until(lambda: cache.stats()['offline'], 5))

    def test_stalled_read_is_reported(self):
        gate = threading.Event()
        self.addCleanup(gate.set)

        def hanging(path):
            gate.wait(10)
            return b'x'
        names = ['%04d.jpg' % i for i in range(5)]
        cache = engine.ImageCache('/share', names, [1] * 5, cfg(), reader=hanging, stall_seconds=0.1)
        self.addCleanup(cache.close)
        self.assertTrue(wait_until(lambda: cache.stats()['stalled'], 3))
        gate.set()
        self.assertTrue(wait_until(lambda: not cache.stats()['stalled'] and cache.stats()['cached'] == 5, 3))

    def test_each_photo_read_once_while_paging(self):
        cache, reader = self.make(n=400, ahead_count=50, behind_count=10)
        for i in range(400):
            cache.set_cursor(i)
            cache.get(i)
            if i % 7 == 0 and i > 2:  # step back now and then, like the ← key
                cache.get(i - 2)
        self.assertEqual(cache.read_counts, [1] * 400)

    def test_tiff_is_converted_to_png(self):
        from PIL import Image
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        Image.new('L', (40, 30), 128).save(os.path.join(folder, 'a.tif'))
        names, sizes = engine.scan(folder)
        cache = engine.ImageCache(folder, names, sizes, cfg())
        self.addCleanup(cache.close)
        data, mime = cache.get(0)
        self.assertEqual(mime, 'image/png')
        self.assertTrue(data.startswith(b'\x89PNG'))

    def test_slow_network_never_makes_the_user_wait(self):
        """25 ms per file + 20 MB/s, paging at 40 photos/s (several times a human): after
        the first photo no request may wait, and memory stays inside the window."""
        reader = FakeReader(latency=0.025, bandwidth=20 * engine.MB)
        cache, _ = self.make(n=200, reader=reader)
        waits = []
        for i in range(200):
            cache.set_cursor(i)
            started = time.monotonic()
            cache.get(i)
            waits.append(time.monotonic() - started)
            time.sleep(0.025)
        self.assertEqual([round(w, 3) for w in waits[1:] if w > 0.01], [])
        self.assertGreater(reader.peak, 4)  # reads really overlap


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.names = ['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg']

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_batches_in_order_and_roundtrip(self):
        session = engine.Session(self.base, r'\\srv\share\LOT1', 'D:\\out', self.names)
        self.assertTrue(session.apply({'seq': 1, 'good': {'1': 1, '3': 1}, 'seen': [0, 1, 2], 'cursor': 2}))
        self.assertTrue(session.apply({'seq': 2, 'good': {'3': 0}, 'seen': [3], 'cursor': 3}))
        self.assertFalse(session.apply({'seq': 2, 'good': {'0': 1}}))  # resent / stale batch
        self.assertFalse(session.apply({'seq': 1, 'good': {'3': 1}}))
        self.assertEqual(session.good, {1})
        self.assertTrue(session.save())
        self.assertFalse(session.save())  # nothing changed
        stored = engine.read_session(self.base, r'\\srv\share\LOT1')
        self.assertEqual((stored['good'], stored['seen'], stored['cursor']), (['b.jpg'], '1111', 3))
        self.assertEqual(engine.session_summary(stored)['good'], 1)
        leftovers = [p for p in Path(self.base).rglob('*') if p.suffix == '.tmp']
        self.assertEqual(leftovers, [])

    def test_concurrent_saves_keep_the_latest_state(self):
        names = ['%03d.jpg' % i for i in range(300)]
        session = engine.Session(self.base, '/race', '/out', names)
        stop = threading.Event()

        def saver():
            while not stop.is_set():
                session.save()
        threads = [threading.Thread(target=saver) for _ in range(3)]
        for t in threads:
            t.start()
        for seq in range(1, 301):
            session.apply({'seq': seq, 'good': {str(seq - 1): 1}, 'cursor': seq - 1})
        stop.set()
        for t in threads:
            t.join()
        session.save()
        stored = engine.read_session(self.base, '/race')
        self.assertEqual((len(stored['good']), stored['cursor']), (300, 299))

    def test_resume_matches_by_name(self):
        first = engine.Session(self.base, '/photos', '/out', self.names)
        first.apply({'seq': 1, 'good': {'1': 1, '2': 1}, 'seen': [0, 1, 2], 'cursor': 2})
        first.save()
        names = ['a.jpg', 'c.jpg', 'c2.jpg', 'd.jpg', 'e.jpg']  # b removed, c2/e added
        resumed = engine.Session(self.base, '/photos', '/out', names, engine.read_session(self.base, '/photos'))
        self.assertEqual(resumed.good, {1})
        self.assertEqual(bytes(resumed.seen), bytes([1, 1, 0, 0, 0]))
        self.assertEqual((resumed.cursor, resumed.added, resumed.removed), (1, 2, 1))


class OutputTest(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_full_review_rounds(self):
        """A full review: <folder>_<n>차리뷰_<date>_<time>_GOOD/REJECT.txt, UTF-8, CRLF, folder order.
        Saving the same review again rewrites its round; a new review is the next round."""
        folder = r'\\srv\aoi\LOT123'
        names = ['불량_01.jpg', 'B.png', 'C.bmp', 'D.jpg']
        first = engine.save_round(self.out, folder, names, ['C.bmp', '불량_01.jpg'])
        self.assertTrue(first['ok'])
        self.assertEqual((first['round'], first['good_count'], first['reject_count'], first['added_path']), (1, 2, 2, None))
        self.assertRegex(first['when'], r'^\d{8}_\d{4}$')
        stem = 'LOT123_1차리뷰_%s_' % first['when']
        self.assertEqual(sorted(os.listdir(self.out)), [stem + 'GOOD.txt', stem + 'REJECT.txt'])
        self.assertEqual(Path(self.out, stem + 'GOOD.txt').read_bytes(), '불량_01.jpg\r\nC.bmp\r\n'.encode('utf-8'))
        self.assertEqual(Path(self.out, stem + 'REJECT.txt').read_bytes(), b'B.png\r\nD.jpg\r\n')
        again = engine.save_round(self.out, folder, names, [], own=(1, first['when']))  # same review saved again
        self.assertEqual((again['round'], again['good_path']), (1, first['good_path']))
        self.assertEqual(Path(self.out, stem + 'GOOD.txt').read_bytes(), b'')
        second = engine.save_round(self.out, folder, names, ['B.png'])  # another full review
        self.assertEqual((second['round'], len(os.listdir(self.out))), (2, 4))
        self.assertEqual(Path(self.out, stem + 'REJECT.txt').read_bytes(), '불량_01.jpg\r\nB.png\r\nC.bmp\r\nD.jpg\r\n'.encode('utf-8'))
        latest = engine.read_results(self.out, folder)
        self.assertEqual((latest['round'], latest['good'], latest['legacy']), (2, ['B.png'], False))

    def test_folder_labels(self):
        self.assertEqual(engine.folder_label(r'\\server\share'), 'share')
        self.assertEqual(engine.folder_label('D:\\AOI\\LOT 7\\'), 'LOT 7')
        self.assertEqual(engine.folder_label('/data/a:b'), 'a_b')
        self.assertEqual(engine.round_names('/x/LOT9', 3, '20261010_1029'),
                         {'추가GOOD': 'LOT9_3차리뷰_20261010_1029_추가GOOD.txt', 'GOOD': 'LOT9_3차리뷰_20261010_1029_GOOD.txt',
                          'REJECT': 'LOT9_3차리뷰_20261010_1029_REJECT.txt'})

    def test_writable_check(self):
        self.assertEqual(engine.check_writable(self.out), (True, ''))
        self.assertEqual(os.listdir(self.out), [])
        self.assertFalse(engine.check_writable(os.path.join(self.out, 'missing'))[0])
        self.assertFalse(engine.check_writable('')[0])


class ExtraReviewTest(unittest.TestCase):
    """v4: extra GOOD review of the photos still REJECT in the previous result files."""

    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.base = tempfile.mkdtemp()
        self.folder = r'\\srv\aoi\LOT5'

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)
        shutil.rmtree(self.base, ignore_errors=True)

    def write(self, name, text, encoding='utf-8'):
        Path(self.out, name).write_bytes(text.replace('\n', '\r\n').encode(encoding))

    def test_read_results_and_plan(self):
        self.assertIsNone(engine.read_results(self.out, self.folder))
        self.write('LOT5_GOOD.txt', '\ufeffb.jpg\nD.JPG\n')  # Notepad BOM; other case on Windows only
        self.write('LOT5_REJECT.txt', 'a.jpg\nc.jpg\n불량_e.jpg\ngone.jpg\n\n', 'cp949')  # saved as ANSI
        results = engine.read_results(self.out, self.folder)  # v4 file names: read as the previous result
        self.assertEqual((results['good'], results['reject']), (['b.jpg', 'D.JPG'], ['a.jpg', 'c.jpg', '불량_e.jpg', 'gone.jpg']))
        self.assertEqual(engine.results_summary(results)['reject'], 4)
        self.assertEqual((results['round'], results['legacy']), (1, True))
        self.write('LOT5_GOOD_추가_20261010_1029.txt', 'b.jpg\n')  # one v4 extra review saved on it
        self.assertEqual(engine.read_results(self.out, self.folder)['round'], 2)
        self.assertEqual(engine.last_round(self.out, self.folder), 2)
        names = ['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg', '불량_e.jpg', 'new.jpg']
        base, targets, fresh, missing = engine.plan_extra(names, results)
        if os.name == 'nt':
            self.assertEqual(base, ['b.jpg', 'd.jpg'])
        else:
            self.assertEqual(base, ['b.jpg'])
            names.remove('d.jpg')
            base, targets, fresh, missing = engine.plan_extra(names, results)
        self.assertEqual((targets, fresh, missing), (['a.jpg', 'c.jpg', '불량_e.jpg', 'new.jpg'], ['new.jpg'], 2))

    def test_latest_round_wins(self):
        for n, when, kinds in ((1, '20261001_0900', ('GOOD', 'REJECT')), (9, '20261002_0900', ('GOOD', 'REJECT')),
                               (10, '20261003_0900', ('추가GOOD', 'GOOD', 'REJECT')), (11, '20261004_0900', ('GOOD',))):
            for kind in kinds:
                self.write('LOT5_%d차리뷰_%s_%s.txt' % (n, when, kind), '%d-%s.jpg\n' % (n, kind))
        self.write('LOT5_GOOD.txt', 'old.jpg\n')  # v4 files are ignored once rounds exist
        self.write('OTHER_12차리뷰_20261005_0900_GOOD.txt', 'x.jpg\n')  # another photo folder's result
        latest = engine.read_results(self.out, self.folder)
        self.assertEqual((latest['round'], latest['good'], latest['time']), (10, ['10-GOOD.jpg'], '2026-10-03 09:00'))
        self.assertEqual(engine.last_round(self.out, self.folder), 11)  # 11 is incomplete: not a result, but the number is taken

    def test_extra_review_writes_three_files_and_never_touches_earlier_ones(self):
        self.write('LOT5_GOOD.txt', 'b.jpg\n')  # v4 result
        self.write('LOT5_REJECT.txt', 'a.jpg\nc.jpg\nd.jpg\n')
        legacy = {n: Path(self.out, n).read_bytes() for n in os.listdir(self.out)}
        results = engine.read_results(self.out, self.folder)
        names = ['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg']
        base, targets, _, _ = engine.plan_extra(names, results)
        kw = dict(base_good=base, base_key=results['key'], min_round=results['round'] + 1)
        result = engine.save_round(self.out, self.folder, names, ['d.jpg'], **kw)
        self.assertTrue(result['ok'])
        self.assertEqual((result['round'], result['good_count'], result['reject_count'], result['added_count'], result['base_count']),
                         (2, 2, 2, 1, 1))
        stem = 'LOT5_2차리뷰_%s_' % result['when']
        self.assertEqual(Path(self.out, stem + '추가GOOD.txt').read_bytes(), b'd.jpg\r\n')
        self.assertEqual(Path(self.out, stem + 'GOOD.txt').read_bytes(), b'b.jpg\r\nd.jpg\r\n')
        self.assertEqual(Path(self.out, stem + 'REJECT.txt').read_bytes(), b'a.jpg\r\nc.jpg\r\n')
        # saved again from the review screen with another pick: the same round is rewritten
        again = engine.save_round(self.out, self.folder, names, ['a.jpg'], own=(2, result['when']), **kw)
        self.assertEqual((again['round'], again['when']), (2, result['when']))
        self.assertEqual(Path(self.out, stem + 'GOOD.txt').read_bytes(), b'a.jpg\r\nb.jpg\r\n')
        self.assertEqual(Path(self.out, stem + '추가GOOD.txt').read_bytes(), b'a.jpg\r\n')
        self.assertEqual(len(os.listdir(self.out)), 2 + 3)
        self.assertEqual({n: Path(self.out, n).read_bytes() for n in legacy}, legacy)  # v4 files untouched
        # meanwhile another PC saved round 3 (c.jpg added): nothing written unless merged
        self.write('LOT5_3차리뷰_20991231_2359_GOOD.txt', 'b.jpg\nc.jpg\n')
        self.write('LOT5_3차리뷰_20991231_2359_REJECT.txt', 'a.jpg\nd.jpg\n')
        changed = engine.save_round(self.out, self.folder, names, ['a.jpg'], own=(2, result['when']), **kw)
        self.assertEqual((changed['ok'], changed['changed'], changed['latest_round']), (False, True, 3))
        merged = engine.save_round(self.out, self.folder, names, ['a.jpg'], own=(2, result['when']), merge_newer=True, **kw)
        self.assertEqual((merged['round'], merged['merged'], merged['base']), (4, True, ['b.jpg', 'c.jpg']))
        stem4 = 'LOT5_4차리뷰_%s_' % merged['when']
        self.assertEqual(Path(self.out, stem4 + 'GOOD.txt').read_bytes(), b'a.jpg\r\nb.jpg\r\nc.jpg\r\n')
        self.assertEqual(Path(self.out, stem4 + 'REJECT.txt').read_bytes(), b'd.jpg\r\n')
        self.assertEqual(Path(self.out, stem4 + '추가GOOD.txt').read_bytes(), b'a.jpg\r\n')
        self.assertEqual(Path(self.out, stem + 'GOOD.txt').read_bytes(), b'a.jpg\r\nb.jpg\r\n')  # round 2 kept as it was

    def test_extra_session_is_separate(self):
        normal = engine.Session(self.base, '/photos', '/out', ['a.jpg', 'b.jpg'])
        normal.apply({'seq': 1, 'good': {'0': 1}, 'cursor': 1})
        normal.save()
        extra = engine.Session(self.base, '/photos', '/out', ['b.jpg'], mode='extra')
        extra.apply({'seq': 1, 'good': {'0': 1}})
        extra.save()
        self.assertEqual(engine.read_session(self.base, '/photos')['good'], ['a.jpg'])
        self.assertEqual(engine.read_session(self.base, '/photos', 'extra')['good'], ['b.jpg'])


class SettingsTest(unittest.TestCase):
    def test_bad_values_fall_back_and_recent_list(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        path = os.path.join(base, 'settings.json')
        Path(path).write_text(json.dumps({'read_threads': 'many', 'arrow_repeat': 1, 'output_dir': 'D:\\out'}), encoding='utf-8')
        settings = engine.Settings(path)
        self.assertEqual((settings['read_threads'], settings['arrow_repeat'], settings['output_dir']), (8, False, 'D:\\out'))
        for i in range(12):
            settings.remember('/p/%d' % i, '/o')
        settings.remember('/p/3', '/o2')
        again = engine.Settings(path)
        self.assertEqual(len(again['recent']), engine.RECENT_MAX)
        self.assertEqual((again['recent'][0]['folder'], again['output_dir']), ('/p/3', '/o2'))
        self.assertEqual([r['folder'] for r in again['recent']].count('/p/3'), 1)


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.photos = tempfile.mkdtemp()
        self.out = tempfile.mkdtemp()
        self.base = tempfile.mkdtemp()
        from PIL import Image
        for i in range(30):
            Image.new('RGB', (64, 48), (i * 8, 100, 50)).save(os.path.join(self.photos, 'IMG_%d.jpg' % i), quality=90)
        self.controller = server.Controller(self.base)
        self.web = server.Server(self.controller, '<html>ui</html>')

    def tearDown(self):
        self.web.close()
        self.controller.close()
        for path in (self.photos, self.out, self.base):
            shutil.rmtree(path, ignore_errors=True)

    def request(self, method, path, body=None, host=None, raw=False):
        conn = http.client.HTTPConnection('127.0.0.1', self.web.port, timeout=10)
        headers = {'Host': host or self.web.host}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        if raw:
            return response, payload
        return response.status, (json.loads(payload) if response.getheader('Content-Type', '').startswith('application/json') else payload)

    def api(self, name, body=None):
        return self.request('POST' if body is not None else 'GET', '/%s/api/%s' % (self.web.token, name), body)

    def start_job(self):
        status, result = self.api('start', {'folder': self.photos, 'output_dir': self.out, 'resume': False})
        self.assertEqual((status, result['ok']), (200, True))
        self.assertTrue(wait_until(lambda: self.api('state')[1]['phase'] == 'ready'))
        return self.api('state')[1]

    def test_token_host_and_page(self):
        self.assertEqual(self.request('GET', '/wrong/')[0], 403)
        self.assertEqual(self.request('GET', '/%s/' % self.web.token, host='evil.example:80')[0], 403)
        response, _ = self.request('GET', '/' + self.web.token, raw=True)
        self.assertEqual((response.status, response.getheader('Location')), (301, '/%s/' % self.web.token))
        self.assertEqual(self.request('GET', '/%s/' % self.web.token)[1], b'<html>ui</html>')

    def test_check_start_images_sync_save(self):
        status, checked = self.api('check', {'folder': self.photos, 'output_dir': self.out})
        self.assertEqual((checked['folder_ok'], checked['output_ok'], checked['results']), (True, True, None))
        self.assertEqual((checked['label'], checked['next_round']), (os.path.basename(self.photos), 1))
        self.assertFalse(self.api('check', {'folder': self.photos + '_nope', 'output_dir': ''})[1]['folder_ok'])

        state = self.start_job()
        job = state['job']
        self.assertEqual(state['names'][:3], ['IMG_0.jpg', 'IMG_1.jpg', 'IMG_2.jpg'])
        self.assertEqual(state['seen'], '0' * 30)

        response, body = self.request('GET', '/%s/img/%s/12' % (self.web.token, job), raw=True)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Content-Type'), 'image/jpeg')
        self.assertEqual(response.getheader('Cache-Control'), 'no-store')
        self.assertEqual(body, Path(self.photos, 'IMG_12.jpg').read_bytes())
        self.assertEqual(self.request('GET', '/%s/img/%s/99' % (self.web.token, job))[0], 404)
        self.assertEqual(self.request('GET', '/%s/img/oldjob/1' % self.web.token)[0], 404)

        status, synced = self.api('sync', {'job': job, 'seq': 1, 'cursor': 5, 'good': {'2': 1, '4': 1}, 'seen': [0, 1, 2, 3, 4, 5]})
        self.assertEqual((status, synced['seq'], synced['stats']['cursor']), (200, 1, 5))
        self.assertEqual(self.api('sync', {'job': 'oldjob', 'seq': 2})[0], 409)
        self.assertTrue(wait_until(lambda: (engine.read_session(self.base, self.photos) or {}).get('good') == ['IMG_2.jpg', 'IMG_4.jpg'], 3))

        response, thumb = self.request('GET', '/%s/thumb/%s/2' % (self.web.token, job), raw=True)
        self.assertEqual((response.status, thumb[:2]), (200, b'\xff\xd8'))

        status, saved = self.api('save', {'job': job, 'good': [2, 4, 7]})
        self.assertTrue(saved['ok'])
        label = os.path.basename(self.photos)
        self.assertEqual(os.path.basename(saved['good_path']), '%s_1차리뷰_%s_GOOD.txt' % (label, saved['when']))
        self.assertEqual(Path(saved['good_path']).read_bytes(), b'IMG_2.jpg\r\nIMG_4.jpg\r\nIMG_7.jpg\r\n')
        self.assertEqual((saved['round'], saved['reject_count'], saved['added_path']), (1, 27, None))
        self.assertNotIn('base', saved)
        self.assertTrue(self.controller.can_open(saved['good_path']))
        self.assertFalse(self.controller.can_open(os.path.join(self.photos, 'IMG_1.jpg')))
        again = self.api('save', {'job': job, 'good': [2]})[1]  # same review saved again: same round rewritten
        self.assertEqual((again['ok'], again['round'], again['good_path']), (True, 1, saved['good_path']))
        self.assertEqual(Path(saved['good_path']).read_bytes(), b'IMG_2.jpg\r\n')
        self.assertEqual(len(os.listdir(self.out)), 2)
        self.assertEqual(engine.read_session(self.base, self.photos)['saved']['good'], 1)
        checked = self.api('check', {'folder': self.photos, 'output_dir': self.out})[1]
        self.assertEqual((checked['results']['round'], checked['results']['good'], checked['next_round']), (1, 1, 2))

        home = self.api('home')[1]
        self.assertEqual((home['output_dir'], home['recent'][0]['folder'], home['recent'][0]['summary']['good']), (self.out, self.photos, 1))

    def test_resume(self):
        job = self.start_job()['job']
        self.api('sync', {'job': job, 'seq': 1, 'cursor': 9, 'good': {'3': 1}, 'seen': list(range(10))})
        self.api('new', {})
        self.assertEqual(self.api('check', {'folder': self.photos, 'output_dir': self.out})[1]['session']['seen'], 10)
        status, result = self.api('start', {'folder': self.photos, 'output_dir': self.out, 'resume': True})
        self.assertTrue(wait_until(lambda: self.api('state')[1]['phase'] == 'ready'))
        state = self.api('state')[1]
        self.assertEqual((state['good'], state['cursor'], state['seen'].count('1')), ([3], 9, 10))

    def test_extra_review(self):
        label = os.path.basename(self.photos)
        status, result = self.api('start', {'folder': self.photos, 'output_dir': self.out, 'resume': False, 'mode': 'extra'})
        self.assertFalse(result['ok'])  # no previous result yet
        job = self.start_job()['job']
        self.assertTrue(self.api('save', {'job': job, 'good': [1, 3]})[1]['ok'])
        os.remove(os.path.join(self.photos, 'IMG_29.jpg'))
        from PIL import Image
        Image.new('RGB', (64, 48)).save(os.path.join(self.photos, 'IMG_30.jpg'))
        checked = self.api('check', {'folder': self.photos, 'output_dir': self.out})[1]
        self.assertEqual((checked['results']['good'], checked['results']['reject'], checked['extra_session']), (2, 28, None))
        self.assertEqual((checked['results']['round'], checked['next_round']), (1, 2))

        self.api('start', {'folder': self.photos, 'output_dir': self.out, 'resume': True, 'mode': 'extra'})
        self.assertTrue(wait_until(lambda: self.api('state')[1]['phase'] == 'ready'))
        state = self.api('state')[1]
        job = state['job']
        self.assertEqual(state['mode'], 'extra')
        self.assertEqual(len(state['names']), 28)  # 30 - 2 GOOD - 1 removed + 1 new
        self.assertNotIn('IMG_1.jpg', state['names'])
        self.assertEqual(state['names'][state['extra']['fresh'][0]], 'IMG_30.jpg')
        self.assertEqual((state['extra']['base_good'], state['extra']['missing'], state['extra']['total']), (2, 1, 30))
        self.assertEqual((state['round'], state['extra']['results_round']), (2, 1))
        target = state['names'].index('IMG_7.jpg')
        response, body = self.request('GET', '/%s/img/%s/%d' % (self.web.token, job, target), raw=True)
        self.assertEqual(body, Path(self.photos, 'IMG_7.jpg').read_bytes())
        self.api('sync', {'job': job, 'seq': 1, 'cursor': target, 'good': {str(target): 1}, 'seen': [0, target]})
        self.api('new', {})
        self.assertEqual(engine.read_session(self.base, self.photos)['saved']['good'], 2)  # normal session untouched
        self.assertEqual(self.api('check', {'folder': self.photos, 'output_dir': self.out})[1]['extra_session']['good'], 1)

        self.api('start', {'folder': self.photos, 'output_dir': self.out, 'resume': True, 'mode': 'extra'})
        self.assertTrue(wait_until(lambda: self.api('state')[1]['phase'] == 'ready'))
        state = self.api('state')[1]
        self.assertEqual((state['good'], state['cursor']), ([target], target))
        status, saved = self.api('save', {'job': state['job'], 'good': state['good']})
        self.assertTrue(saved['ok'])
        self.assertEqual(saved['round'], 2)
        self.assertEqual(Path(saved['good_path']).read_bytes(), b'IMG_1.jpg\r\nIMG_3.jpg\r\nIMG_7.jpg\r\n')
        self.assertEqual(Path(saved['added_path']).read_bytes(), b'IMG_7.jpg\r\n')
        self.assertEqual(os.path.basename(saved['added_path']), '%s_2차리뷰_%s_추가GOOD.txt' % (label, saved['when']))
        self.assertEqual((saved['reject_count'], saved['added_count'], saved['base_count']), (27, 1, 2))
        self.assertTrue(self.controller.can_open(saved['added_path']))
        self.assertEqual(self.api('save', {'job': state['job'], 'good': state['good']})[1]['round'], 2)  # saving again: same round
        self.assertEqual(len(os.listdir(self.out)), 2 + 3)  # round 1 (2 files) + round 2 (3 files)
        checked = self.api('check', {'folder': self.photos, 'output_dir': self.out})[1]
        self.assertEqual((checked['results']['round'], checked['results']['good'], checked['extra_session']), (2, 3, None))

    def test_empty_folder(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        self.api('start', {'folder': empty, 'output_dir': self.out})
        self.assertTrue(wait_until(lambda: self.api('state')[1]['phase'] == 'error'))
        self.assertIn('사진이 없습니다', self.api('state')[1]['message'])


class StartupTest(unittest.TestCase):
    def test_no_heavy_imports_before_the_window(self):
        code = ('import sys; sys.path.insert(0, %r); import engine, server; '
                'print(sorted(m for m in ("PIL", "webview") if m in sys.modules))' % str(APP_DIR))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, '[]')

    def test_js_api_exposes_only_dialog_calls(self):
        """The bridge must expose choose_folder/open_path only and never walk window.native."""
        import webview
        from webview import util
        api = M.app.API(webview, types.SimpleNamespace(closing=False))
        walked = []

        class Native:
            def __getattr__(self, name):
                walked.append(name)
                return Native()

            def __dir__(self):
                return ['Controls', 'Parent']

        api._window = types.SimpleNamespace(native=Native())
        captured = {}

        class FakeWindow:
            _js_api = api
            _functions = {}
            _expose_lock = threading.Lock()
            events = types.SimpleNamespace(before_load=threading.Event(), _pywebviewready=threading.Event(), loaded=threading.Event())

            def run_js(self, script):
                if '"func"' in script:
                    captured['functions'] = script

        original = util.load_js_files
        util.load_js_files = lambda window, platform: ('', '%(functions)s')
        try:
            util.inject_pywebview('edgechromium', FakeWindow())
            self.assertTrue(FakeWindow.events.loaded.wait(10))
        finally:
            util.load_js_files = original
        self.assertEqual({entry['func'] for entry in json.loads(captured['functions'])}, {'choose_folder', 'open_path'})
        self.assertEqual(walked, [])

    def test_inline_ui_is_one_page(self):
        sys.path.insert(0, str(APP_DIR))
        sys.modules.pop('runtime', None)
        try:
            runtime = importlib.import_module('runtime')
            html = runtime.inline_ui(APP_DIR / 'ui')
        finally:
            sys.path.remove(str(APP_DIR))
            sys.modules.pop('runtime', None)
        self.assertIn('<style>', html)
        self.assertNotIn('src="app.js"', html)
        self.assertNotIn('location.reload()', html)


if __name__ == '__main__':
    unittest.main()
