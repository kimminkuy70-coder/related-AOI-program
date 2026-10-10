# -*- coding: utf-8 -*-
"""Photo Sorter engine: folder scan, prefetching image cache, session, settings, outputs.

Only the standard library is imported at module level. Pillow is imported inside
make_thumbnail()/to_png() so the window opens without paying for it.
"""
import ctypes
import functools
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import time

IS_WIN = os.name == 'nt'
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')
CONVERT_EXTS = ('.tif', '.tiff')  # Chromium cannot show TIFF: converted to PNG on read
MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.bmp': 'image/bmp'}
MB = 1024 * 1024

DEFAULT_SETTINGS = {
    'output_dir': '',
    'recent': [],
    'read_threads': 8,
    'ahead_count': 200,
    'ahead_bytes': 384 * MB,
    'behind_count': 50,
    'behind_bytes': 128 * MB,
    'retry_delays': [0.2, 0.5, 1.0],
    'thumb_size': 192,
    'arrow_repeat': False,
    'space_min_view_ms': 120,  # Space counts only after the photo was on screen this long
    'decode_ahead': 5,
    'decode_behind': 3,
}
RECENT_MAX = 10


# ---------------------------------------------------------------- utilities

def atomic_write(path, data):
    """Write bytes through a temp file in the same folder and swap it in, so an
    interrupted write (crash, network drop) never leaves a half-written file."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', suffix='.tmp', dir=folder)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def total_memory():
    """Physical memory in bytes, 0 when unknown."""
    try:
        if IS_WIN:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
            return 0
        return os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    except (AttributeError, ValueError, OSError):
        return 0


def _natural_key(name):
    parts = [(0, int(part), '') if part.isdigit() else (1, 0, part.casefold()) for part in re.split(r'(\d+)', name) if part]
    return parts, name


def _sort_key():
    """Explorer order on Windows (StrCmpLogicalW: IMG_2 before IMG_10), a natural sort elsewhere."""
    if IS_WIN:
        try:
            compare = ctypes.windll.shlwapi.StrCmpLogicalW
            compare.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
            compare.restype = ctypes.c_int
            return functools.cmp_to_key(compare)
        except (AttributeError, OSError):
            pass
    return _natural_key


def folder_label(folder):
    """Last path component, used to name the result files (works for \\\\server\\share too)."""
    parts = [p for p in re.split(r'[\\/]+', str(folder)) if p and p != '.']
    label = parts[-1] if parts else 'photos'
    label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', label).strip(' .')
    return label or 'photos'


def output_names(folder):
    label = folder_label(folder)
    return label + '_GOOD.txt', label + '_REJECT.txt'


def existing_outputs(output_dir, folder):
    return [name for name in output_names(folder) if os.path.exists(os.path.join(output_dir, name))]


def check_folder(folder):
    if not folder:
        return False, '사진 폴더를 지정하세요.'
    if not os.path.isdir(folder):
        return False, '폴더를 찾을 수 없거나 접근할 수 없습니다.'
    return True, ''


def check_writable(output_dir):
    """Really write and delete a file: a permission problem shows up before an
    hour of work, not when the results are saved."""
    if not output_dir:
        return False, '결과 저장 위치를 지정하세요.'
    if not os.path.isdir(output_dir):
        return False, '저장 위치 폴더가 없거나 접근할 수 없습니다.'
    try:
        fd, tmp = tempfile.mkstemp(prefix='.aoi_photo_sorter_', suffix='.tmp', dir=output_dir)
        os.close(fd)
        os.unlink(tmp)
    except OSError as exc:
        return False, '저장 위치에 쓸 수 없습니다: %s' % (exc.strerror or exc)
    return True, ''


def write_outputs(output_dir, folder, names, good, overwrite=False):
    """<folder>_GOOD.txt (picked with Space) and <folder>_REJECT.txt (everything else):
    one file name per line in folder order, UTF-8, CRLF."""
    good_name, reject_name = output_names(folder)
    if not overwrite:
        existing = existing_outputs(output_dir, folder)
        if existing:
            return {'ok': False, 'conflict': existing}
    good = set(good)
    picked = [n for i, n in enumerate(names) if i in good]
    rest = [n for i, n in enumerate(names) if i not in good]
    paths = {}
    for key, name, lines in (('good', good_name, picked), ('reject', reject_name, rest)):
        path = os.path.join(output_dir, name)
        atomic_write(path, ''.join(line + '\r\n' for line in lines).encode('utf-8'))
        paths[key] = path
    return {'ok': True, 'good_path': paths['good'], 'reject_path': paths['reject'],
            'good_count': len(picked), 'reject_count': len(rest)}


# ---------------------------------------------------------------- settings

class Settings:
    def __init__(self, path):
        self.path = path
        self.data = dict(DEFAULT_SETTINGS)
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                stored = json.load(handle)
            for key, default in DEFAULT_SETTINGS.items():
                value = stored.get(key)
                if type(value) is type(default):  # a hand-edited wrong type falls back to the default
                    self.data[key] = value
        except (OSError, ValueError, AttributeError):
            pass

    def __getitem__(self, key):
        return self.data[key]

    def tuned(self):
        """Cache limits for this PC: halved on PCs with 8 GB of memory or less."""
        cfg = dict(self.data)
        memory = total_memory()
        if memory and memory <= 8 * 1024 * MB:
            for key in ('ahead_bytes', 'behind_bytes'):
                cfg[key] = cfg[key] // 2
        cfg['read_threads'] = max(2, min(16, int(cfg['read_threads'])))
        return cfg

    def remember(self, folder, output_dir):
        self.data['output_dir'] = output_dir
        key = os.path.normcase(os.path.abspath(folder))
        recent = [r for r in self.data['recent'] if isinstance(r, dict) and os.path.normcase(os.path.abspath(r.get('folder', ''))) != key]
        recent.insert(0, {'folder': folder, 'output_dir': output_dir, 'time': time.strftime('%Y-%m-%d %H:%M')})
        self.data['recent'] = recent[:RECENT_MAX]
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=1).encode('utf-8'))


# ---------------------------------------------------------------- scan

def scan(folder, progress=None, cancel=None, exts=IMAGE_EXTS):
    """Photos directly inside folder, Explorer order. One os.scandir pass: on Windows
    the size comes with the directory listing, so there is no per-file round trip."""
    found = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if cancel is not None and cancel.is_set():
                break
            if not entry.name.lower().endswith(exts):
                continue
            try:
                if not entry.is_file():
                    continue
                size = entry.stat().st_size
            except OSError:
                continue
            found.append((entry.name, size))
            if progress is not None and len(found) % 200 == 0:
                progress(len(found))
    key = _sort_key()
    found.sort(key=lambda item: key(item[0]))
    if progress is not None:
        progress(len(found))
    return [name for name, _ in found], [size for _, size in found]


# ---------------------------------------------------------------- image cache

class ReadError(Exception):
    """A photo could not be read. offline: the network folder itself is unreachable
    (the photo will be read again by itself once the connection is back)."""

    def __init__(self, message, offline=False):
        super().__init__(message)
        self.offline = offline


class _ShareReadError(ReadError):
    """Reading the file failed (not a decode problem): the folder may be gone."""


def read_file(path):
    with open(path, 'rb', buffering=0) as handle:
        return handle.read()


def to_png(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA', 'I;16'):
            image = image.convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, 'PNG', compress_level=1)
    return buffer.getvalue()


def make_thumbnail(data, size=192):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.draft('RGB', (size, size))  # JPEG: decode at 1/2..1/8 scale directly
        image.thumbnail((size, size))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', quality=80)
    return buffer.getvalue()


class ImageCache:
    """Keeps the photos around the viewing position in RAM, read ahead by a pool of threads.

    The window is the cursor, then up to ahead_count/ahead_bytes photos after it and
    behind_count/behind_bytes before it (sizes are known from the scan, so the window
    is planned before anything is read). Loads go nearest-first, forward first.
    Everything outside the window is dropped, so memory stays flat over 10,000 photos.
    A photo asked for outside the window (review screen, sub-list browsing) jumps the
    queue as "urgent".

    Network folder outages: when a read fails, the folder itself is probed. If the
    folder is unreachable the cache goes offline instead of marking photos as failed:
    prefetching pauses, requests for photos not in RAM fail at once, and a monitor
    probes the folder every probe_interval seconds. When it answers again, every
    failure is forgotten and reading resumes by itself. refresh() does the same on
    demand (F5). epoch counts these resets so the screen knows to reload failed photos.
    """
    URGENT_MAX = 16

    def __init__(self, folder, names, sizes, cfg, reader=read_file, cursor=0, probe=None,
                 probe_interval=2.0, stall_seconds=5.0):
        self._paths = [os.path.join(folder, name) for name in names]
        self._exts = [os.path.splitext(name)[1].lower() for name in names]
        self._sizes = list(sizes)
        self._n = len(names)
        self._cfg = cfg
        self._reader = reader
        self._cond = threading.Condition()
        self._data = {}
        self._errors = {}
        self._inflight = set()
        self._urgent = []
        self._cursor = max(0, min(self._n - 1, int(cursor)))  # resume: read around the old position first
        self._order = []
        self._window = set()
        self._ahead = []
        self._closed = False
        self._probe = probe or functools.partial(os.stat, folder)  # raises OSError when the folder is gone
        self._probe_interval = probe_interval
        self._stall_seconds = stall_seconds
        self._offline = False
        self._epoch = 0
        self._started = {}  # index -> start time of a read in flight (stalled share detection)
        self._stop = threading.Event()
        self.read_counts = [0] * self._n  # network reads per photo (tests: each photo read once)
        self._plan()
        self._threads = []
        for number in range(min(cfg['read_threads'], max(1, self._n))):
            thread = threading.Thread(target=self._work, name='photo-reader-%d' % number, daemon=True)
            thread.start()
            self._threads.append(thread)
        threading.Thread(target=self._watch, name='share-monitor', daemon=True).start()

    def __len__(self):
        return self._n

    # planning (call with the lock held)
    def _plan(self):
        cfg, c, n = self._cfg, self._cursor, self._n
        if not n:
            self._order, self._window, self._ahead = [], set(), []
            return
        ahead, total = [], 0
        for i in range(c + 1, min(n, c + 1 + cfg['ahead_count'])):
            total += self._sizes[i]
            if total > cfg['ahead_bytes'] and ahead:
                break
            ahead.append(i)
        behind, total = [], 0
        for i in range(c - 1, max(-1, c - 1 - cfg['behind_count']), -1):
            total += self._sizes[i]
            if total > cfg['behind_bytes'] and behind:
                break
            behind.append(i)
        order = [c] + [i for i in reversed(self._urgent) if i != c]
        order += ahead[:10] + behind[:5] + ahead[10:] + behind[5:]
        seen = set()
        self._order = [i for i in order if not (i in seen or seen.add(i))]
        self._window = seen
        self._ahead = ahead
        for i in [i for i in self._data if i not in seen]:
            del self._data[i]

    def _next(self):
        for i in self._order:
            if i not in self._data and i not in self._inflight and i not in self._errors:
                return i
        return None

    # public
    def set_cursor(self, index):
        with self._cond:
            index = max(0, min(self._n - 1, int(index)))
            if index == self._cursor:
                return
            self._cursor = index
            self._plan()
            self._cond.notify_all()

    def get(self, index, timeout=60.0):
        """(bytes, mime) of one photo, waiting for it if needed. Raises ReadError."""
        if not 0 <= index < self._n:
            raise IndexError(index)
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                if index in self._data:
                    return self._data[index]
                if index in self._errors:
                    raise ReadError(self._errors[index])
                if self._closed:
                    raise ReadError('작업이 종료되었습니다.')
                if self._offline:  # do not keep the screen waiting on a dead share
                    raise ReadError('네트워크 폴더 연결이 끊겼습니다.', offline=True)
                if index not in self._window:
                    if index in self._urgent:
                        self._urgent.remove(index)
                    self._urgent.append(index)
                    del self._urgent[:-self.URGENT_MAX]
                    self._plan()
                    self._cond.notify_all()
                remain = deadline - time.monotonic()
                if remain <= 0:
                    raise ReadError('읽기 시간 초과')
                self._cond.wait(remain)

    def peek(self, index):
        with self._cond:
            return self._data.get(index)

    def refresh(self):
        """F5: forget every failure and the offline state, read again now."""
        with self._cond:
            self._offline = False
            self._reset()

    def stats(self):
        with self._cond:
            ready = 0
            for i in self._ahead:
                if i not in self._data:
                    break
                ready += 1
            oldest = min(self._started.values(), default=None)
            return {'cursor': self._cursor, 'ready_ahead': ready, 'ahead_target': len(self._ahead),
                    'cached': len(self._data), 'cached_bytes': sum(len(v[0]) for v in self._data.values()),
                    'errors': len(self._errors), 'offline': self._offline, 'epoch': self._epoch,
                    'stalled': oldest is not None and time.monotonic() - oldest > self._stall_seconds}

    def close(self):
        self._stop.set()
        with self._cond:
            self._closed = True
            self._data.clear()
            self._cond.notify_all()

    # network folder state
    def _reset(self):  # lock held
        self._errors.clear()
        self._epoch += 1
        self._cond.notify_all()

    def _share_ok(self):
        try:
            self._probe()
            return True
        except OSError:
            return False

    def _watch(self):
        while not self._stop.wait(self._probe_interval):
            if self._offline and self._share_ok():
                with self._cond:
                    if self._offline:
                        self._offline = False
                        self._reset()

    # workers
    def _load(self, index):
        path, delays = self._paths[index], [0] + list(self._cfg['retry_delays'])
        last = None
        for delay in delays:
            if delay:
                time.sleep(delay)
            if self._closed:
                raise ReadError('작업이 종료되었습니다.')
            try:
                self.read_counts[index] += 1
                data = self._reader(path)
                break
            except OSError as exc:
                last = exc
        else:
            raise _ShareReadError('읽기 실패: %s' % (getattr(last, 'strerror', None) or last))
        ext = self._exts[index]
        if ext in CONVERT_EXTS:
            try:
                return to_png(data), 'image/png'
            except Exception as exc:
                raise ReadError('TIFF 변환 실패: %s' % exc)
        return data, MIME.get(ext, 'application/octet-stream')

    def _work(self):
        while True:
            with self._cond:
                while not self._closed and (self._offline or self._next() is None):
                    self._cond.wait()
                if self._closed:
                    return
                index = self._next()
                self._inflight.add(index)
                self._started[index] = time.monotonic()
            offline = False
            try:
                result, error = self._load(index), None
            except _ShareReadError as exc:
                result, error = None, str(exc)
                offline = not self._share_ok()  # the whole folder gone, or only this file?
            except ReadError as exc:
                result, error = None, str(exc)
            except Exception as exc:  # never let a worker die
                result, error = None, '읽기 실패: %s' % exc
            with self._cond:
                self._inflight.discard(index)
                self._started.pop(index, None)
                if self._closed:
                    pass
                elif offline:
                    self._offline = True  # not a failure of this photo: read again after reconnect
                elif error is not None:
                    self._errors[index] = error
                elif index in self._window:
                    self._data[index] = result
                self._cond.notify_all()


class Thumbnails:
    """Small JPEGs of the GOOD photos for the review screen. Made from the bytes
    already in RAM when a photo is picked, so the network is not read again."""

    def __init__(self, cache, size=192):
        self._cache = cache
        self._size = size
        self._thumbs = {}
        self._lock = threading.Lock()
        self._queue = []
        self._wake = threading.Condition(self._lock)
        self._closed = False
        self._thread = threading.Thread(target=self._work, name='thumbnails', daemon=True)
        self._thread.start()

    def want(self, index):
        with self._lock:
            if index not in self._thumbs and index not in self._queue:
                self._queue.append(index)
                self._wake.notify()

    def get(self, index):
        with self._lock:
            if index in self._thumbs:
                return self._thumbs[index]
        data, _ = self._cache.get(index)
        thumb = make_thumbnail(data, self._size)
        with self._lock:
            self._thumbs[index] = thumb
        return thumb

    def close(self):
        with self._lock:
            self._closed = True
            self._thumbs.clear()
            self._wake.notify()

    def _work(self):
        while True:
            with self._lock:
                while not self._closed and not self._queue:
                    self._wake.wait()
                if self._closed:
                    return
                index = self._queue.pop(0)
                if index in self._thumbs:
                    continue
            cached = self._cache.peek(index)
            if cached is None:
                continue  # made on demand by get() when the review screen asks
            try:
                thumb = make_thumbnail(cached[0], self._size)
            except Exception:
                continue
            with self._lock:
                self._thumbs[index] = thumb


# ---------------------------------------------------------------- session

def session_path(base_dir, folder):
    key = hashlib.sha1(os.path.normcase(os.path.abspath(folder)).encode('utf-8')).hexdigest()[:20]
    return os.path.join(base_dir, 'sessions', key + '.json')


def read_session(base_dir, folder):
    try:
        with open(session_path(base_dir, folder), 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) and isinstance(data.get('names'), list) else None
    except (OSError, ValueError):
        return None


def session_summary(data):
    if not data:
        return None
    names = data.get('names', [])
    return {'total': len(names), 'seen': str(data.get('seen', '')).count('1'), 'good': len(data.get('good', [])),
            'updated': data.get('updated', ''), 'saved': data.get('saved')}


class Session:
    """GOOD picks, which photos were really on screen ("seen") and the position.
    Saved atomically (temp file + replace) by the controller about once a second."""

    def __init__(self, base_dir, folder, output_dir, names, previous=None):
        self.path = session_path(base_dir, folder)
        self.folder = folder
        self.output_dir = output_dir
        self.names = names
        self.good = set()
        self.seen = bytearray(len(names))
        self.cursor = 0
        self.seq = 0
        self.saved = None
        self.added = self.removed = 0
        self._lock = threading.Lock()
        self._write = threading.Lock()  # one writer at a time: an older snapshot never lands last
        self.dirty = True
        if previous:
            self._restore(previous)

    def _restore(self, previous):
        """Match by file name: photos added since then start unseen, removed ones are dropped."""
        index = {name: i for i, name in enumerate(self.names)}
        old_names = previous.get('names', [])
        old_seen = str(previous.get('seen', ''))
        for name in previous.get('good', []):
            if name in index:
                self.good.add(index[name])
        for pos, name in enumerate(old_names):
            if pos < len(old_seen) and old_seen[pos] == '1' and name in index:
                self.seen[index[name]] = 1
        old = set(old_names)
        self.removed = len(old - set(index))
        self.added = len([n for n in self.names if n not in old])
        cursor_name = old_names[previous.get('cursor', 0)] if 0 <= previous.get('cursor', 0) < len(old_names) else None
        self.cursor = index.get(cursor_name, 0)
        self.saved = previous.get('saved')

    def apply(self, payload):
        """One batch from the screen. seq orders the batches: a stale or repeated one is ignored."""
        with self._lock:
            seq = int(payload.get('seq', 0))
            if seq <= self.seq:
                return False
            self.seq = seq
            n = len(self.names)
            for key, value in (payload.get('good') or {}).items():
                i = int(key)
                if 0 <= i < n:
                    (self.good.add if value else self.good.discard)(i)
            for i in payload.get('seen') or []:
                if 0 <= int(i) < n:
                    self.seen[int(i)] = 1
            if 'cursor' in payload and 0 <= int(payload['cursor']) < max(1, n):
                self.cursor = int(payload['cursor'])
            self.dirty = True
            return True

    def set_good(self, indices):
        with self._lock:
            self.good = set(i for i in indices if 0 <= i < len(self.names))
            self.dirty = True

    def state(self):
        with self._lock:
            return {'names': self.names, 'good': sorted(self.good), 'seen': ''.join('1' if s else '0' for s in self.seen),
                    'cursor': self.cursor, 'seq': self.seq, 'added': self.added, 'removed': self.removed,
                    'saved': self.saved}

    def save(self, force=False):
        with self._write:
            with self._lock:
                if not self.dirty and not force:
                    return False
                data = {'version': 1, 'folder': self.folder, 'output_dir': self.output_dir, 'names': self.names,
                        'good': [self.names[i] for i in sorted(self.good)],
                        'seen': ''.join('1' if s else '0' for s in self.seen),
                        'cursor': self.cursor, 'saved': self.saved, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
                self.dirty = False
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            try:
                atomic_write(self.path, json.dumps(data, ensure_ascii=False).encode('utf-8'))
            except OSError:
                with self._lock:
                    self.dirty = True
                raise
            return True
