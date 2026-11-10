"""Resumable one-URL-at-a-time extraction. Run python3 batch_extract.py --help."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
from html import escape
import io
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit

from document import document
from extractor import extract
from retrieval import validate_url

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(path)


def json_write(path, value):
    atomic(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def urls_from_file(path):
    unique = {}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        url = line.strip()
        if not url or url.startswith('#'):
            continue
        p = validate_url(url)
        url = urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, ''))
        unique.setdefault(url, None)
    return list(unique)


def source_key(url):
    slug = urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1] or 'source'
    slug = re.sub('[^a-z0-9-]+', '-', slug.lower()).strip('-')[:85]
    return slug + '--' + digest(url.encode())[:12]


def code_revision():
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
        return {'commit': commit, 'working_tree_modified': dirty}
    except (OSError, subprocess.CalledProcessError):
        return {'commit': None, 'working_tree_modified': True}


def issues_for(result):
    issues = []
    browser = result.get('browser', {})
    if browser.get('status') == 'failed':
        issues.append('browser_failed')
    if any(t.get('status') != 'captured' for t in browser.get('tabs', [])):
        issues.append('some_tabs_unavailable')
    if not result.get('questionnaire'):
        issues.append('no_structured_questions')
    if not result.get('scoring'):
        issues.append('no_structured_scoring')
    if any(d.get('status') not in ('processed', 'retained_excerpt') for d in result.get('documents', [])):
        issues.append('some_documents_not_processed')
    if result.get('missing_fields'):
        issues.append('metadata_fields_unavailable')
    return issues


def checkpoint(output, manifest):
    manifest['updated_at'] = now()
    manifest['counts'] = dict(Counter(item['status'] for item in manifest['items']))
    groups = defaultdict(list)
    for item in manifest['items']:
        if item.get('resolved_url'):
            groups[item['resolved_url']].append(item['source_key'])
    manifest['possible_aliases'] = {u: keys for u, keys in groups.items() if len(keys) > 1}
    json_write(output / 'manifest.json', manifest)
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(['source_key', 'url', 'status', 'title', 'question_count', 'option_count', 'coverage_issues', 'error', 'document', 'json'])
    rows = []
    for item in manifest['items']:
        files = item.get('files', {})
        writer.writerow([item['source_key'], item['url'], item['status'], item.get('title', ''), item.get('question_count', ''),
            item.get('option_count', ''), '; '.join(item.get('coverage_issues', [])), item.get('error', ''), files.get('document', ''), files.get('extraction', '')])
        links = ' '.join(f'<a href="{escape(files[k], quote=True)}">{k}</a>' for k in ('document', 'extraction') if files.get(k))
        rows.append('<tr>' + ''.join(f'<td>{escape(str(value))}</td>' for value in [
            item.get('title') or item['source_key'], item['status'], item.get('question_count', ''),
            ', '.join(item.get('coverage_issues', [])) or item.get('error', '')]) +
            f'<td><a href="{escape(item["url"], quote=True)}">Source</a> {links}</td></tr>')
    atomic(output / 'summary.csv', csv_buffer.getvalue())
    counts = ', '.join(f'{k}: {v}' for k, v in manifest['counts'].items())
    atomic(output / 'index.html', '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">'
        '<title>Assessment batch review</title><style>body{font:14px system-ui;margin:32px;color:#243d32}'
        'table{border-collapse:collapse;width:100%}th,td{text-align:left;border:1px solid #ddd;padding:10px;overflow-wrap:anywhere}'
        'a{color:#245d4c;margin-right:8px}</style></head><body><h1>Assessment batch review</h1>'
        f'<p>{escape(counts)} / {len(manifest["items"])} URLs. Updated: {escape(manifest["updated_at"])}</p>'
        '<p>Extraction drafts only. No assessment is approved for clinical use or Gemini execution.</p>'
        '<p><a href="manifest.json">Manifest</a><a href="summary.csv">CSV summary</a><a href="urls.txt">Input URLs</a></p>'
        '<table><thead><tr><th>Assessment</th><th>Retrieval</th><th>Questions</th><th>Review issues</th><th>Files</th></tr></thead><tbody>'
        + ''.join(rows) + '</tbody></table></body></html>')


def run(input_file, output, retry_failed=False, limit=None, extraction_fn=extract):
    urls = urls_from_file(input_file)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / '.run.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This output folder already has a running batch.')
        input_text = '\n'.join(urls) + '\n'
        fingerprint = digest(input_text.encode())
        manifest_file = output / 'manifest.json'
        if manifest_file.exists():
            manifest = json.loads(manifest_file.read_text())
            if manifest['input_sha256'] != fingerprint:
                raise ValueError('The URL list differs from this run. Use a new output folder.')
        else:
            manifest = {'schema_version': 'batch/1', 'run_id': output.name, 'created_at': now(),
                'input_sha256': fingerprint, 'extractor': code_revision(), 'run_status': 'running',
                'configuration': {'mode': 'live', 'render_browser': True, 'process_documents': True, 'max_linked_pdfs': 3, 'concurrency': 1},
                'items': [{'url': url, 'source_key': source_key(url), 'status': 'pending', 'attempts': []} for url in urls]}
            atomic(output / 'urls.txt', input_text)
        manifest['run_status'] = 'running'
        checkpoint(output, manifest)
        attempted = 0
        for ordinal, row in enumerate(manifest['items'], 1):
            if row['status'] == 'extracted':
                # A checkpoint must have its promised artifacts before it can be skipped.
                for kind, relative in row.get('files', {}).items():
                    path = output / relative
                    if not path.is_file() or digest(path.read_bytes()) != row['checksums'][kind]:
                        raise ValueError(f'Artifact missing or changed for {row["source_key"]}. Use a new output folder.')
                continue
            if row['status'] == 'failed' and not retry_failed:
                continue
            if limit is not None and attempted >= limit:
                break
            attempted += 1
            attempt = {'number': len(row['attempts'])+1, 'started_at': now(), 'extractor': code_revision()}
            row['attempts'].append(attempt)
            row.update(status='running', error=None)
            folder = Path('assessments') / row['source_key'] / 'attempts' / f'{attempt["number"]:04d}'
            checkpoint(output, manifest)
            atomic(output / folder / 'source_url.txt', row['url'] + '\n')
            print(f'[{ordinal}/{len(urls)}] extracting {row["url"]}', flush=True)
            try:
                result = extraction_fn(row['url'], 'live', True, True)
                json_write(output / folder / 'extraction.json', result)
                atomic(output / folder / 'document.html', document(result))
                files = {'extraction': str(folder / 'extraction.json'), 'document': str(folder / 'document.html'), 'source': str(folder / 'source_url.txt')}
                row.update(status='extracted', title=result.get('assessment', {}).get('name'),
                    question_count=len(result.get('questionnaire', [])), option_count=sum(len(q.get('options', [])) for q in result.get('questionnaire', [])),
                    resolved_url=result.get('sources', [{}])[0].get('url'), coverage_issues=issues_for(result),
                    review_status='needs_review', files=files, checksums={k: digest((output/v).read_bytes()) for k, v in files.items()})
            except KeyboardInterrupt:
                row['status'] = 'interrupted'
                manifest['run_status'] = 'interrupted'
                attempt.update(finished_at=now(), status='interrupted')
                json_write(output / folder / 'status.json', row)
                checkpoint(output, manifest)
                raise
            except Exception as exc:
                row.update(status='failed', error=str(exc), error_type=type(exc).__name__, error_status=getattr(exc, 'status', 'extraction_failed'))
            attempt.update(finished_at=now(), status=row['status'], folder=str(folder))
            json_write(output / folder / 'status.json', row)
            checkpoint(output, manifest)
            print(f'[{ordinal}/{len(urls)}] {row["status"]}; questions={row.get("question_count", 0)}; issues={row.get("coverage_issues", [])}; error={row.get("error")}', flush=True)
        manifest['run_status'] = 'finished' if all(r['status'] in ('extracted', 'failed') for r in manifest['items']) else 'paused'
        checkpoint(output, manifest)
        print(json.dumps({'run_status': manifest['run_status'], 'counts': manifest['counts'], 'index': str(output/'index.html')}), flush=True)
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'data/novopsych_assessment_urls.txt')
    parser.add_argument('--output', type=Path, required=True, help='Reuse the same folder to resume; use a new folder for a fresh extraction.')
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--limit', type=int, help='Maximum URLs attempted in this invocation, for smoke tests.')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    try:
        run(args.input, args.output, args.retry_failed, args.limit)
    except KeyboardInterrupt:
        parser.exit(130, 'Interrupted. Reuse --output to resume.\n')
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc)+'\n')
