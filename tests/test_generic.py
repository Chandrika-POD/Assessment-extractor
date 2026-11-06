import unittest
from unittest.mock import patch

from extractor import extract, live, GAD_URL
from retrieval import ExtractionError, permission, robots_allowed, public_fetch
from source_parser import parse_html, html_questions, pdf_questions


class GenericTests(unittest.TestCase):
    def test_browser_tab_sections_merge_without_duplicate_overview(self):
        url = 'https://example.org/scale'
        overview = '<main><h1>New scale</h1><h2>Overview</h2><p>A description with enough text for a useful source preview.</p></main>'
        scoring = overview.replace('</main>', '<h2>Scoring</h2><p>Explicit scoring text from the second tab.</p></main>')
        rendered = {'tabs': [{'title': 'Scoring', 'status': 'captured'}], 'snapshots': [{'html': overview}, {'html': scoring}]}
        with patch('extractor.fetch', return_value=(url, 'text/html', overview.encode())), patch('browser_capture.capture', return_value=rendered):
            result = live(url, process_documents=False)
        self.assertEqual(len(result['sections']), 2)
        self.assertEqual(result['scoring'][0]['title'], 'Scoring')
        self.assertEqual(result['browser']['tabs'][0]['status'], 'captured')

    def test_failed_browser_keeps_visible_html_and_reports_failure(self):
        url = 'https://example.org/scale'
        html = b'<main><h1>New scale</h1><p>A description with enough text for a useful source preview.</p></main>'
        with patch('extractor.fetch', return_value=(url, 'text/html', html)), patch('browser_capture.capture', side_effect=ExtractionError('Browser unavailable')):
            result = live(url, process_documents=False)
        self.assertEqual(result['browser']['status'], 'failed')
        self.assertTrue(result['sections'])

    def test_public_fetch_still_rejects_internal_redirect(self):
        with patch('retrieval.robots_allowed'), patch('retrieval.request', return_value=(302, {'Location': 'https://internal.local/'}, b'')) as req:
            with self.assertRaises(ExtractionError):
                public_fetch('https://example.org/scale')
        self.assertEqual(req.call_count, 1)

    def test_browser_asset_cannot_request_another_origin(self):
        from browser_capture import asset
        with patch('browser_capture.request', side_effect=AssertionError('No request expected')):
            for url in ('https://127.0.0.1/private', 'https://different.example/x.js'):
                with self.assertRaises(ExtractionError):
                    asset(url, 'example.org')

    def test_default_and_legacy_auto_never_return_saved_records(self):
        for mode in ('live', 'auto'):
            with patch('extractor.fetch', side_effect=ExtractionError('restricted', 'restricted')) as fetch:
                with self.assertRaises(ExtractionError):
                    extract(GAD_URL, mode)
                fetch.assert_called_once_with(GAD_URL)

    def test_arbitrary_instrument_table_and_empty_anchor(self):
        html = '''<title>New instrument</title><nav>Do not include me</nav>
        <a id="main-content"></a><div id="innerContentWrapper">
        <h1>A new scale</h1><h2>Questions</h2><table>
        <tr><th>Item</th><th>Question</th><th>Never</th><th>Often</th></tr>
        <tr><td>1</td><td>First unfamiliar question?</td><td>0</td><td>3</td></tr>
        <tr><td>2</td><td>Second unfamiliar question?</td><td>0</td><td>3</td></tr></table>
        <p hidden>Secret text</p><script>bad code</script></div>'''
        data = parse_html(html, 'https://example.org/new-scale')
        questions = html_questions(data)
        self.assertEqual(data['name'], 'A new scale')
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[1]['options'][1]['response_value'], 3)
        self.assertIsNone(questions[1]['options'][1]['score'])
        text = str(data['sections'])
        for excluded in ('Secret text', 'bad code', 'Do not include me'):
            self.assertNotIn(excluded, text)

    def test_question_list_does_not_turn_references_into_questions(self):
        html = '<main><h1>Test</h1><h2>Questions</h2><ol><li>How have you felt?</li></ol><h2>References</h2><ol><li>Author et al. 2020</li></ol></main>'
        items = html_questions(parse_html(html, 'https://example.org/a'))
        self.assertEqual([q['text'] for q in items], ['How have you felt?'])
        self.assertEqual(items[0]['options'], [])

    def test_pdf_preserves_wrapping_and_numbers_in_question_wording(self):
        text = ('Instructions: Choose a response.\n'
                'In the last week:                       Never     Often\n'
                '1. Over the past 3 days did you           0         2\n'
                '   feel rested?\n'
                '2. How well could you concentrate?       0         2\n'
                'Page 1 of 1\n')
        questions = pdf_questions(text, 'https://example.org/new.pdf')
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]['text'], 'Over the past 3 days did you feel rested?')
        self.assertEqual([o['label'] for o in questions[0]['options']], ['Never', 'Often'])
        self.assertIsNone(questions[0]['reverse_scored'])
        self.assertEqual(questions[0]['source']['page'], 1)

    def test_pdf_response_numbers_on_separate_line_keep_wrapped_text(self):
        text = ('Past week:                             Never     Often\n'
                '1. Did you have trouble\n'
                '                                         0         2\n'
                '   completing daily tasks?\n'
                '2. Did you sleep well?                   0         2\n')
        questions = pdf_questions(text, 'https://example.org/a.pdf')
        self.assertEqual(questions[0]['text'], 'Did you have trouble completing daily tasks?')
        self.assertEqual(len(questions[0]['options']), 2)

    def test_pdf_unpunctuated_number_and_per_item_response_labels(self):
        text = ('                                         0         2\n'
                '  1   Have you felt rested?             Never     Often\n\n\n'
                '                                         0         2\n'
                '  2   Have you felt comfortable?        Never     Often\n\n\n')
        questions = pdf_questions(text, 'https://example.org/b.pdf')
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]['text'], 'Have you felt rested?')
        self.assertEqual([o['label'] for o in questions[1]['options']], ['Never', 'Often'])

    def test_centered_item_number_keeps_wording_above_and_below(self):
        text = ('      First part of the question          0         2\n'
                '  1                                    Never     Often\n'
                '      and its continuation?\n\n\n'
                '  2\n'
                '      Another question starts below      0         2\n'
                '      its item number?                 Never     Often\n\n\n')
        questions = pdf_questions(text, 'https://example.org/centered.pdf')
        self.assertEqual([q['text'] for q in questions], [
            'First part of the question and its continuation?',
            'Another question starts below its item number?'])
        self.assertTrue(all(len(q['options']) == 2 for q in questions))

    def test_observer_report_form_is_not_treated_as_sample_report(self):
        url = 'https://example.org/scale'
        page = b'<main><h1>Observer instrument</h1><p>Download the observer questionnaire for this assessment.</p><a href="/Observer-Report-Scale.pdf">Download PDF</a></main>'
        replies = [(url, 'text/html', page), (url+'/Observer-Report-Scale.pdf', 'application/pdf', b'%PDF-test')]
        with patch('extractor.fetch', side_effect=replies), patch('extractor.pdf_text', return_value='1. First observation?\n2. Second observation?'):
            result = live(url, render_browser=False)
        self.assertEqual(len(result['questionnaire']), 2)

    def test_failed_linked_document_preserves_page_and_scoring(self):
        url = 'https://example.org/new'
        page = b'<main><h1>Example scale</h1><h2>Scoring</h2><p>These are the explicitly supplied scoring instructions.</p><a href="/scale.pdf">Questionnaire form</a></main>'
        with patch('extractor.fetch', side_effect=[(url, 'text/html', page), ExtractionError('Not approved', 'restricted')]), patch('extractor.permission', return_value={}):
            data = live(url, render_browser=False)
        self.assertEqual(data['documents'][0]['status'], 'restricted')
        self.assertIn('explicitly supplied', data['scoring'][0]['text'])
        self.assertEqual(data['questionnaire'], [])
        self.assertEqual(data['mode'], 'live_source')

    def test_different_linked_forms_are_kept_separate(self):
        url = 'https://example.org/new'
        page = b'<main><h1>Example scale</h1><p>Two different questionnaire versions are available below.</p><a href="/a.pdf">Form A</a><a href="/b.pdf">Form B</a></main>'
        replies = [(url, 'text/html', page), (url+'/a.pdf', 'application/pdf', b'%PDF-a'), (url+'/b.pdf', 'application/pdf', b'%PDF-b')]
        with patch('extractor.fetch', side_effect=replies), patch('extractor.permission', return_value={}), patch('extractor.pdf_text', side_effect=['1. First wording?\n2. Second wording?', '1. Different wording?\n2. Another wording?']):
            data = live(url, render_browser=False)
        self.assertEqual(len(data['questionnaire']), 2)
        self.assertEqual(data['questionnaire'][0]['text'], 'First wording?')
        self.assertEqual(data['documents'][1]['questionnaire'][0]['text'], 'Different wording?')

    def test_policy_scope_applies_to_each_document(self):
        self.assertTrue(permission('https://www.ptsd.va.gov/professional/assessment/documents/PCL5_Standard_form.pdf')['allow_fetch'])
        with self.assertRaises(ExtractionError):
            permission('https://www.ptsd.va.gov/professional/assessment/documents/unapproved.pdf')

    def test_robots_disallow_and_invalid_html_remain_blocked(self):
        for reply in [(200, {'Content-Type': 'text/plain'}, b'User-agent: *\nDisallow: /'),
                      (200, {'Content-Type': 'text/html'}, b'<html>Sign in first</html>')]:
            with patch('retrieval.request', return_value=reply), self.assertRaises(ExtractionError):
                robots_allowed('https://example.org/form')
        with patch('retrieval.request', return_value=(200, {'Content-Type': 'text/html'}, b'<meta name="dcterms.subject" content="Page Not Found - 404 Error" />')):
            robots_allowed('https://example.org/form')


if __name__ == '__main__':
    unittest.main()
