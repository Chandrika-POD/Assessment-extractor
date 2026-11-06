"""Playwright renderer with all resource requests brokered through pinned HTTPS."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from urllib.parse import urlsplit, urljoin

from retrieval import ExtractionError, request, validate_url

ROOT = Path(__file__).parent
ASSET_CACHE = {}


def asset(url, origin):
    for _ in range(4):
        validate_url(url)
        if urlsplit(url).netloc != origin:
            raise ExtractionError('Cross-origin browser resource omitted.')
        cached = ASSET_CACHE.get(url)
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
        status, headers, body = request(url)
        if status in (301, 302, 303, 307, 308):
            location = next((v for k, v in headers.items() if k.lower() == 'location'), '')
            url = urljoin(url, location)
            continue
        if status != 200:
            raise ExtractionError(f'Resource returned HTTP {status}.')
        result = {'body': base64.b64encode(body).decode(), 'contentType': next((v for k, v in headers.items() if k.lower() == 'content-type'), 'application/octet-stream')}
        # Keep a small bounded cache of public CSS/JS, never browser state or cookies.
        if len(ASSET_CACHE) >= 100:
            ASSET_CACHE.pop(next(iter(ASSET_CACHE)))
        ASSET_CACHE[url] = (time.monotonic(), result)
        return result
    raise ExtractionError('Too many resource redirects.')


def capture(url, html):
    env = os.environ.copy()
    proc = subprocess.Popen(['node', str(ROOT / 'browser_capture.cjs')], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    messages = queue.Queue()
    def read_messages():
        for line in proc.stdout:
            messages.put(line)
        messages.put(None)
    reader = threading.Thread(target=read_messages, daemon=True)
    reader.start()
    workers = ThreadPoolExecutor(max_workers=6)
    write_lock = threading.Lock()
    deadline = time.monotonic() + 210
    count, total = 0, 0
    def respond(message, allowed):
        nonlocal total
        reply = {'id': message['id']}
        try:
            if not allowed or total > 16 * 1024 * 1024:
                raise ExtractionError('Browser resource budget reached.')
            reply.update(asset(message['url'], urlsplit(url).netloc))
            with write_lock:
                total += len(reply['body'])
        except (ExtractionError, OSError) as exc:
            reply['error'] = str(exc)
        with write_lock:
            if proc.poll() is None:
                try:
                    proc.stdin.write(json.dumps(reply) + '\n')
                    proc.stdin.flush()
                except (OSError, ValueError):
                    pass
    try:
        proc.stdin.write(json.dumps({'url': url, 'html': html}) + '\n')
        proc.stdin.flush()
        while time.monotonic() < deadline:
            try:
                line = messages.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if not line:
                break
            message = json.loads(line)
            if message['type'] == 'complete':
                return message['result']
            if message['type'] == 'error':
                raise ExtractionError(message['error'], 'browser_failed')
            if message['type'] != 'request':
                continue
            count += 1
            workers.submit(respond, message, count <= 65)
        raise ExtractionError('Browser rendering timed out or stopped. Check Node.js and Playwright installation.', 'browser_failed')
    finally:
        proc.kill() if proc.poll() is None else None
        proc.wait()
        workers.shutdown(wait=True, cancel_futures=True)
        reader.join(timeout=2)
        proc.stdin.close()
        proc.stdout.close()
