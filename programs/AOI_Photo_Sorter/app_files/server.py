# -*- coding: utf-8 -*-
"""Controller (one sorting job at a time) and the loopback HTTP server.

Photos never go through the pywebview bridge: it returns results as JSON through
ExecuteScript on the WebView2 UI thread, and a base64 photo there stalls the screen.
Instead the page and the photos come from this server, on the same origin, so
Chromium's local network access rules and CORS never apply. The server listens on
127.0.0.1 only, on a port the OS picks, every URL carries a per-run random token,
and photos are addressed by index (no file paths from the page). Standard library only.
"""
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
    def __init__(self, folder, output_dir):
        self.id = secrets.token_hex(4)
        self.folder = folder
        self.output_dir = output_dir
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

    def __init__(self, base_dir, reader=engine.read_file):
        self.base_dir = str(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self.settings = engine.Settings(os.path.join(self.base_dir, 'settings.json'))
        self._reader = reader
        self._lock = threading.RLock()
        self._job = None
        self._opened = set()
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
        return {'output_dir': cfg['output_dir'], 'recent': recent,
                'config': {key: cfg[key] for key in ('arrow_repeat', 'space_min_view_ms', 'decode_ahead', 'decode_behind')}}

    def check(self, folder, output_dir):
        folder = (folder or '').strip()
        output_dir = (output_dir or '').strip()
        folder_ok, folder_msg = engine.check_folder(folder)
        output_ok, output_msg = engine.check_writable(output_dir)
        good_name, reject_name = engine.output_names(folder) if folder else ('', '')
        existing = engine.existing_outputs(output_dir, folder) if folder and output_ok else []
        session = engine.session_summary(engine.read_session(self.base_dir, folder)) if folder_ok else None
        return {'folder_ok': folder_ok, 'folder_msg': folder_msg, 'output_ok': output_ok, 'output_msg': output_msg,
                'files': [good_name, reject_name], 'existing': existing, 'session': session}

    def start(self, folder, output_dir, resume):
        folder = (folder or '').strip()
        output_dir = (output_dir or '').strip()
        checked = self.check(folder, output_dir)
        if not checked['folder_ok'] or not checked['output_ok']:
            return {'ok': False, 'error': checked['folder_msg'] or checked['output_msg']}
        job = Job(folder, output_dir)
        with self._lock:
            if self._job is not None:
                self._job.close()
            self._job = job
        self.settings.remember(folder, output_dir)
        self._allow_open(folder, output_dir)
        threading.Thread(target=self._prepare, args=(job, bool(resume)), name='folder-scan', daemon=True).start()
        return {'ok': True, 'job': job.id}

    def _prepare(self, job, resume):
        try:
            names, sizes = engine.scan(job.folder, progress=lambda n: setattr(job, 'found', n), cancel=job.cancel)
            if job.cancel.is_set():
                return
            if not names:
                job.message = '사진이 없습니다 (jpg, jpeg, png, bmp, tif).'
                job.phase = 'error'
                return
            previous = engine.read_session(self.base_dir, job.folder) if resume else None
            session = engine.Session(self.base_dir, job.folder, job.output_dir, names, previous)
            cfg = self.settings.tuned()
            cache = engine.ImageCache(job.folder, names, sizes, cfg, reader=self._reader, cursor=session.cursor)
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
               'folder': job.folder, 'output_dir': job.output_dir, 'files': list(engine.output_names(job.folder))}
        if job.phase == 'ready':
            out.update(job.session.state())
            out['stats'] = job.cache.stats()
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

    def retry(self, job_id, index):
        self._current(job_id).cache.retry(index)
        return {'ok': True}

    def save(self, payload):
        job = self._current(payload.get('job'))
        output_dir = (payload.get('output_dir') or job.output_dir).strip()
        if isinstance(payload.get('good'), list):  # the page's full list is authoritative at save time
            job.session.set_good([int(i) for i in payload['good']])
        ok, message = engine.check_writable(output_dir)
        if not ok:
            return {'ok': False, 'error': message}
        try:
            result = engine.write_outputs(output_dir, job.folder, job.names, job.session.good, bool(payload.get('overwrite')))
        except OSError as exc:
            log.exception('write outputs failed')
            return {'ok': False, 'error': '결과 파일을 쓰지 못했습니다: %s' % (exc.strerror or exc)}
        if result['ok']:
            if output_dir != job.output_dir:
                job.output_dir = job.session.output_dir = output_dir
                self.settings.remember(job.folder, output_dir)
            job.session.saved = {'good': result['good_count'], 'reject': result['reject_count'],
                                 'output_dir': output_dir, 'time': time.strftime('%Y-%m-%d %H:%M')}
            try:
                job.session.save(force=True)
            except OSError:
                log.exception('session save failed')
            self._allow_open(output_dir, result['good_path'], result['reject_path'])
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
            elif len(parts) == 3 and parts[0] in ('img', 'thumb'):
                getter = controller.image if parts[0] == 'img' else controller.thumbnail
                data, mime = getter(parts[1], int(parts[2]))
                self._send(200, data, mime)
            elif parts == ['api', 'home']:
                self._json(controller.home())
            elif parts == ['api', 'state']:
                self._json(controller.state())
            else:
                self._text(404, 'not found')
        except engine.ReadError as exc:
            self._text(503, str(exc))
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
                self._json(controller.check(payload.get('folder'), payload.get('output_dir')))
            elif name == 'start':
                self._json(controller.start(payload.get('folder'), payload.get('output_dir'), payload.get('resume')))
            elif name == 'sync':
                self._json(controller.sync(payload))
            elif name == 'retry':
                self._json(controller.retry(payload.get('job'), int(payload.get('index', -1))))
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
