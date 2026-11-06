"""Optional real network smoke test: python3 tests/live_novopsych.py."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extractor import extract
from document import document

SOURCES = {
    'GAD-7': 'https://novopsych.com/assessments/anxiety/generalised-anxiety-disorder-assessment-gad-7/',
    'PHQ-9': 'https://novopsych.com/assessments/depression/patient-health-questionnaire-depression-phq-9/',
    'DASS-21': 'https://novopsych.com/assessments/depression/depression-anxiety-stress-scales-short-form-dass-21/',
    'ASRS-O': 'https://novopsych.com/assessments/diagnosis/adult-adhd-observer-report-scale-asrs-o/',
}
root = Path(__file__).resolve().parents[1] / 'artifacts'
root.mkdir(exist_ok=True)
for name, url in SOURCES.items():
    print('Extracting', name, flush=True)
    result = extract(url)
    (root / (name+'-novopsych-live.json')).write_text(json.dumps(result, indent=2))
    (root / (name+'-novopsych-live.html')).write_text(document(result))
    print(json.dumps({'name': name, 'title': result['assessment']['name'], 'items': len(result['questionnaire']),
        'sections': len(result['sections']), 'browser': result.get('browser'),
        'documents': [(d['title'], d['status']) for d in result['documents']]}), flush=True)
    assert result['mode'] == 'live_source'
    assert result['sections'] and result['scoring']
    assert result.get('browser', {}).get('tabs'), 'No browser tabs captured'
    assert all(t['status'] == 'captured' for t in result['browser']['tabs'])
    expected, choices = {'GAD-7': (7,4), 'PHQ-9': (9,4), 'DASS-21': (21,4), 'ASRS-O': (18,5)}[name]
    assert len(result['questionnaire']) == expected
    assert all(len(q['options']) == choices for q in result['questionnaire'])
