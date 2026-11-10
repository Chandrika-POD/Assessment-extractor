import json
from pathlib import Path
import tempfile
import unittest

from batch_extract import run, source_key, urls_from_file
from extractor import base


def fake_extract(url, *args):
    result = base(url)
    result.update(mode='live_source', sources=[{'url': url}], validation={})
    result['assessment']['name'] = 'Fixture scale'
    result['warnings'] = ['Synthetic test source']
    result['sections'] = [{'title': 'Overview', 'text': 'Fixture source', 'source_url': url}]
    return result


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root/'urls.txt'
        self.input.write_text('https://example.org/a\nhttps://example.org/b\n')

    def tearDown(self):
        self.temp.cleanup()

    def test_resume_skips_saved_outputs_and_continues_pending(self):
        out = self.root/'run'
        run(self.input, out, limit=1, extraction_fn=fake_extract)
        called = []
        def fake(url, *args):
            called.append(url)
            return fake_extract(url)
        result = run(self.input, out, extraction_fn=fake)
        self.assertEqual(called, ['https://example.org/b'])
        self.assertEqual(result['counts'], {'extracted': 2})
        self.assertTrue((out/'index.html').is_file())
        self.assertTrue(all(r['review_status']=='needs_review' for r in result['items']))

    def test_failure_does_not_stop_remaining_urls_and_can_retry(self):
        def fake(url, *args):
            if url.endswith('/a'):
                raise ValueError('Unavailable source')
            return fake_extract(url)
        out = self.root/'run'
        result = run(self.input, out, extraction_fn=fake)
        self.assertEqual(result['counts'], {'failed': 1, 'extracted': 1})
        result = run(self.input, out, retry_failed=True, extraction_fn=fake_extract)
        self.assertEqual(result['counts'], {'extracted': 2})
        self.assertEqual(len(result['items'][0]['attempts']), 2)
        self.assertTrue((out/'assessments'/result['items'][0]['source_key']/'attempts/0001/status.json').is_file())

    def test_changed_input_and_corrupt_artifact_are_not_silently_skipped(self):
        out = self.root/'run'
        result = run(self.input, out, extraction_fn=fake_extract)
        saved = self.input.read_text()
        self.input.write_text('https://example.org/c\n')
        with self.assertRaises(ValueError):
            run(self.input, out, extraction_fn=fake_extract)
        self.input.write_text(saved)
        (out/result['items'][0]['files']['extraction']).write_text('{}')
        with self.assertRaises(ValueError):
            run(self.input, out, extraction_fn=fake_extract)

    def test_source_identity_does_not_collide_for_same_slug(self):
        self.assertNotEqual(source_key('https://example.org/child/same'), source_key('https://example.org/diagnosis/same'))

    def test_exact_duplicates_are_removed_but_aliases_remain(self):
        self.input.write_text('https://example.org/a\nhttps://example.org/a#section\nhttps://example.org/child/a\n')
        self.assertEqual(len(urls_from_file(self.input)), 2)


if __name__ == '__main__':
    unittest.main()
