"""Escaped, self-contained HTML document; no remote assets or source HTML."""
from html import escape


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


def document(data):
    title = data['assessment'].get('name') or 'Assessment source document'
    sections = []
    def section(name, content, anchor):
        sections.append(f'<section id="{anchor}"><h2>{name}</h2>{content}</section>')
    section('Collection notes', render(data['warnings']), 'notes')
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
    for i, block in enumerate(data['sections']):
        section(esc(block['title']), f'<pre>{esc(block["text"])}</pre><p>{render(block["source_url"])}</p>', f'source-{i}')
    section('Documents', render(data['documents']), 'documents')
    if data.get('extraction_log'):
        section('Extraction log', render(data['extraction_log']), 'log')
    section('Sources and permissions', render({'sources': data['sources'], 'permissions': data.get('permission'), 'field_provenance': data['field_provenance']}), 'sources')
    section('Missing information and review', render({'missing_fields': data['missing_fields'], 'validation': data.get('validation'), 'status': data['status']}), 'missing')
    style = '''*{box-sizing:border-box}body{font:15px/1.65 system-ui,sans-serif;color:#203630;background:#fff;margin:0;padding:48px 54px}header{border-bottom:2px solid #245d4c;padding-bottom:24px}h1{font:38px/1.2 Georgia,serif;margin:12px 0}h2{font:25px/1.3 Georgia,serif;color:#245d4c}h3{font-size:16px;font-weight:550}section{padding-top:22px;border-bottom:1px solid #e3e9e5;padding-bottom:24px}a{color:#22614d;overflow-wrap:anywhere}p{margin:10px 0}.muted,summary{color:#738078;font-size:13px}.eyebrow{text-transform:uppercase;letter-spacing:2px;font-size:11px;color:#477663}dl{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:8px 20px}dt{text-transform:capitalize;color:#65756c}dd{margin:0;overflow-wrap:anywhere}dd dl{display:block}dd dt{margin-top:8px}ul{padding-left:22px}li{margin:6px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui}.question{padding:12px 0 20px;break-inside:avoid;border-bottom:1px solid #edf0ed}.number{color:#43816b;margin-right:10px}.options{display:grid;grid-template-columns:1fr 1fr;gap:8px;list-style:none;padding:0}.options li{padding:8px 12px;border:1px solid #dfe7e1;border-radius:6px;display:flex;justify-content:space-between;gap:10px;font-size:13px}.value{color:#2d6f55;font-weight:700}details{font-size:12px}footer{color:#738078;font-size:12px;margin-top:24px}@media(max-width:600px){body{padding:24px}h1{font-size:29px}dl{display:block}dt{margin-top:12px}.options{grid-template-columns:1fr}}@media print{body{padding:0;font-size:11px}h1{font-size:28px}h2{break-after:avoid}details{display:none}a{color:inherit}section{break-inside:auto}}'''
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title><style>{style}</style></head><body><header><div class="eyebrow">Assessment source document</div><h1>{esc(title)}</h1><p>{esc(data["mode"].replace("_", " "))} · Partial coverage</p><p class="muted">Requested URL: {render(data["requested_url"])}<br>Generated: {esc(data["created_at"])}</p></header>{"".join(sections)}<footer>Source review prototype. No clinical scoring is performed. Unavailable information has not been inferred.</footer></body></html>'
