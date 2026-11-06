import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from document import document
from extractor import GAD_URL, PageParser, extract, live, pdf_text
from retrieval import ExtractionError, PinnedHTTPS, fetch, permission, validate_url
from server import Handler


class ExtractionTests(unittest.TestCase):
    def test_local_preview_forwarding_and_origin_checks(self):
        for host, origin, expected in [('localhost:61036', 'http://localhost:61036', True),
                ('127.0.0.1:4177', None, True), ('localhost:61036', 'https://evil.example', False),
                ('evil.example:4177', None, False), ('evil@localhost:4177', None, False),
                ('localhost:4177/path', None, False), ('localhost:999999', None, False)]:
            headers = {'Host': host}
            if origin:
                headers['Origin'] = origin
            self.assertEqual(Handler.local_request(SimpleNamespace(headers=headers)), expected)

    def test_gad_url_uses_retained_publisher_source_without_network(self):
        with patch('extractor.fetch', side_effect=AssertionError('No network expected')):
            data = extract(GAD_URL, 'demo')
        self.assertEqual(len(data['questionnaire']), 7)
        self.assertEqual(data['scoring']['range'], [0, 21])
        self.assertEqual(data['mode'], 'retained_publisher_source')
        self.assertIsNone(data['scoring']['missing_answers'])
        self.assertIn('assessment.psychometrics', data['missing_fields'])
        self.assertTrue(all(q['source']['url'].startswith('https://www.phqscreeners.com/') for q in data['questionnaire']))
        json.dumps(data, allow_nan=False)

    def test_other_retained_instrument_is_not_gad_hardcoded(self):
        records = json.loads(Path('data/instruments.json').read_text())
        phq = next(r for r in records if r['assessment_id'] == 'PHQ-9')
        data = extract(phq['questions'][0]['source']['url'], 'demo')
        self.assertEqual(data['assessment']['abbreviation'], 'PHQ-9')
        self.assertEqual(len(data['questionnaire']), 9)

    def test_url_matching_does_not_match_impostor_host(self):
        with self.assertRaises(ExtractionError) as error:
            extract(GAD_URL.replace('novopsych.com', 'novopsych.com.example.org'), 'demo')
        self.assertEqual(error.exception.status, 'unavailable')

    def test_bad_urls(self):
        for url in [None, 8, 'file:///etc/passwd', 'http://example.com', 'https://127.0.0.1',
                    'https://169.254.169.254/', 'https://user:pass@example.com', 'https://example.com:80',
                    'https://foo.local', 'https://[::1]', 'https://example.com\n/x', 'https://example.com.']:
            with self.subTest(url=url), self.assertRaises(ExtractionError):
                validate_url(url)

    def test_public_source_does_not_require_permission_record(self):
        url = 'https://example.org/another-assessment'
        page = b'<main><h1>New assessment</h1><p>A public description of an unfamiliar assessment instrument.</p></main>'
        with patch('extractor.fetch', return_value=(url, 'text/html', page)):
            data = extract(url, render_browser=False)
        self.assertEqual(data['mode'], 'live_source')
        self.assertEqual(data['permission']['reproduction_permission'], 'not_verified')

    def test_live_gad_mode_does_not_claim_snapshot_is_fresh(self):
        with patch('extractor.fetch', side_effect=ExtractionError('HTTP 403', 'restricted')):
            with self.assertRaises(ExtractionError) as error:
                extract(GAD_URL, 'live')
        self.assertEqual(error.exception.status, 'restricted')

    def test_parser_excludes_hidden_scripts_and_navigation(self):
        parser = PageParser()
        parser.feed('<head><title>Example</title></head><nav>skip navigation</nav><main><h1>Example scale</h1><p>Visible</p><p hidden>secret</p><script>alert(1)</script><ol><li>Question one?</li><li>Question two?</li></ol></main>')
        parser.flush()
        text = '\n'.join(v for _, v in parser.blocks)
        self.assertNotIn('secret', text)
        self.assertNotIn('alert', text)
        self.assertNotIn('navigation', text)
        self.assertIn('Question one?', text)

    def test_generic_live_path_preserves_text_and_marks_candidates(self):
        page = b'<main><h1>Example instrument</h1><h2>Instructions</h2><p>Answer all the following questions about the past week.</p><ol><li>First question?</li><li>Second question?</li></ol><a href="/form.pdf">Form</a></main>'
        with patch('extractor.fetch', return_value=('https://example.org/scale', 'text/html', page)), patch('extractor.permission', return_value={'allow_reproduce': True}):
            data = live('https://example.org/scale', process_documents=False, render_browser=False)
        self.assertEqual(data['assessment']['name'], 'Example instrument')
        self.assertEqual(len(data['question_candidates']), 2)
        self.assertEqual(data['questionnaire'], [])
        self.assertEqual(data['documents'][0]['url'], 'https://example.org/form.pdf')
        self.assertIsNone(data['assessment']['psychometrics'])

    def test_restricted_redirect_is_checked_again(self):
        def approved(url):
            if 'internal' in url:
                raise ExtractionError('Blocked redirect', 'restricted')
        with patch('retrieval.permission', side_effect=approved), patch('retrieval.robots_allowed'), patch('retrieval.request', return_value=(302, {'Location': 'https://internal.local/'}, b'')) as request:
            with self.assertRaises(ExtractionError):
                fetch('https://example.org/')
        self.assertEqual(request.call_count, 1)

    def test_private_dns_is_blocked_before_connect(self):
        with patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(ExtractionError):
                PinnedHTTPS('example.org').connect()

    def test_document_escapes_source_markup(self):
        data = extract(GAD_URL, 'demo')
        data['assessment']['name'] = '<script>alert(1)</script>'
        result = document(data)
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;', result)
        self.assertIn('Partial coverage', result)
        self.assertIn('Feeling nervous', result)
        self.assertIn('Sources and permissions', result)

    def test_pdf_reports_scanned_or_empty_document(self):
        with patch('extractor.shutil.which', return_value='/usr/bin/pdftotext'), patch('extractor.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b'\x0c'
            with self.assertRaises(ExtractionError) as error:
                pdf_text(b'%PDF-test')
        self.assertEqual(error.exception.status, 'ocr_required')


if __name__ == '__main__':
    unittest.main()
