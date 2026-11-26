import json
from pathlib import Path
import tempfile
import unittest
from batch_index import enrich_manifest, render_index


class BatchIndexTests(unittest.TestCase):
    def test_summary_preserves_counts_and_failures_without_asset_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'result.json').write_text(json.dumps({
                'tables': [{'rows': [['Example']]}],
                'images': [{'status': 'saved', 'archive': {'data_base64': 'DO_NOT_COPY'}}, {'status': 'failed'}],
                'documents': [{'status': 'processed', 'archive': {'data_base64': 'DO_NOT_COPY'}}, {'status': 'ocr_required', 'archive': { 'data_base64': 'DO_NOT_COPY' }}],
                'browser': {'tabs': [{'status': 'captured'}]},
                'coverage': {'unresolved': [{'kind': 'document', 'status': 'ocr_required', 'error': 'OCR needed'}]},
                'missing_fields': ['assessment.purpose'], 'source_archive': [{}]
            }))
            manifest = {'items': [{'status': 'extracted', 'files': {'extraction': 'result.json'}}]}
            enrich_manifest(root, manifest)
            summary = manifest['items'][0]['capture_summary']
            self.assertEqual((summary['images_saved'], summary['images_discovered']), (1, 2))
            self.assertEqual((summary['pdfs_saved'], summary['pdf_texts']), (2, 1))
            self.assertEqual(summary['unresolved'][0]['status'], 'ocr_required')
            self.assertNotIn('DO_NOT_COPY', json.dumps(manifest))

    def test_source_text_cannot_close_embedded_json_script(self):
        value = '</script><script>window.injected=true</script>'
        rendered = render_index({'items': [{'title': value}]})
        self.assertNotIn(value, rendered)
        block = rendered.split('<script id="initial-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(block)['items'][0]['title'], value)


if __name__ == '__main__':
    unittest.main()
