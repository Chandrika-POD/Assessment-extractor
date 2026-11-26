"""Escaped HTML document with embedded raster images and downloadable source archives."""
from html import escape
import base64
from rich_content import raster_type


def esc(value):
    return escape(str(value), quote=True)


def render(value):
    if value is None:
        return '<span class="muted">Unavailable in collected sources</span>'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, dict):
        return '<dl>' + ''.join(f'<dt>{esc(k.replace("_", " "))}</dt><dd>{render(v)}</dd>' for k, v in value.items()) + '</dl>'
    if isinstance(value, list):
        return '<ul>' + ''.join(f'<li>{render(v)}</li>' for v in value) + '</ul>' if value else '<span class="muted">None recorded</span>'
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        return f'<a href="{esc(value)}" target="_blank" rel="noopener noreferrer">{esc(value)}</a>'
    return esc(value)


def archive_link(saved, label, filename, mime):
    encoded = saved.get('data_base64', '')
    try:
        base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return '<p>Archive unavailable</p>'
    return f'<a download="{esc(filename)}" href="data:{mime};base64,{encoded}">{esc(label)}</a>'


def render_tables(tables):
    output = []
    for index, table in enumerate(tables, 1):
        rows = table.get('cells') or [[{'text': c} for c in row] for row in table['rows']]
        html = ''
        for row in rows:
            html += '<tr>'
            for cell in row:
                tag = 'th' if cell.get('header') else 'td'
                def span(key):
                    try:
                        return max(1, min(100, int(cell.get(key, 1))))
                    except (ValueError, TypeError):
                        return 1
                html += f'<{tag} rowspan="{span("rowspan")}" colspan="{span("colspan")}">{esc(cell["text"])}</{tag}>'
            html += '</tr>'
        caption = table.get('caption') or table.get('section') or f'Table {index}'
        output.append(f'<div class="source-table"><table><caption>{esc(caption)}</caption>{html}</table></div><p>{render(table["source_url"])}</p>')
    return ''.join(output)


def render_images(images):
    output = []
    for image in images:
        saved = image.get('archive', {})
        encoded = saved.get('data_base64', '')
        try:
            kind = raster_type(base64.b64decode(encoded, validate=True))
        except (ValueError, TypeError):
            kind = None
        visual = (f'<a href="{esc(image["url"])}" target="_blank" rel="noopener noreferrer"><img loading="lazy" src="data:{kind};base64,{encoded}" alt="{esc(image.get("alt", ""))}"></a>'
                  if kind else f'<p>Image unavailable: {esc(image.get("error") or image["status"])}</p>')
        caption = image.get('caption') or image.get('alt') or image.get('section', 'Source image')
        output.append(f'<figure>{visual}<figcaption>{esc(caption)}</figcaption><p>{render(image["url"])}</p></figure>')
    return ''.join(output)


def document(data):
    title = data['assessment'].get('name') or 'Assessment source document'
    sections = []
    def section(name, content, anchor):
        sections.append(f'<section id="{anchor}"><h2>{name}</h2>{content}</section>')
    section('Collection notes', render(data['warnings']), 'notes')
    if data.get('coverage'):
        section('Capture coverage', render(data['coverage']), 'coverage')
    if data.get('browser'):
        section('Page tabs', render(data['browser']), 'tabs')
    section('Assessment information', render({k: v for k, v in data['assessment'].items() if v is not None}), 'overview')
    section('Respondent instructions', render(data['instructions']), 'instructions')
    questions = data['questionnaire']
    content = ''
    for i, q in enumerate(questions, 1):
        options = ''.join(f'<li>{esc(o["label"])} <span class="value">{esc(o["score"] if o.get("score") is not None else o.get("response_value", "Unknown"))}</span></li>' for o in q['options'])
        reverse = 'Unknown' if q.get('reverse_scored') is None else ('Yes' if q['reverse_scored'] else 'No')
        options = f'<ul class="options">{options}</ul>' if options else '<p class="muted">Response options could not be reliably identified. Review the source.</p>'
        content += f'<article class="question"><h3><span class="number">{i:02d}</span> {esc(q["text"])}</h3>{options}<p class="muted">{esc(q["type"])} · Reverse scored: {reverse} · Source review required</p><details><summary>Item source</summary>{render(q["source"])}</details></article>'
    section(f'Questionnaire · {len(questions)} structured items', content or '<p class="muted">No verified questionnaire structure available. Check the source text and review candidates below.</p>', 'questionnaire')
    if data.get('question_candidates'):
        section('Numbered lines · unverified candidates', render(data['question_candidates']), 'candidates')
    section('Scoring and interpretation', render(data['scoring']), 'scoring')
    if data.get('interpretation'):
        section('Interpretation', render(data['interpretation']), 'interpretation')
    if data.get('tables'):
        section('Source tables', render_tables(data['tables']), 'tables')
    if data.get('images'):
        section('Source images and charts', render_images(data['images']), 'images')
    for i, block in enumerate(data['sections']):
        section(esc(block['title']), f'<pre>{esc(block["text"])}</pre><p>{render(block["source_url"])}</p>', f'source-{i}')
    docs = ''
    for index, doc in enumerate(data['documents'], 1):
        docs += render({k: v for k, v in doc.items() if k != 'archive'})
        if doc.get('archive'):
            docs += archive_link(doc['archive'], 'Download original PDF (includes diagrams and layout)', f'source-document-{index}.pdf', 'application/pdf')
    section('Documents', docs or '<p>None discovered.</p>', 'documents')
    if data.get('links'):
        section('All discovered source links', render(data['links']), 'links')
    if data.get('source_archive'):
        archives = ''
        for index, saved in enumerate(data['source_archive'], 1):
            mime = 'application/pdf' if saved['mime_type'] == 'application/pdf' else 'text/plain'
            suffix = 'pdf' if mime == 'application/pdf' else 'html.txt'
            archives += '<p>' + archive_link(saved, saved.get('label', 'Source snapshot'), f'source-{index}.{suffix}', mime) + '</p>'
        section('Archived page and tab sources', '<p>HTML snapshots download as text for inspection; source scripts are not run.</p>'+archives, 'archive')
    if data.get('extraction_log'):
        section('Extraction log', render(data['extraction_log']), 'log')
    section('Sources and permissions', render({'sources': data['sources'], 'permissions': data.get('permission'), 'field_provenance': data['field_provenance']}), 'sources')
    section('Missing information and review', render({'missing_fields': data['missing_fields'], 'validation': data.get('validation'), 'status': data['status']}), 'missing')
    style = '''*{box-sizing:border-box}body{font:15px/1.65 system-ui,sans-serif;color:#203630;background:#fff;margin:0;padding:48px 54px}header{border-bottom:2px solid #245d4c;padding-bottom:24px}h1{font:38px/1.2 Georgia,serif;margin:12px 0}h2{font:25px/1.3 Georgia,serif;color:#245d4c}h3{font-size:16px;font-weight:550}section{padding-top:22px;border-bottom:1px solid #e3e9e5;padding-bottom:24px}a{color:#22614d;overflow-wrap:anywhere}p{margin:10px 0}.muted,summary{color:#738078;font-size:13px}.eyebrow{text-transform:uppercase;letter-spacing:2px;font-size:11px;color:#477663}dl{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:8px 20px}dt{text-transform:capitalize;color:#65756c}dd{margin:0;overflow-wrap:anywhere}dd dl{display:block}dd dt{margin-top:8px}ul{padding-left:22px}li{margin:6px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui}.question{padding:12px 0 20px;break-inside:avoid;border-bottom:1px solid #edf0ed}.number{color:#43816b;margin-right:10px}.options{display:grid;grid-template-columns:1fr 1fr;gap:8px;list-style:none;padding:0}.options li{padding:8px 12px;border:1px solid #dfe7e1;border-radius:6px;display:flex;justify-content:space-between;gap:10px;font-size:13px}.value{color:#2d6f55;font-weight:700}details{font-size:12px}footer{color:#738078;font-size:12px;margin-top:24px}@media(max-width:600px){body{padding:24px}h1{font-size:29px}dl{display:block}dt{margin-top:12px}.options{grid-template-columns:1fr}}@media print{body{padding:0;font-size:11px}h1{font-size:28px}h2{break-after:avoid}details{display:none}a{color:inherit}section{break-inside:auto}}'''
    style += 'figure{margin:24px 0}figure img{max-width:100%;height:auto;border:1px solid #ddd}figcaption{font-weight:600}.source-table{overflow-x:auto}table{border-collapse:collapse;width:100%;margin:16px 0}caption{text-align:left;font-weight:600;padding:12px 0}th,td{padding:10px;border:1px solid #ccd8d2;text-align:left;vertical-align:top}th{background:#eef4f1}'
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title><style>{style}</style></head><body><header><div class="eyebrow">Assessment source document</div><h1>{esc(title)}</h1><p>{esc(data["mode"].replace("_", " "))} · Partial coverage</p><p class="muted">Requested URL: {render(data["requested_url"])}<br>Generated: {esc(data["created_at"])}</p></header>{"".join(sections)}<footer>Source review prototype. No clinical scoring is performed. Unavailable information has not been inferred.</footer></body></html>'
