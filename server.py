"""Run with python3 server.py. No Python packages or API keys required."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import socket
import subprocess
import threading
from urllib.parse import urlsplit

from document import document
from extractor import extract
from retrieval import ExtractionError

ROOT = Path(__file__).parent
ACTIVE = threading.BoundedSemaphore(2)
FILES = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, body, kind='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def local_request(self):
        host = self.headers.get('Host', '')
        try:
            address = urlsplit('http://' + host)
            # Codex forwards the local preview through a changing localhost port.
            valid = (address.hostname in {'127.0.0.1', 'localhost'}
                     and address.port is not None and 0 < address.port < 65536
                     and host == f'{address.hostname}:{address.port}')
        except ValueError:
            return False
        return valid and self.headers.get('Origin', 'http://' + host) == 'http://' + host

    def do_GET(self):
        if not self.local_request():
            return self.respond(403, {'error': 'Local requests only.'})
        if self.path == '/api/health':
            return self.respond(200, {'status': 'ok'})
        if self.path not in FILES:
            return self.respond(404, {'error': 'Not found.'})
        name, kind = FILES[self.path]
        self.respond(200, (ROOT / 'static' / name).read_bytes(), kind)

    def do_POST(self):
        if not self.local_request():
            return self.respond(403, {'error': 'Local requests only.'})
        if self.path != '/api/extract':
            return self.respond(404, {'error': 'Not found.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond(415, {'error': 'Send application/json.'})
        if not ACTIVE.acquire(blocking=False):
            return self.respond(429, {'error': 'Two extractions are already running. Try again shortly.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192:
                return self.respond(413, {'error': 'Request must be between 1 and 8192 bytes.'})
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError('Expected a JSON object.')
            documents = request.get('process_documents', True)
            if not isinstance(documents, bool):
                raise ValueError('process_documents must be a boolean.')
            render_browser = request.get('render_browser', True)
            if not isinstance(render_browser, bool):
                raise ValueError('render_browser must be a boolean.')
            result = extract(request.get('url'), request.get('mode', 'live'), documents, render_browser)
            self.respond(200, {'result': result, 'document': document(result)})
        except ExtractionError as exc:
            self.respond(422, {'error': str(exc), 'status': exc.status})
        except (ValueError, TypeError) as exc:
            self.respond(400, {'error': str(exc), 'status': 'invalid_request'})
        except (OSError, socket.timeout, subprocess.TimeoutExpired):
            self.respond(502, {'error': 'Source retrieval or processing failed or timed out. No content was inferred.', 'status': 'extraction_failed'})
        except Exception:
            logging.exception('Unexpected extraction error')
            self.respond(500, {'error': 'An internal extraction error occurred. Check the server terminal for details.', 'status': 'extraction_failed'})
        finally:
            ACTIVE.release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4177)
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        if exc.errno == 98:
            parser.exit(1, f'Port {args.port} is already in use. Open http://127.0.0.1:{args.port}, or use --port {args.port + 1}.\n')
        raise
    print(f'Assessment preview: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
