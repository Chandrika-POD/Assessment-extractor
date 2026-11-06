"""Small URL-driven engine: retained instrument sources + permitted live HTML/PDF."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urljoin, urlsplit

from retrieval import ExtractionError, public_fetch as fetch, permission, validate_url

ROOT = Path(__file__).parent
GAD_URL = 'https://novopsych.com/assessments/anxiety/generalised-anxiety-disorder-assessment-gad-7/'
RETAINED_PAGE_URLS = {
    'GAD-7': GAD_URL,
    'PHQ-9': 'https://novopsych.com/assessments/depression/patient-health-questionnaire-depression-phq-9/',
}
FIELDS = ['description', 'purpose', 'target_population', 'intended_use', 'administration_time',
          'format', 'publisher', 'reference_period', 'psychometrics', 'normative_data', 'missing_item_handling']


def normalize(url):
    p = validate_url(url)
    return p.hostname.lower(), p.path.rstrip('/')


def base(url):
    return {'schema_version': '0.1', 'requested_url': url, 'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'partial', 'mode': None, 'assessment': {k: None for k in FIELDS},
            'instructions': None, 'questionnaire': [], 'scoring': {}, 'sections': [],
            'documents': [], 'sources': [], 'warnings': [], 'missing_fields': [], 'field_provenance': {}}


def retained(url, record):
    result = base(url)
    result['mode'] = 'retained_publisher_source'
    result['assessment'].update(name=record['name'], abbreviation=record['assessment_id'],
        category=record['category'], language=record['language'], question_count=len(record['questions']))
    result['instructions'] = record['instructions']
    period = re.search(r'(?:last|past)\s+(\d+\s+(?:days?|weeks?|months?))', record['instructions'], re.I)
    if period:
        result['assessment']['reference_period'] = period.group(1)
    result['questionnaire'] = record['questions']
    result['scoring'] = record['scoring']
    result['permission'] = record['licensing']
    result['validation'] = record['validation']
    sources = [q['source'] for q in record['questions']] + record['scoring']['evidence'] + record['licensing']['evidence']
    result['sources'] = list({s['url']: s for s in sources}.values())
    result['documents'] = [{'url': s['url'], 'status': 'retained_excerpt', 'title': s.get('title', 'Original questionnaire PDF')}
                           for s in result['sources'] if urlsplit(s['url']).path.lower().endswith('.pdf')]
    result['field_provenance'] = {
        'assessment': {'type': 'retained_local_record', 'file': 'data/instruments.json', 'review': 'Needs independent source review'},
        'instructions': record['questions'][0]['source'],
        'assessment.reference_period': record['questions'][0]['source'],
        'questionnaire': 'Each item contains its own source URL, page and capture date.',
        'scoring': record['scoring']['evidence'],
    }
    result['warnings'] = [
        'This is a retained publisher-source preview, not a live scrape or a complete copy of the submitted webpage.',
        'Questionnaire wording was captured on 5 November 2026 and still needs independent review.',
        'NovoPsych page content, proprietary norms and reports have not been collected.',
        'Missing fields mean unavailable in these retained sources, not absent from the assessment itself.',
    ]
    result['missing_fields'] = [f'assessment.{k}' for k, v in result['assessment'].items() if v is None]
    return result


def pdf_text(body):
    if not shutil.which('pdftotext'):
        raise ExtractionError('PDF extraction requires the system pdftotext command.', 'extraction_failed')
    with tempfile.TemporaryDirectory(prefix='assessment-pdf-') as temp:
        path = Path(temp) / 'source.pdf'
        path.write_bytes(body)
        proc = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, timeout=20)
        if proc.returncode:
            raise ExtractionError('PDF could not be parsed; it may be protected or damaged.', 'extraction_failed')
        text = proc.stdout.decode('utf-8', errors='replace').strip()
        if len(text) < 30:
            raise ExtractionError('PDF has no usable text layer. OCR is needed; no questionnaire was inferred.', 'ocr_required')
        return text


class PageParser(HTMLParser):
    """Basic text extraction kept inline so the original app has no parsing module dependency."""
    SKIP = {'script', 'style', 'nav', 'footer', 'noscript', 'svg', 'template', 'head'}
    VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.blocks, self.links, self.buffer, self.lists = [], [], [], [], []
        self.heading, self.title, self.in_title = None, '', False

    def flush(self):
        text = re.sub(r'\s+', ' ', ''.join(self.buffer)).strip()
        if text:
            self.blocks.append((self.heading or 'text', text))
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        hidden = (bool(self.stack and self.stack[-1][1]) or tag in self.SKIP
                  or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
                  or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style', ''), re.I)))
        if tag not in self.VOID:
            self.stack.append((tag, hidden))
        if hidden:
            return
        if tag in {'p', 'div', 'section', 'article', 'main', 'li', 'tr', 'br'} or re.fullmatch('h[1-6]', tag):
            self.flush()
        if re.fullmatch('h[1-6]', tag):
            self.heading = tag
        if tag == 'ol':
            self.lists.append(0)
        if tag == 'li' and self.lists:
            self.lists[-1] += 1
            self.buffer.append(f'{self.lists[-1]}. ')
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])

    def handle_endtag(self, tag):
        hidden = bool(self.stack and self.stack[-1][1])
        if not hidden and (tag in {'p', 'div', 'section', 'article', 'main', 'li', 'tr'} or re.fullmatch('h[1-6]', tag)):
            self.flush()
        if re.fullmatch('h[1-6]', tag):
            self.heading = None
        if tag == 'ol' and self.lists:
            self.lists.pop()
        if tag == 'title':
            self.in_title = False
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if not self.stack or not self.stack[-1][1]:
            self.buffer.append(data)


def live(url, process_documents=True, render_browser=True):
    from source_parser import parse_html, html_questions, pdf_questions, map_sections
    result = base(url)
    result['mode'] = 'live_source'
    final, content_type, body = fetch(url)
    try:
        result['permission'] = permission(final)
    except ExtractionError:
        result['permission'] = {'access': 'public_page', 'reproduction_permission': 'not_verified',
            'note': 'Public retrieval does not establish licensing or reuse rights.'}
    result['sources'] = [{'url': final, 'retrieved_at': result['created_at']}]
    result['extraction_log'] = [{'stage': 'source', 'url': final, 'status': 'retrieved'}]
    if 'application/pdf' in content_type or body.startswith(b'%PDF-'):
        text = pdf_text(body)
        result['assessment']['name'] = urlsplit(final).path.rsplit('/', 1)[-1]
        result['sections'] = [{'title': 'PDF text', 'text': text, 'source_url': final}]
        result['questionnaire'] = pdf_questions(text, final)
        result['documents'] = [{'title': 'Submitted PDF', 'url': final, 'status': 'processed'}]
    elif 'text/html' in content_type:
        charset = re.search(r'charset=([\w-]+)', content_type, re.I)
        try:
            html = body.decode(charset.group(1) if charset else 'utf-8', errors='replace')
        except LookupError:
            html = body.decode('utf-8', errors='replace')
        parsed = parse_html(html, final)
        if render_browser:
            from browser_capture import capture
            try:
                rendered = capture(final, html)
                snapshots = [parse_html(s['html'], final) for s in rendered['snapshots']]
                if snapshots:
                    combined = snapshots[0]
                    for part in snapshots[1:]:
                        for key in ('sections', 'tables', 'links', 'list_items'):
                            combined[key].extend(part[key])
                    for key in ('sections', 'tables', 'links', 'list_items'):
                        combined[key] = list({json.dumps(v, sort_keys=True): v for v in combined[key]}.values())
                    combined['description'] = parsed['description']
                    parsed = combined
                result['browser'] = {'engine': 'Playwright Chromium', 'tabs': rendered['tabs'], 'page_errors': rendered.get('page_errors', [])}
                result['extraction_log'] += [{'stage': 'tab', **t} for t in rendered['tabs']]
            except (ExtractionError, OSError) as exc:
                result['browser'] = {'engine': 'Playwright Chromium', 'status': 'failed', 'error': str(exc)}
                result['warnings'].append('Browser rendering failed; only initially accessible HTML is included: '+str(exc))
        result['provider'] = parsed['provider']
        result['assessment'].update(name=parsed['name'], description=parsed['description'])
        result['sections'] = parsed['sections']
        result['tables'] = parsed['tables']
        result['questionnaire'] = html_questions(parsed)
        result['documents'] = [{**link, 'status': 'not_processed'} for link in parsed['links']
            if urlsplit(link['url']).path.lower().endswith('.pdf')][:50]
        result['documents'].sort(key=lambda d: (bool(re.search(r'sample|results|example[-_ ]?report|scoring[-_ ]?report|manual', d['title']+' '+d['url'], re.I)),
            not bool(re.search(r'standard|questionnaire|form|survey', d['title']+' '+d['url'], re.I))))
        result['warnings'].append('Page retrieved live. Check tab and document statuses for coverage. Image-only content may need OCR.')
    else:
        raise ExtractionError('Only HTML webpages and text-based PDFs are supported.', 'unsupported_format')
    text = '\n'.join(s['text'] for s in result['sections'])
    if len(text.strip()) < 40:
        raise ExtractionError('No substantial source text found. This page may require JavaScript or access credentials.', 'extraction_failed')
    if 'text/html' in content_type and process_documents:
        for doc in result['documents'][:3]:
            try:
                resolved, _, content = fetch(doc['url'])
                if not content.startswith(b'%PDF-'):
                    raise ExtractionError('Link did not return a PDF.', 'extraction_failed')
                pdf = pdf_text(content)
                doc.update(status='processed', resolved_url=resolved)
                result['sources'].append({'url': resolved, 'retrieved_at': result['created_at'], 'discovered_on': final})
                result['sections'].append({'title': 'Document: '+doc['title'], 'text': pdf, 'source_url': resolved})
                if not re.search(r'sample|results|example[-_ ]?report|scoring[-_ ]?report|manual', doc['title']+' '+doc['url'], re.I):
                    questions = pdf_questions(pdf, resolved)
                    if not result['questionnaire']:
                        result['questionnaire'] = questions
                        doc['used_for_main_questionnaire'] = bool(questions)
                    elif questions:
                        doc['questionnaire'] = questions
                        doc['used_for_main_questionnaire'] = False
            except ExtractionError as exc:
                doc.update(status=exc.status, error=str(exc))
            except (OSError, subprocess.TimeoutExpired):
                doc.update(status='extraction_failed', error='Document retrieval or parsing failed.')
            result['extraction_log'].append({'stage': 'document', 'url': doc['url'], 'status': doc['status']})
    unique = {}
    for question in result['questionnaire']:
        key = re.sub(r'\W+', '', question['text']).lower()
        if key in unique:
            unique[key].setdefault('additional_sources', []).append(question['source'])
        else:
            unique[key] = question
    result['questionnaire'] = list(unique.values())
    for i, q in enumerate(result['questionnaire'], 1):
        q['id'] = f'Q{i}'
    map_sections(result)
    result['question_candidates'] = [{'number': int(n), 'text': t.strip(), 'status': 'needs_review', 'source_url': final}
        for n, t in re.findall(r'^\s*(\d{1,3})[.)]\s+([^\n]+)', text, re.M)] if not result['questionnaire'] else []
    result['validation'] = {'extracted_item_count': len(result['questionnaire']), 'questionnaire_status': 'needs_review',
                            'independent_wording_review_completed': False, 'ready_for_clinical_use': False}
    result['warnings'] += ['Extracted question text and option mappings need review against the source; reverse scoring is not inferred.',
        'Printed response values are preserved; item scores are unknown until scoring rules are reviewed. Additional forms remain separate under Documents.',
        'Only three linked PDFs are processed. Each has an independent status; restricted or failed documents do not erase page results.',
        'Unknown fields are left unavailable. No LLM or clinical scoring is used.']
    result['missing_fields'] = [f'assessment.{k}' for k, v in result['assessment'].items() if v is None]
    result['field_provenance'].update({'assessment.name': {'url': final, 'locator': 'Page heading or PDF filename'},
        'questionnaire': 'Per-item source URL, page/table and original source lines'})
    if result['assessment']['description'] and 'assessment.description' not in result['field_provenance']:
        result['field_provenance']['assessment.description'] = {'url': final, 'locator': 'HTML description metadata'}
    return result


def extract(url, source_mode='live', process_documents=True, render_browser=True):
    validate_url(url)
    if source_mode not in ('demo', 'auto', 'live'):
        raise ExtractionError('Unknown source mode.', 'invalid_request')
    records = json.loads((ROOT / 'data/instruments.json').read_text())
    if source_mode == 'demo':
        for record in records:
            urls = {q['source']['url'] for q in record['questions']}
            page_url = RETAINED_PAGE_URLS.get(record['assessment_id'])
            if page_url:
                urls.add(page_url)
            if normalize(url) in {normalize(u) for u in urls}:
                return retained(url, record)
    if source_mode == 'demo':
        raise ExtractionError('No saved example exists for this URL. Select Live extraction for a permitted source.', 'unavailable')
    return live(url, process_documents, render_browser)
