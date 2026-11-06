const GAD_URL = 'https://novopsych.com/assessments/anxiety/generalised-anxiety-disorder-assessment-gad-7/';
const LIVE_URL = GAD_URL;
const $ = id => document.getElementById(id);
let current = null;
let documentHTML = '';
let busy = false;
$('url').value = LIVE_URL;
$('example').onclick = () => { $('url').value = LIVE_URL; $('mode').value = 'live'; $('url').focus(); };
$('try-example').onclick = () => { $('url').value = GAD_URL; $('mode').value = 'demo'; $('extract-form').requestSubmit(); };

function tab(json) {
  $('document-tab').setAttribute('aria-selected', String(!json));
  $('json-tab').setAttribute('aria-selected', String(json));
  $('document-pane').hidden = json;
  $('json-pane').hidden = !json;
}
$('document-tab').onclick = () => tab(false);
$('json-tab').onclick = () => tab(true);
for (const id of ['document-tab', 'json-tab']) $(id).onkeydown = event => {
  if (['ArrowLeft', 'ArrowRight'].includes(event.key)) {
    event.preventDefault();
    const json = id === 'document-tab'; tab(json); $(json ? 'json-tab' : 'document-tab').focus();
  }
};

function download(content, mime, extension) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = document.createElement('a');
  link.href = url;
  link.download = (current.assessment.abbreviation || 'assessment').replace(/[^a-z0-9-]/gi, '-') + '.' + extension;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('download-html').onclick = () => download(documentHTML, 'text/html;charset=utf-8', 'html');
$('download-json').onclick = () => download(JSON.stringify(current, null, 2), 'application/json', 'json');
$('print').onclick = () => { $('document-frame').contentWindow.focus(); $('document-frame').contentWindow.print(); };
document.querySelectorAll('[data-section]').forEach(button => {
  button.onclick = () => $('document-frame').contentDocument.getElementById(button.dataset.section)?.scrollIntoView({ behavior: 'smooth' });
});

$('extract-form').onsubmit = async event => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  $('submit').disabled = true;
  $('try-example').disabled = true;
  $('error').hidden = true;
  $('progress').textContent = 'Reading the page, opening tabs and processing linked PDFs. The first browser extraction can take 2–4 minutes…';
  $('preview-state').textContent = 'Preparing document';
  $('results').hidden = true;
  $('empty').hidden = false;
  current = null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 360000);
  try {
    const response = await fetch('/api/extract', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: $('url').value.trim(), mode: $('mode').value, process_documents: $('process-documents').checked, render_browser: $('render-browser').checked }), signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Extraction failed.');
    current = payload.result;
    documentHTML = payload.document;
    $('empty').hidden = true;
    $('results').hidden = false;
    $('result-name').textContent = current.assessment.name || 'Assessment source';
    $('result-label').textContent = current.mode === 'retained_publisher_source' ? 'RETAINED PUBLISHER SOURCE' : 'LIVE SOURCE EXTRACTION';
    $('result-origin').textContent = current.assessment.abbreviation || new URL(current.requested_url).hostname;
    $('question-count').textContent = current.questionnaire.length;
    $('source-count').textContent = current.sources.length;
    $('missing-count').textContent = current.missing_fields.length;
    $('coverage').textContent = current.warnings[0];
    $('document-frame').srcdoc = documentHTML;
    $('json-pane').textContent = JSON.stringify(current, null, 2);
    $('preview-state').textContent = 'Partial coverage · review ready';
    $('progress').textContent = 'Document ready. Review the notes and source evidence.';
    tab(false);
  } catch (error) {
    $('error').textContent = error.name === 'AbortError' ? 'This source took too long. Try again or use the retained example.' : error.message;
    $('error').hidden = false;
    $('progress').textContent = '';
    $('preview-state').textContent = 'Source needs attention';
  } finally {
    clearTimeout(timer);
    busy = false;
    $('submit').disabled = false;
    $('try-example').disabled = false;
  }
};
