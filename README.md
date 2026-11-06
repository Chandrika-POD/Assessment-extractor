# Assessment URL Preview

Paste a public assessment URL to create a visual document and JSON. Live extraction uses Playwright to open page tabs and follows up to three linked PDFs. NovoPsych assessment links are supported without adding each assessment to a list.

## Start

```bash
cd /home/chandrikak/POD/assessment-url-preview
python3 server.py
```

Open http://127.0.0.1:4177. After updating the code, stop the previous server with Ctrl+C and start it again. If the port is occupied, use `python3 server.py --port 4180` and open that port.

1. Paste a public assessment URL.
2. Keep **Live extraction**, **Open page tabs with Playwright**, and **Include linked PDFs** selected.
3. Click **Create assessment document**. The first browser extraction can take 2–4 minutes; public JavaScript/CSS resources are cached in memory for ten minutes.
4. Review the document, questions, source references, tab statuses and missing information.
5. Download **Document** (standalone HTML) or **JSON**. Use **Print / PDF** to save a PDF.

The default example is NovoPsych GAD-7. The same pipeline handles PHQ-9, DASS-21, ASRS-O and other public assessment pages. There is no instrument-specific list in the live extractor.

Verified on 6 November 2026: all public tabs/accordions captured for the four examples. The retrieved source PDFs produced GAD-7: 7 items / 28 choices; PHQ-9: 9 / 36; DASS-21: 21 / 84; ASRS-O: 18 / 90. PHQ-9 and ASRS-O PDFs required support for vertically centered item numbers; the retained live PDF text was reprocessed after that fix. One external reference PDF on the ASRS-O page failed retrieval; its main questionnaire and sample report were processed. The live GAD-7 browser UI and HTML/JSON/PDF downloads passed, along with 29 unit tests.

## Runtime requirements

- Python 3.10+ and Node.js.
- Playwright and its Chromium browser. This workspace reuses Playwright from `../assessment-database/node_modules/playwright` and the installed browser cache.
- To install independently: `npm install playwright`, then `npx playwright install chromium` in this folder.
- Optional `CHROMIUM_EXECUTABLE` specifies an installed Chromium executable.
- `pdftotext` (`poppler-utils` on Debian/Ubuntu) for text-based PDFs.
- No LLM or API key is required.

## Extraction behavior

The browser captures the visible page, clicks available tabs/accordions, and captures each visible panel. Source headings, paragraphs, tables, links and references are preserved. Sections are grouped into instructions, scoring, interpretation, psychometrics and references by their headings. Each tab has its own captured/unavailable status.

PDF links are discovered from the captured page. Up to three are processed, prioritizing forms over sample reports. Numbered PDF items, wrapped question lines and printed response values are extracted when their layout is recognizable. Sample reports are kept as source text, but do not supply questionnaire items. The first questionnaire found supplies the main preview; additional forms remain separate under Documents.

Live mode never substitutes the saved GAD-7/PHQ-9 library. Saved examples are available only through the explicit demo selection.

## Access and provenance

Public HTTP access and reproduction permissions are tracked separately. The previous mandatory permission-file gate has been removed from live public-page extraction. `policies.json` is retained as optional evidence for sources with recorded rights; an unlisted source is labelled `reproduction_permission: not_verified`, never approved automatically.

The extractor respects robots rules and stops at HTTP access restrictions. It does not log in, solve CAPTCHAs, submit questionnaires, or open account-only content. Public availability alone does not establish reuse rights. Review the exported rights metadata before reusing content.

Requests use validated HTTPS URLs and DNS addresses pinned to public IPs. Chromium receives source resources through that same Python transport: direct resource requests, cross-origin resources, WebSockets, forms and service workers are blocked. Rendering is bounded by time, resource count and response size. Only the local browser can call the API.

## Coverage limits

“Any URL” means the same extraction process can be attempted for new public assessment links. It does not guarantee that every site exposes every question, tab or document. Missing questions, blocked tabs and failed PDFs remain visible in the result.

- Image-only questionnaires and scanned PDFs require OCR, which is not included.
- Cross-origin scripts and dynamic API content may be unavailable in the bounded browser renderer.
- Automatic item extraction requires recognizable numbering or table headings; retain the source text for review.
- Response values are preserved, but item scores and reverse scoring are not inferred.
- This prototype does not perform clinical scoring or generate Excel/DOCX files.

## Files

- `server.py`: localhost API and static assets.
- `retrieval.py`: bounded public HTTPS retrieval, robots checks and optional rights evidence.
- `browser_capture.py` / `browser_capture.cjs`: Playwright rendering and tab capture through the pinned transport.
- `source_parser.py`: source sections, tables and PDF question parsing.
- `extractor.py`: source aggregation and explicit saved examples.
- `document.py`: escaped standalone HTML export.
- `static/`: browser UI.

## Checks

```bash
python3 -m unittest discover -s tests -v
```

Optional live NovoPsych tests (real network and browser access):

```bash
python3 tests/live_novopsych.py
```

These save HTML/JSON files for GAD-7, PHQ-9, DASS-21 and ASRS-O in `artifacts/`. Optional browser UI checks use `node tests/browser.cjs`; set `BASE_URL` for a non-default port and `CHROMIUM_EXECUTABLE` if needed. Artifacts are local and ignored by git.
