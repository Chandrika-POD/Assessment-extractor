import base64
import unittest
from unittest.mock import patch

from document import document
from extractor import live
from rich_content import archive, collect_images
from source_parser import parse_html

URL = 'https://example.org/scale'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZuoAAAAASUVORK5CYII=')


class RichContentTests(unittest.TestCase):
    def test_largest_srcset_image_is_selected(self):
        parsed = parse_html('<main><h1>Example scale</h1><p>Enough text for a useful assessment content container.</p><img src="/small.png" srcset="/large.png 1200w, /small.png 300w"></main>', URL)
        self.assertEqual(parsed['images'][0]['url'], 'https://example.org/large.png')

    def test_table_structure_nested_image_and_offline_document(self):
        page = '''<main><h1>Example assessment</h1><p>Enough source text for a readable assessment document.</p>
        <h2>Scoring</h2><table><caption>Score bands</caption><tr><th colspan="2">Band</th></tr>
        <tr><td rowspan="2">A &lt; B</td><td>First</td></tr><tr><td>Second</td></tr></table>
        <figure><p><img src="/tiny.png" data-src="/chart.png" alt="Chart"></p><figcaption>Chart caption</figcaption></figure></main>'''
        with patch('extractor.fetch', side_effect=[(URL, 'text/html', page.encode()),
                   (URL+'/chart.png', 'image/png', PNG)]):
            result = live(URL, render_browser=False)
        self.assertEqual(result['images'][0]['url'], 'https://example.org/chart.png')
        self.assertEqual(result['images'][0]['caption'], 'Chart caption')
        self.assertEqual(result['coverage']['images_saved'], 1)
        html = document(result)
        self.assertIn('<table>', html)
        self.assertIn('colspan="2"', html)
        self.assertIn('rowspan="2"', html)
        self.assertIn('A &lt; B', html)
        self.assertIn('data:image/png;base64,', html)
        self.assertEqual(base64.b64decode(result['source_archive'][0]['data_base64']), page.encode())

    def test_more_than_three_documents_and_scanned_pdf_bytes_retained(self):
        page = '<main><h1>Scale</h1><p>Source with four linked questionnaire documents available for extraction.</p>'
        page += ''.join(f'<a href="/{n}.pdf">Form {n}</a>' for n in range(4)) + '</main>'
        from retrieval import ExtractionError
        replies = [(URL, 'text/html', page.encode())] + [(f'https://example.org/{n}.pdf', 'application/pdf', b'%PDF-scan') for n in range(4)]
        with patch('extractor.fetch', side_effect=replies), patch('extractor.pdf_text', side_effect=ExtractionError('Needs OCR', 'ocr_required')):
            result = live(URL, render_browser=False)
        self.assertEqual(result['coverage']['documents_archived'], 4)
        self.assertEqual(len(result['coverage']['unresolved']), 4)
        self.assertTrue(all(d['status'] == 'ocr_required' for d in result['documents']))
        self.assertEqual(document(result).count('Download original PDF'), 4)

    def test_image_markup_cannot_execute_html_or_svg(self):
        images = [{'url': 'https://example.org/a.png'}]
        collect_images(images, lambda url: (url, 'image/png', b'<svg onload="alert(1)"></svg>'))
        self.assertEqual(images[0]['status'], 'unsupported_format')
        self.assertNotIn('archive', images[0])

    def test_embedded_media_is_explicitly_reported(self):
        result = parse_html('<main><h1>Scale</h1><p>A sufficiently long source paragraph to select the content.</p><svg><text>Chart</text></svg><iframe src="https://example.org/video"></iframe></main>', URL)
        self.assertEqual({m['kind'] for m in result['embedded_media']}, {'svg', 'iframe'})

    def test_raw_source_links_survive_rendered_tab_merge(self):
        page = '<main><h1>Scale</h1><p>Enough visible source text to retain a useful assessment overview.</p><a href="/reference">Reference</a></main>'
        snapshot = '<main><h1>Scale</h1><p>A different rendered tab with more source text.</p></main>'
        rendered = {'tabs': [], 'snapshots': [{'html': snapshot}]}
        with patch('extractor.fetch', return_value=(URL, 'text/html', page.encode())), patch('browser_capture.capture', return_value=rendered):
            result = live(URL, process_documents=False)
        self.assertEqual(result['links'][0]['url'], 'https://example.org/reference')
        self.assertEqual(len(result['source_archive']), 2)


if __name__ == '__main__':
    unittest.main()
