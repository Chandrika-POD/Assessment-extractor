"""Bounded HTTPS retrieval with exact-host policy and pinned public DNS addresses."""
import http.client
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).parent
AGENT = 'AssessmentPreview/1.0'
MAX_BYTES = 3 * 1024 * 1024
LOCK = threading.Lock()
LAST = {}


class ExtractionError(ValueError):
    def __init__(self, message, status='unavailable'):
        super().__init__(message)
        self.status = status


def validate_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ExtractionError('Enter a valid public HTTPS URL.', 'invalid_url')
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
            raise ValueError()
        host = p.hostname.encode('idna').decode('ascii').lower()
        if '.' not in host or host.endswith('.'):
            raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError()
        except ValueError:
            # A literal IP, including a private one, is never accepted.
            if ':' in host or host.replace('.', '').isdigit():
                raise ValueError()
        if host.endswith(('.local', '.localhost', '.internal')):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ExtractionError('Use a public HTTPS hostname on port 443, without credentials.', 'invalid_url')
    return p


def permission(url):
    host = validate_url(url).hostname.lower()
    policy = json.loads((ROOT / 'policies.json').read_text())['sources'].get(host, {})
    if not all(policy.get(k) for k in ('allow_fetch', 'allow_reproduce', 'access_evidence', 'reproduction_evidence')):
        raise ExtractionError('This source needs collection and reproduction permission recorded in policies.json. No remote content was fetched.', 'restricted')
    if policy.get('allowed_paths') and urlsplit(url).path not in policy['allowed_paths']:
        raise ExtractionError('This document is outside the recorded permission scope.', 'restricted')
    return policy


class PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        answers = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not answers or any(not ipaddress.ip_address(a[4][0]).is_global for a in answers):
            raise ExtractionError('DNS resolved to a non-public address.', 'restricted')
        # Use the checked address directly: no second DNS lookup between check and connect.
        family, kind, proto, _, address = answers[0]
        sock = socket.socket(family, kind, proto)
        sock.settimeout(self.timeout)
        try:
            sock.connect(address)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def request(url):
    p = validate_url(url)
    with LOCK:
        delay = max(0, 2 - (time.monotonic() - LAST.get(p.hostname, 0)))
        time.sleep(delay)
        LAST[p.hostname] = time.monotonic()
    conn = PinnedHTTPS(p.hostname, timeout=15, context=ssl.create_default_context())
    try:
        conn.request('GET', (p.path or '/') + ('?' + p.query if p.query else ''), headers={
            'User-Agent': AGENT, 'Accept': 'text/html,application/pdf,text/plain', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        content = response.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ExtractionError('Source exceeds the 3 MB prototype limit.')
        return response.status, dict(response.getheaders()), content
    finally:
        conn.close()


def robots_allowed(url):
    p = validate_url(url)
    status, headers, body = request(f'https://{p.hostname}/robots.txt')
    if status == 404:
        return
    if status != 200:
        raise ExtractionError('Robots rules could not be verified; retrieval stopped.', 'restricted')
    if 'text/html' in next((v for k, v in headers.items() if k.lower() == 'content-type'), ''):
        # Some sites return a clearly labelled not-found page with HTTP 200.
        import re
        if re.search(rb'<meta\s+name="dcterms.subject"\s+content="Page Not Found - 404 Error"', body, re.I):
            return
        raise ExtractionError('Robots endpoint returned HTML rather than rules.', 'restricted')
    robot = RobotFileParser()
    robot.parse(body.decode('utf-8', errors='replace').splitlines())
    if not robot.can_fetch(AGENT, url):
        raise ExtractionError('robots.txt disallows this URL.', 'restricted')
    delay = robot.crawl_delay(AGENT) or 0
    rate = robot.request_rate(AGENT)
    if rate:
        delay = max(delay, rate.seconds / rate.requests)
    if delay > 30:
        raise ExtractionError('Source crawl delay exceeds the prototype time budget.', 'restricted')
    if delay:
        time.sleep(delay)


def fetch(url, require_permission=True):
    for _ in range(5):
        if require_permission:
            permission(url)
        else:
            validate_url(url)
        robots_allowed(url)
        status, headers, body = request(url)
        if status in (301, 302, 303, 307, 308):
            location = next((v for k, v in headers.items() if k.lower() == 'location'), None)
            if not location:
                raise ExtractionError('Redirect has no destination.')
            url = urljoin(url, location)
            continue
        if status != 200:
            raise ExtractionError(f'Source returned HTTP {status}; no access restriction was bypassed.',
                                  'restricted' if status in (401, 403, 429) else 'unavailable')
        kind = next((v for k, v in headers.items() if k.lower() == 'content-type'), '')
        return url, kind, body
    raise ExtractionError('Too many redirects.')


def public_fetch(url):
    """User-submitted public source; rights metadata is separate from HTTP access."""
    return fetch(url, require_permission=False)
