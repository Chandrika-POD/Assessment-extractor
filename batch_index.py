"""Compact batch dashboard. Source bytes stay in each assessment's JSON export."""
import json


def enrich_manifest(output, manifest):
    for item in manifest['items']:
        if item['status'] != 'extracted' or item.get('capture_summary'):
            continue
        source = output / item['files']['extraction']
        try:
            data = json.loads(source.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            item['capture_summary'] = {'error': 'Saved JSON could not be read for the index.'}
            continue
        coverage = data.get('coverage', {})
        images = data.get('images', [])
        docs = data.get('documents', [])
        tabs = data.get('browser', {}).get('tabs', [])
        item['capture_summary'] = {
            'tables': len(data.get('tables', [])),
            'images_saved': sum(i.get('status') == 'saved' for i in images),
            'images_discovered': len(images),
            'pdfs_saved': sum(bool(d.get('archive')) for d in docs),
            'pdfs_discovered': len(docs),
            'pdf_texts': sum(d.get('status') == 'processed' for d in docs),
            'tabs_captured': sum(t.get('status') == 'captured' for t in tabs),
            'unresolved': coverage.get('unresolved', []),
            'missing_fields': data.get('missing_fields', []),
            'has_archives': bool(data.get('source_archive')),
            'has_coverage': bool(coverage),
        }


def render_index(manifest):
    # Escape '<' to prevent source titles/URLs from closing the inert JSON block.
    initial = json.dumps(manifest, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return TEMPLATE.replace('__INITIAL_DATA__', initial)


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Assessment extraction library</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f7f5;color:#213d34;font:15px/1.55 system-ui,sans-serif}
main{max-width:1500px;margin:auto;padding:36px 28px}header{display:flex;justify-content:space-between;align-items:start;gap:24px}
h1{font:38px/1.2 Georgia,serif;margin:8px 0 12px}.eyebrow{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#547869}
p{margin:8px 0}.muted{color:#63756c;font-size:13px}.status{font-size:13px;background:#e4eee8;padding:8px 14px;border-radius:20px;white-space:nowrap}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:28px 0}.stat{padding:20px;background:white;border:1px solid #dce5de;border-radius:10px}.stat strong{display:block;font-size:30px}.stat span{font-size:13px;color:#63756c}
.tools{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:22px 0}input,select,button{font:inherit;padding:11px 14px;border:1px solid #becfc4;border-radius:6px;background:white;color:inherit}input{flex:1;min-width:220px}button{cursor:pointer}a{color:#216049;text-underline-offset:3px}nav{display:flex;flex-wrap:wrap;gap:20px;margin:18px 0}
.table-wrap{overflow:auto;border:1px solid #dce5de;border-radius:10px;background:white}table{border-collapse:collapse;width:100%;min-width:1000px}th{text-align:left;background:#eaf0ec;font-size:12px;color:#506c5d;letter-spacing:.4px}th,td{padding:16px 14px;border-bottom:1px solid #e3eae5;vertical-align:top}th:first-child{width:32%}td.title strong{display:block}td.title>a{font-size:12px}td.count{white-space:nowrap}td.links{min-width:210px}.links a{display:inline-block;margin:0 12px 8px 0;font-size:13px}.links a.primary{font-weight:700}.pill{display:inline-block;border-radius:5px;padding:3px 8px;font-size:12px;background:#edf1ee}.pill.saved{background:#e2f0e6;color:#225b3c}.pill.failed{background:#fce9e4;color:#8c3e2c}.pill.running{background:#fff1d4;color:#775716}
details{margin-top:10px;font-size:12px;color:#6e5841}summary{cursor:pointer}details ul{padding-left:18px;margin:6px 0}details li{margin:6px 0;overflow-wrap:anywhere}.note{border-left:3px solid #6a927c;padding:10px 16px;background:#ecf2ed}.empty{padding:30px;text-align:center}footer{padding-top:20px;color:#63756c;font-size:12px}@media(max-width:700px){main{padding:22px 16px}h1{font-size:30px}.stats{grid-template-columns:repeat(2,1fr)}header{display:block}.status{display:inline-block;margin-top:12px}}
</style></head><body><main>
<header><div><div class="eyebrow">Assessment source library</div><h1>All your extracted assessments</h1><p>Open each document to review its questions, source text, tables, images and original PDFs.</p></div><span id="run-state" class="status"></span></header>
<div class="stats"><div class="stat"><strong id="saved">0</strong><span>Documents saved</span></div><div class="stat"><strong id="remaining">0</strong><span>Still to process</span></div><div class="stat"><strong id="gaps">0</strong><span>Saved with capture gaps</span></div><div class="stat"><strong id="failed">0</strong><span>Extraction failures</span></div></div>
<p class="note">Saved means the available content was exported; it does not certify complete coverage. Image-based tables and graphs appear under <b>Images</b>. PDF links in each document download the original file.</p>
<nav><a href="summary.csv" download>Download summary CSV</a><a href="manifest.json">Batch details</a><a href="urls.txt">All input URLs</a></nav>
<div class="tools"><label for="search">Find assessment</label><input id="search" type="search" placeholder="Search name or URL…"><label for="filter">Show</label><select id="filter"><option value="all">All assessments</option><option value="extracted">Saved documents</option><option value="remaining">Still processing</option><option value="gaps">Capture gaps</option><option value="failed">Failures</option></select><button id="refresh" type="button">Refresh now</button></div>
<p id="shown" class="muted" aria-live="polite"></p><p id="refresh-state" class="muted" role="status"></p>
<div class="table-wrap"><table><thead><tr><th>Assessment</th><th>Status</th><th>Questions</th><th>Tables</th><th>Images<br>saved / found</th><th>PDFs<br>saved / found</th><th>Open content</th></tr></thead><tbody id="rows"></tbody></table></div>
<footer id="updated"></footer>
</main><script id="initial-data" type="application/json">__INITIAL_DATA__</script>
<script>
let data = JSON.parse(document.getElementById('initial-data').textContent);
const $ = id => document.getElementById(id);
function element(tag, text, className) { const node=document.createElement(tag); if(text!==undefined)node.textContent=String(text); if(className)node.className=className; return node; }
function safePath(path) {return typeof path==='string' && !path.startsWith('/') && !path.includes('..') && /^[a-zA-Z0-9_./-]+$/.test(path);}
function sourceLink(url) {try{return new URL(url).protocol==='https:';}catch{return false;}}
function link(parent, label, href, primary=false) {const a=element('a',label,primary?'primary':'');a.href=href;a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}
function hasGaps(item) {return Boolean(item.capture_summary?.error || item.capture_summary?.unresolved?.length || (item.coverage_issues||[]).some(x=>x!=='metadata_fields_unavailable'));}
function render() {
  const items=data.items||[], saved=items.filter(i=>i.status==='extracted');
  $('saved').textContent=saved.length+' / '+items.length;
  $('remaining').textContent=items.filter(i=>!['extracted','failed'].includes(i.status)).length;
  $('gaps').textContent=saved.filter(hasGaps).length;
  $('failed').textContent=items.filter(i=>i.status==='failed').length;
  $('run-state').textContent=data.run_status==='running'?'Batch processing':data.run_status==='finished'?'Batch finished':('Batch '+data.run_status);
  $('updated').textContent='Last checkpoint: '+new Date(data.updated_at).toLocaleString()+' · '+items.length+' input URLs';
  const query=$('search').value.trim().toLowerCase(), filter=$('filter').value;
  const shown=items.filter(i=>(!query||((i.title||'')+' '+i.url).toLowerCase().includes(query)) &&
    (filter==='all'||filter===i.status||(filter==='remaining'&&!['extracted','failed'].includes(i.status))||(filter==='gaps'&&i.status==='extracted'&&hasGaps(i))));
  $('shown').textContent=shown.length+' of '+items.length+' assessments shown';
  const fragment=document.createDocumentFragment();
  for(const item of shown){
    const tr=element('tr');
    const title=element('td',undefined,'title');
    const slug=item.url.replace(/\/$/,'').split('/').pop().replace(/-/g,' ');
    title.append(element('strong',item.title||slug));
    if(sourceLink(item.url))link(title,'Original page ↗',item.url);
    const c=item.capture_summary;
    if(item.status==='extracted'){
      const details=element('details');details.append(element('summary',hasGaps(item)?'View capture gaps and review notes':'View capture and review notes'));
      const list=element('ul');
      if(c){
        if(c.error)list.append(element('li',c.error));
        else list.append(element('li',c.tabs_captured+' tabs captured; '+c.pdf_texts+' PDFs with extracted text.'));
        for(const gap of c.unresolved||[]){
          const li=element('li',[gap.kind,gap.status,gap.error||gap.note||gap.title||''].filter(Boolean).join(' · '));
          if(gap.url && sourceLink(gap.url)){li.append(document.createTextNode(' '));link(li,'Source',gap.url);}
          list.append(li);
        }
        if(c.missing_fields?.length)list.append(element('li',c.missing_fields.length+' structured metadata fields unavailable; see the document for retained source text.'));
      }
      if(!item.question_count)list.append(element('li','No structured questionnaire was identified. Review the source document.'));
      for(const issue of item.coverage_issues||[]){if(issue!=='metadata_fields_unavailable'&&issue!=='unresolved_capture_gaps')list.append(element('li',issue.replace(/_/g,' ')));}
      list.append(element('li','Independent source review is still required.'));
      details.append(list);title.append(details);
    }
    if(item.error)title.append(element('p',item.error,'muted'));
    tr.append(title);
    const status=element('td');status.append(element('span',({extracted:'Saved',running:'Processing',pending:'Queued',failed:'Failed',interrupted:'Interrupted'})[item.status]||item.status,'pill '+(item.status==='extracted'?'saved':item.status)));tr.append(status);
    tr.append(element('td',item.status==='extracted'?item.question_count:'—','count'));
    tr.append(element('td',c&&!c.error?c.tables:'—','count'));
    tr.append(element('td',c&&!c.error?c.images_saved+' / '+c.images_discovered:'—','count'));
    tr.append(element('td',c&&!c.error?c.pdfs_saved+' / '+c.pdfs_discovered:'—','count'));
    const files=element('td',undefined,'links'), doc=item.files?.document;
    if(safePath(doc)){
      link(files,'Full document',doc,true);
      for(const [label,anchor] of [['Questions','questionnaire'],['Scoring','scoring'],['PDFs','documents']])link(files,label,doc+'#'+anchor);
      if(c?.tables)link(files,'Tables',doc+'#tables');
      if(c?.images_discovered)link(files,'Images',doc+'#images');
      if(c?.has_coverage)link(files,'Coverage',doc+'#coverage');
      if(c?.has_archives)link(files,'Page archive',doc+'#archive');
      link(files,'Review notes',doc+'#missing');
    }
    if(safePath(item.files?.extraction))link(files,'JSON',item.files.extraction);
    if(!files.children.length)files.append(element('span',item.status==='failed'?'See error details':'Available after extraction','muted'));
    tr.append(files);fragment.append(tr);
  }
  if(!shown.length){const row=element('tr'),cell=element('td','No assessments match your search.','empty');cell.colSpan=7;row.append(cell);fragment.append(row);}
  $('rows').replaceChildren(fragment);
}
let refreshing=false;
async function refresh(){
  if(refreshing)return;refreshing=true;
  try{
    const response=await fetch('manifest.json',{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);
    const next=await response.json();if(!Array.isArray(next.items))throw new Error('Invalid progress data');data=next;render();
    $('refresh-state').textContent=data.run_status==='running'?'Updates automatically every 30 seconds. Search and filters are preserved.':'Latest saved progress loaded.';
  }catch(error){$('refresh-state').textContent='Showing the saved snapshot. Live refresh is unavailable; open this page through the local preview server.';}
  finally{refreshing=false;}
}
$('search').addEventListener('input',render);$('filter').addEventListener('change',render);$('refresh').addEventListener('click',refresh);
render();refresh();setInterval(refresh,30000);
</script></body></html>'''
