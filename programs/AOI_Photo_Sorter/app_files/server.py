# -*- coding: utf-8 -*-
"""Controller (one sorting job at a time) and the loopback HTTP server.

Photos never go through the pywebview bridge: it returns results as JSON through
ExecuteScript on the WebView2 UI thread, and a base64 photo there stalls the screen.
Instead the page and the photos come from this server, on the same origin, so
Chromium's local network access rules and CORS never apply. The server listens on
127.0.0.1 only, on a port the OS picks, every URL carries a per-run random token,
and photos are addressed by index (no file paths from the page). Standard library only.
The overview of a parent folder (v8, all GOOD / REJECT results at once) works the same way:
its photo list stays here and the page asks for thumbnails by index.
"""
import collections
import http.server
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse

import engine

log = logging.getLogger(__name__)


class Job:
    def __init__(self, folder, output_dir, mode='', root=''):
        self.id = secrets.token_hex(4)
        self.folder = folder
        self.output_dir = output_dir
        self.root = root  # the parent folder it was opened through ('' = opened directly)
        self.label = engine.result_label(folder, root)  # the result files start with this
        self.mode = mode  # '' = normal sort, 'extra' = extra GOOD review of the previous REJECT photos
        self.all_names = []  # extra: the whole folder (names = the photos under review)
        self.base_good = []  # extra: GOOD in the previous result, kept as is
        self.fresh = []  # extra: indices into names of photos that came after the previous result
        self.missing = 0  # extra: names in the previous result that are no longer in the folder
        self.base_key = None  # extra: key of the result (n차리뷰) the review started from
        self.base_round = 0  # extra: that round; full review: the last round so far (0: none)
        self.own = None  # (n, when) of the round this review saved: saving again rewrites it
        self.results_time = ''
        self.phase = 'scanning'
        self.found = 0
        self.message = ''
        self.names = []
        self.cache = None
        self.thumbs = None
        self.session = None
        self.cancel = threading.Event()

    def close(self):
        self.cancel.set()
        if self.session is not None:
            try:
                self.session.save()
            except OSError:
                log.exception('session save failed')
        if self.thumbs is not None:
            self.thumbs.close()
        if self.cache is not None:
            self.cache.close()


class Controller:
    """Everything the page can do. Called from the HTTP handler threads."""

    def __init__(self, base_dir, reader=engine.read_file, probe=None, title=''):
        self.base_dir = str(base_dir)
        self.title = title
        self._probe = probe  # tests: stand-in for checking that the network folder answers
        os.makedirs(self.base_dir, exist_ok=True)
        self.settings = engine.Settings(os.path.join(self.base_dir, 'settings.json'))
        self._reader = reader
        self._lock = threading.RLock()
        self._job = None
        self._tree = None  # engine.FolderTree of the parent folder on the start screen
        self._index = (None, 0.0, {})  # (output_dir, time, engine.results_index) for the subfolder list
        self._summaries = {}  # session file -> (mtime, size, summary)
        self._opened = set()
        self._overview = None  # (id, [photo paths]) of the overview on screen
        self._othumbs = collections.OrderedDict()  # (overview id, index) -> thumbnail, most recent last
        self.closing = False
        self._stop = threading.Event()
        self._saver = threading.Thread(target=self._autosave, name='session-autosave', daemon=True)
        self._saver.start()

    # helpers
    def _current(self, job_id):
        job = self._job
        if job is None or job.id != job_id or job.phase != 'ready':
            raise LookupError('작업이 바뀌었거나 준비되지 않았습니다.')
        return job

    def _autosave(self):
        # The page batches changes every ~150 ms; the file is written at most once a second.
        while not self._stop.wait(1.0):
            job = self._job
            if job is not None and job.session is not None:
                try:
                    job.session.save()
                except OSError:
                    log.exception('session autosave failed')

    def _allow_open(self, *paths):
        with self._lock:
            self._opened.update(os.path.normcase(os.path.abspath(p)) for p in paths if p)

    def can_open(self, path):
        with self._lock:
            return bool(path) and os.path.normcase(os.path.abspath(path)) in self._opened and os.path.exists(path)

    # page API
    def home(self):
        recent = []
        for item in self.settings['recent']:
            if isinstance(item, dict) and item.get('folder'):
                summary = engine.session_summary(engine.read_session(self.base_dir, item['folder']))
                recent.append(dict(item, summary=summary))
        cfg = self.settings.data
        return {'title': self.title, 'output_dir': cfg['output_dir'], 'recent': recent,
                'config': self._config()}

    def _config(self):
        cfg = self.settings.data
        return {key: cfg[key] for key in ('arrow_repeat', 'arrow_repeat_ms', 'space_min_view_ms', 'decode_ahead', 'decode_behind',
                                          'path_panel')}

    def options(self, payload):
        """A switch on the screen (연속 넘김, 경로 패널): kept in settings.json for the next start."""
        for key, value in payload.items():
            self.settings.set_option(key, value)
        return {'ok': True, 'config': self._config()}

    def check(self, folder, output_dir, root=''):
        """folder: the photo folder to open; root: the parent folder it was picked from."""
        folder = (folder or '').strip()
        output_dir = (output_dir or '').strip()
        root = (root or '').strip()
        label = engine.result_label(folder, root) if folder else ''
        folder_ok, folder_msg = engine.check_folder(folder)
        output_ok, output_msg = engine.check_writable(output_dir)
        session = engine.session_summary(engine.read_session(self.base_dir, folder)) if folder_ok else None
        results = engine.results_summary(engine.read_results(output_dir, folder, label)) if folder and output_ok else None
        last = engine.last_round(output_dir, folder, label) if folder and output_ok else 0
        extra = self._extra_session(folder) if folder_ok and results else None
        return {'folder_ok': folder_ok, 'folder_msg': folder_msg, 'output_ok': output_ok, 'output_msg': output_msg,
                'folder': folder, 'label': label, 'next_round': last + 1, 'session': session,
                'results': results, 'extra_session': engine.session_summary(extra)}

    def tree(self, folder, output_dir, rescan=False):
        """The photo folders at and below folder (listed in the background; the page asks
        again while state is 'running'), each with its progress and latest saved round."""
        folder = (folder or '').strip()
        output_dir = (output_dir or '').strip()
        ok, message = engine.check_folder(folder)
        if not ok:
            return {'ok': False, 'error': message}
        out = self._folder_tree(folder, rescan).snapshot()
        index = self._results_index(output_dir, fresh=rescan)
        for entry in out['entries']:
            entry['label'] = engine.result_label(entry['path'], folder)
            entry['results'] = index.get(entry['label'].casefold())
            entry['session'] = self._summary(entry['path'])
            extra = self._summary(entry['path'], 'extra')
            entry['extra_session'] = extra if extra and not extra.get('saved') else None
        out.update(ok=True, root=folder)
        return out

    def _folder_tree(self, folder, rescan=False):
        with self._lock:
            tree = self._tree
            if tree is None or tree.key != engine.path_key(folder) or rescan or tree.state in ('stopped', 'error'):
                if tree is not None:
                    tree.cancel()
                tree = self._tree = engine.FolderTree(folder)
            return tree

    def overview(self, folder, output_dir, rescan=False):
        """Every result under a parent folder at once (v8): the latest saved round of each
        photo folder in its list, with the names of its GOOD and REJECT photos. Folders not
        saved yet are listed without photos. The page asks again while state is 'running'
        (the folder list is still being found). Photos are then asked for by their index in
        the order of the folders, GOOD before REJECT within a folder."""
        folder = (folder or '').strip()
        output_dir = (output_dir or '').strip()
        ok, message = engine.check_folder(folder)
        if not ok:
            return {'ok': False, 'error': message}
        if not output_dir or not os.path.isdir(output_dir):
            return {'ok': False, 'error': '결과 저장 위치 폴더가 없거나 접근할 수 없습니다.'}
        tree = self._folder_tree(folder, rescan)
        snap = tree.snapshot()
        if snap['state'] == 'running':
            return {'ok': True, 'state': 'running', 'listed': snap['listed'], 'found': len(snap['entries'])}
        index = engine.results_index(output_dir)
        folders, paths = [], []
        for entry in snap['entries']:
            label = engine.result_label(entry['path'], folder)
            results = engine.read_results(output_dir, entry['path'], label) if label.casefold() in index else None
            row = {'path': entry['path'], 'parts': entry['parts'], 'count': entry['count'], 'label': label,
                   'first': len(paths), 'good': [], 'reject': [], 'round': 0, 'time': '',
                   'session': self._summary(entry['path'])}
            if results:
                row.update(good=results['good'], reject=results['reject'], round=results['round'], time=results['time'])
                paths.extend(os.path.join(entry['path'], name) for name in results['good'] + results['reject'])
            folders.append(row)
        with self._lock:
            view_id = secrets.token_hex(4)
            self._overview = (view_id, paths)
            self._othumbs.clear()
        self._allow_open(output_dir)
        return {'ok': True, 'state': snap['state'], 'id': view_id, 'root': folder, 'output_dir': output_dir,
                'folders': folders, 'failed': snap['failed']}

    def _overview_path(self, view_id, index):
        with self._lock:
            view = self._overview
        if view is None or view[0] != view_id or not 0 <= index < len(view[1]):
            raise LookupError('전체 결과 목록이 바뀌었습니다.')
        return view[1][index]

    def _read_photo(self, path):
        try:
            return engine.photo_bytes(path, self._reader)
        except OSError as exc:
            raise engine.ReadError('읽기 실패: %s' % (exc.strerror or exc))
        except Exception as exc:
            raise engine.ReadError('표시할 수 없는 사진: %s' % exc)

    def overview_image(self, view_id, index):
        return self._read_photo(self._overview_path(view_id, index))

    def overview_thumbnail(self, view_id, index):
        key = (view_id, index)
        with self._lock:
            thumb = self._othumbs.get(key)
            if thumb is not None:
                self._othumbs.move_to_end(key)
                return thumb, 'image/jpeg'
        path = self._overview_path(view_id, index)
        try:
            thumb = engine.make_thumbnail(self._reader(path), self.settings['thumb_size'])
        except OSError as exc:
            raise engine.ReadError('읽기 실패: %s' % (exc.strerror or exc))
        except Exception as exc:
            raise engine.ReadError('표시할 수 없는 사진: %s' % exc)
        with self._lock:
            self._othumbs[key] = thumb
            while len(self._othumbs) > 3000:  # ~15 KB each
                self._othumbs.popitem(last=False)
        return thumb, 'image/jpeg'

    def original(self, job_id, index):
        """The photo file as it is (a photo dragged out of the window is copied from this)."""
        job = self._current(job_id)
        if not 0 <= index < len(job.names):
            raise LookupError('없는 사진입니다.')
        path = os.path.join(job.folder, job.names[index])
        try:
            data = self._reader(path)
        except OSError as exc:
            raise engine.ReadError('읽기 실패: %s' % (exc.strerror or exc))
        ext = os.path.splitext(path)[1].lower()
        return data, engine.MIME.get(ext, 'image/tiff' if ext in engine.CONVERT_EXTS else 'application/octet-stream')

    def _results_index(self, output_dir, fresh=False):
        # the list is asked for every 250 ms while folders are being found: one listing per 2 s
        with self._lock:
            cached_dir, made, index = self._index
            if not fresh and cached_dir == output_dir and time.monotonic() - made < 2.0:
                return index
        index = engine.results_index(output_dir) if output_dir and os.path.isdir(output_dir) else {}
        with self._lock:
            self._index = (output_dir, time.monotonic(), index)
        return index

    def _summary(self, folder, mode=''):
        """session_summary of a folder, parsed again only when its session file changed."""
        path = engine.session_path(self.base_dir, folder, mode)
        try:
            info = os.stat(path)
        except OSError:
            return None
        stamp = (info.st_mtime_ns, info.st_size)
        with self._lock:
            cached = self._summaries.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
        summary = engine.session_summary(engine.read_session(self.base_dir, folder, mode))
        with self._lock:
            self._summaries[path] = (stamp, summary)
        return summary

    def _extra_session(self, folder):
        """An extra review that was not saved yet (a saved one is done: the next review
        starts from the result files again)."""
        data = engine.read_session(self.base_dir, folder, 'extra')
        return data if data and not data.get('saved') else None

    def start(self, folder, output_dir, resume, mode='', root=''):
        folder = (folder or '').strip()
        output_dir = (output_dir or '').strip()
        root = (root or '').strip()
        if root and engine.relative_parts(root, folder) is None:
            root = ''
        mode = 'extra' if mode == 'extra' else ''
        checked = self.check(folder, output_dir, root)
        if not checked['folder_ok'] or not checked['output_ok']:
            return {'ok': False, 'error': checked['folder_msg'] or checked['output_msg']}
        if mode and not checked['results']:
            return {'ok': False, 'error': '저장 위치에 이 폴더의 이전 결과 파일(%s_n차리뷰_…_GOOD.txt / _REJECT.txt)이 없습니다.'
                    % checked['label']}
        job = Job(folder, output_dir, mode, root)
        with self._lock:
            if self._job is not None:
                self._job.close()
            self._job = job
            if self._tree is not None:
                self._tree.cancel()  # the photo reads come first; a cut-short list is found again later
        self.settings.remember(root or folder, output_dir)
        self._allow_open(folder, output_dir)
        threading.Thread(target=self._prepare, args=(job, bool(resume)), name='folder-scan', daemon=True).start()
        return {'ok': True, 'job': job.id}

    def _prepare(self, job, resume):
        try:
            tree = self._tree
            listed = tree.listing(job.folder) if tree is not None else None  # listed a moment ago: not again
            if listed is not None:
                names, sizes = listed
                folders = []
            else:
                names, sizes, folders = engine.list_folder(job.folder, progress=lambda n: setattr(job, 'found', n),
                                                           cancel=job.cancel)
                if tree is not None and not job.cancel.is_set():
                    tree.update(job.folder, names)
            if job.cancel.is_set():
                return
            if not names:
                job.message = '사진이 없습니다 (jpg, jpeg, png, bmp, tif).'
                if folders:
                    job.message += '\n하위 폴더가 있으면 하위 폴더 목록이 나타난 뒤 목록에서 골라 시작하세요.'
                job.phase = 'error'
                return
            if job.mode == 'extra':
                results = engine.read_results(job.output_dir, job.folder, job.label)
                if results is None:
                    raise RuntimeError('이전 결과 파일을 읽을 수 없습니다.')
                base, targets, fresh, missing = engine.plan_extra(names, results)
                if not targets:
                    job.message = '추가로 검토할 REJECT 사진이 없습니다 (폴더의 사진이 모두 이미 GOOD입니다).'
                    job.phase = 'error'
                    return
                position = {name: i for i, name in enumerate(names)}
                job.all_names, job.base_good, job.missing = names, base, missing
                job.base_key, job.base_round, job.results_time = results['key'], results['round'], results['time']
                names = targets
                sizes = [sizes[position[name]] for name in targets]
                fresh = set(fresh)
                job.fresh = [i for i, name in enumerate(targets) if name in fresh]
                previous = self._extra_session(job.folder) if resume else None
            else:
                previous = engine.read_session(self.base_dir, job.folder) if resume else None
                job.all_names = names
                job.base_round = engine.last_round(job.output_dir, job.folder, job.label)
                saved = (previous or {}).get('saved') or {}
                if (saved.get('round') and saved.get('when') and saved.get('output_dir') == job.output_dir
                        and saved.get('label', engine.folder_label(job.folder)) == job.label):
                    job.own = (saved['round'], saved['when'])  # resumed: saving again rewrites that round
            session = engine.Session(self.base_dir, job.folder, job.output_dir, names, previous, job.mode)
            cfg = self.settings.tuned()
            cache = engine.ImageCache(job.folder, names, sizes, cfg, reader=self._reader, cursor=session.cursor,
                                      probe=self._probe)
            with self._lock:
                if job.cancel.is_set():
                    cache.close()
                    return
                job.names, job.session, job.cache = names, session, cache
                job.thumbs = engine.Thumbnails(cache, cfg['thumb_size'])
                job.phase = 'ready'
        except OSError as exc:
            log.exception('scan failed')
            job.message = '폴더를 읽을 수 없습니다: %s' % (exc.strerror or exc)
            job.phase = 'error'
        except Exception as exc:
            log.exception('prepare failed')
            job.message = str(exc)
            job.phase = 'error'

    def state(self):
        job = self._job
        if job is None:
            return {'phase': 'idle'}
        out = {'phase': job.phase, 'job': job.id, 'found': job.found, 'message': job.message,
               'folder': job.folder, 'output_dir': job.output_dir, 'label': job.label,
               'root': job.root, 'parts': engine.relative_parts(job.root, job.folder) if job.root else [],
               'round': job.own[0] if job.own else job.base_round + 1}
        if job.phase == 'ready':
            out.update(job.session.state())
            out['stats'] = job.cache.stats()
            out['mode'] = job.mode
            if job.mode == 'extra':
                out['extra'] = {'base_good': len(job.base_good), 'total': len(job.all_names), 'fresh': job.fresh,
                                'missing': job.missing, 'results_time': job.results_time, 'results_round': job.base_round}
        return out

    def sync(self, payload):
        job = self._current(payload.get('job'))
        before = set(job.session.good)
        if job.session.apply(payload):
            for index in job.session.good - before:
                job.thumbs.want(index)
            if 'cursor' in payload:
                job.cache.set_cursor(int(payload['cursor']))
        return {'ok': True, 'seq': job.session.seq, 'stats': job.cache.stats()}

    def image(self, job_id, index):
        return self._current(job_id).cache.get(index)

    def thumbnail(self, job_id, index):
        return self._current(job_id).thumbs.get(index), 'image/jpeg'

    def refresh(self, job_id):
        """F5 on the screen: reconnect and read every failed photo again."""
        cache = self._current(job_id).cache
        cache.refresh()
        return {'ok': True, 'stats': cache.stats()}

    def save(self, payload):
        job = self._current(payload.get('job'))
        output_dir = (payload.get('output_dir') or job.output_dir).strip()
        if isinstance(payload.get('good'), list):  # the page's full list is authoritative at save time
            job.session.set_good([int(i) for i in payload['good']])
        ok, message = engine.check_writable(output_dir)
        if not ok:
            return {'ok': False, 'error': message}
        try:
            same_place = output_dir == job.output_dir
            picked = [job.names[i] for i in sorted(job.session.good)]
            result = engine.save_round(
                output_dir, job.folder, job.all_names, picked,
                base_good=job.base_good if job.mode == 'extra' else None,
                # the newer-result check only applies where the review's base was read
                base_key=job.base_key if same_place else None,
                own=job.own if same_place else None,
                merge_newer=bool(payload.get('overwrite')), min_round=job.base_round + 1, label=job.label)
        except OSError as exc:
            log.exception('write outputs failed')
            return {'ok': False, 'error': '결과 파일을 쓰지 못했습니다: %s' % (exc.strerror or exc)}
        if result['ok']:
            with self._lock:
                self._index = (None, 0.0, {})  # the subfolder list shows this round when the page asks next
            if output_dir != job.output_dir:
                job.output_dir = job.session.output_dir = output_dir
                self.settings.remember(job.root or job.folder, output_dir)
            job.own = (result['round'], result['when'])
            base = result.pop('base')
            if job.mode == 'extra':
                job.base_good = base  # merged with a newer result: saving again keeps that base
            job.session.saved = {'good': result['good_count'], 'reject': result['reject_count'], 'round': result['round'],
                                 'when': result['when'], 'output_dir': output_dir, 'label': job.label,
                                 'time': time.strftime('%Y-%m-%d %H:%M')}
            try:
                job.session.save(force=True)
            except OSError:
                log.exception('session save failed')
            self._allow_open(output_dir, result['good_path'], result['reject_path'], result.get('added_path'))
            result['output_dir'] = output_dir
        return result

    def new(self):
        with self._lock:
            if self._job is not None:
                self._job.close()
            self._job = None
        return {'ok': True}

    def close(self):
        if self.closing:
            return
        self.closing = True
        self._stop.set()
        with self._lock:
            if self._tree is not None:
                self._tree.cancel()
            if self._job is not None:
                self._job.close()


class _HTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        # No other socket may bind the same port and take our connections.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        # The page drops keep-alive connections all the time (paging, closing): not an error.
        # Anything else goes to the log file instead of the stderr pythonw does not have.
        if not isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            log.exception('request from %s failed', client_address)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'  # keep-alive: no new connection per photo
    server_version = 'AOIPhotoSorter'

    def log_message(self, fmt, *args):
        pass  # pythonw has no stderr; errors are logged where they happen

    GETTERS = {'img': 'image', 'thumb': 'thumbnail', 'file': 'original', 'oimg': 'overview_image',
               'othumb': 'overview_thumbnail'}

    @property
    def app(self):
        return self.server.app

    def _send(self, code, body=b'', content_type='application/json; charset=utf-8', headers=()):
        try:
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            # no-store: WebView2 must not pile gigabytes of photos into its disk cache
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the page dropped a request it no longer needs (fast paging)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _text(self, code, text):
        self._send(code, text.encode('utf-8'), 'text/plain; charset=utf-8')

    def _route(self):
        if self.headers.get('Host') != self.app.host:
            self._text(403, 'forbidden')
            return None
        parts = urllib.parse.urlsplit(self.path).path.split('/')
        if len(parts) < 2 or not secrets.compare_digest(parts[1], self.app.token):
            self._text(403, 'forbidden')
            return None
        if len(parts) == 2:  # relative URLs in the page need the trailing slash
            self._send(301, headers=(('Location', '/%s/' % self.app.token),))
            return None
        return parts[2:]

    def do_GET(self):
        parts = self._route()
        if parts is None:
            return
        controller = self.app.controller
        try:
            if parts == ['']:
                self._send(200, self.app.html, 'text/html; charset=utf-8')
            elif len(parts) == 3 and parts[0] in self.GETTERS:
                data, mime = getattr(controller, self.GETTERS[parts[0]])(parts[1], int(parts[2]))
                self._send(200, data, mime)
            elif parts == ['api', 'home']:
                self._json(controller.home())
            elif parts == ['api', 'state']:
                self._json(controller.state())
            else:
                self._text(404, 'not found')
        except engine.ReadError as exc:
            # the page tells a dead network folder (reloads by itself) from a bad file
            self._send(503, str(exc).encode('utf-8'), 'text/plain; charset=utf-8',
                       (('X-Photo-Error', 'offline' if exc.offline else 'read'),))
        except (LookupError, ValueError) as exc:
            self._text(404, str(exc))
        except Exception as exc:
            log.exception('GET %s failed', self.path)
            self._text(500, str(exc))

    def do_POST(self):
        parts = self._route()
        if parts is None:
            return
        controller = self.app.controller
        try:
            length = int(self.headers.get('Content-Length') or 0)
            payload = json.loads(self.rfile.read(length) or b'{}') if length else {}
            if not isinstance(payload, dict):
                raise ValueError('bad request')
            name = parts[1] if len(parts) == 2 and parts[0] == 'api' else ''
            if name == 'check':
                self._json(controller.check(payload.get('folder'), payload.get('output_dir'), payload.get('root')))
            elif name == 'options':
                self._json(controller.options(payload))
            elif name == 'tree':
                self._json(controller.tree(payload.get('folder'), payload.get('output_dir'), bool(payload.get('rescan'))))
            elif name == 'overview':
                self._json(controller.overview(payload.get('folder'), payload.get('output_dir'), bool(payload.get('rescan'))))
            elif name == 'start':
                self._json(controller.start(payload.get('folder'), payload.get('output_dir'), payload.get('resume'),
                                            payload.get('mode') or '', payload.get('root')))
            elif name == 'sync':
                self._json(controller.sync(payload))
            elif name == 'refresh':
                self._json(controller.refresh(payload.get('job')))
            elif name == 'save':
                self._json(controller.save(payload))
            elif name == 'new':
                self._json(controller.new())
            else:
                self._text(404, 'not found')
        except LookupError as exc:
            self._json({'ok': False, 'stale': True, 'error': str(exc)}, 409)
        except ValueError as exc:
            self._text(400, str(exc))
        except Exception as exc:
            log.exception('POST %s failed', self.path)
            self._text(500, str(exc))


class Server:
    def __init__(self, controller, html):
        self.controller = controller
        self.html = html.encode('utf-8') if isinstance(html, str) else html
        self.token = secrets.token_urlsafe(18)
        self.httpd = _HTTPServer(('127.0.0.1', 0), Handler)
        self.httpd.app = self
        self.port = self.httpd.server_address[1]
        self.host = '127.0.0.1:%d' % self.port
        self.url = 'http://%s/%s/' % (self.host, self.token)
        self._thread = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': 0.5},
                                        name='photo-server', daemon=True)
        self._thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
