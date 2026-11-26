# Assessment-extractor

## Current validated export — 18 November 2026

Use [assessment-exports/current/all-assessments.json](assessment-exports/current/all-assessments.json)
for later app integration. It preserves all 186 assessments, 4,927 response fields
and 729 draft rules, removes provider website links including the PDF URL fragment,
and adds report configuration for all 186 records: 183 numeric reports, one
descriptive checklist, one screening protocol and one unavailable questionnaire.
Every existing scoring rule and response field is mapped into the report contract.

The current export also includes version-bound scoring verification for every record,
selected primary-source benchmarks, and six corrected YES chart minimums.
Clinical approval is still pending; see
[the scoring verification summary](assessment-exports/current/scoring-verification-summary.json).

See [the current export guide](assessment-exports/current/README.md),
[validation results](assessment-exports/current/validation-report.json) and
[per-assessment readiness](assessment-exports/current/assessment-readiness.csv).
Clinical scoring remains disabled; independent review and app implementation are
still required. The download server below now lists only this current package.

Redundant distribution ZIPs, obsolete combined exports, duplicate audit outputs,
the earlier standalone prototype and caches were removed with a recovery archive.
Historical bundles still used by rebuild scripts/tests and referenced source assets
are retained. The current package's cleanup-manifest.json records the exact
removals and recovery archive location.


Paste a public assessment URL to create a visual document and JSON. Live extraction uses Playwright to open page tabs and saves discovered images and linked PDFs. NovoPsych assessment links are supported without adding each assessment to a list.

## Start

```bash
cd /home/chandrikak/Pod_Dev/assessment-url-preview
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
- Playwright and its Chromium browser. A local installation takes priority; this workspace can also reuse Playwright from `../pod-assessment-platform/node_modules/playwright` in the sibling project under `~/Pod_Dev` and the installed browser cache.
- To install independently: `npm install playwright`, then `npx playwright install chromium` in this folder.
- Optional `CHROMIUM_EXECUTABLE` specifies an installed Chromium executable.
- `pdftotext` (`poppler-utils` on Debian/Ubuntu) for text-based PDFs.
- No LLM or API key is required.

## Extraction behavior

The browser captures the visible page, clicks available tabs/accordions, and captures each visible panel. Source headings, paragraphs, tables, links and references are preserved. Sections are grouped into instructions, scoring, interpretation, psychometrics and references by their headings. Each tab has its own captured/unavailable status.

PDF links are discovered from the captured page. Discovered PDFs are processed within the documented collection budgets, prioritizing forms over sample reports. Numbered PDF items, wrapped question lines and printed response values are extracted when their layout is recognizable. Sample reports are kept as source text, but do not supply questionnaire items. The first questionnaire found supplies the main preview; additional forms remain separate under Documents.

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


## Batch extraction

The supplied 186-URL list is saved in `data/novopsych_assessment_urls.txt`.
Run all URLs sequentially, saving a checkpoint after each source:

```bash
python3 batch_extract.py --input data/novopsych_assessment_urls.txt --output artifacts/batches/novopsych-20261106
```

Repeat the same command to resume interrupted/pending sources. Successfully saved artifacts are verified by checksum and skipped. Use `--retry-failed` to retry failed sources; use a new output folder for a fresh capture. `--limit 2` limits an invocation for a smoke test. A file lock prevents two processes from writing the same run. Distinct URLs with the same slug receive different source keys.

Each URL has its own attempt folder containing `source_url.txt`, `extraction.json`, `document.html` and `status.json`. The batch creates `manifest.json`, `summary.csv`, `urls.txt` and an auto-refreshing `index.html`. Retrieval status is separate from coverage and review status: an extracted page can still have missing questions, failed tabs or unprocessed PDFs. Nothing is automatically approved for clinical use. Rich captures retain original page/tab HTML as encoded data, original PDF bytes, and embedded raster images in JSON and the HTML export. Archives include checksums. Source tables retain headers and cell spans.

For local browser monitoring:

```bash
python3 -m http.server 4181 --bind 127.0.0.1 --directory artifacts
```

Open http://127.0.0.1:4181/batches/novopsych-20261106/index.html. If a batch is already running, inspect this page instead of launching another process against the same output folder.

## Rich source capture

New live extractions include visible source tables, offline PNG/JPEG/GIF/WebP images, archived original PDFs, original HTML and captured tab snapshots, and a capture-coverage report. PDF downloads preserve diagrams and layout even when text parsing fails. Source HTML is downloaded as text, never executed in the preview. All discovered links remain listed.

The former three-PDF cutoff is removed. Budgets are 100 linked PDFs, 100 images / 40 MB total image bytes, and 3 MB per download. Every discovered resource beyond a budget remains listed with an explicit status. Other webpages are not recursively crawled. OCR, embedded video, canvas and inline SVG rendering remain unsupported and are flagged. Captured content still requires source review; successful retrieval does not certify complete coverage.

Old batches are snapshots and are not upgraded by opening them. Run a fresh capture in a new output folder to preserve the old results:

```bash
python3 batch_extract.py --input data/novopsych_assessment_urls.txt --output artifacts/batches/novopsych-rich-20261110
```

## Consolidated assessment workspace

The active assessment workflow is organized as follows:

```text
assessment-url-preview/
  server.py, extractor.py, ...     # Existing URL extraction app
  tools/assessment_repair/         # Offline cleanup, schema, validation, downloads
  assessment-registry/             # Saved repair evidence
  assessment-exports/current/      # Single current export, schema and validation
  assessment-exports/              # Retained rebuild inputs and source evidence
  artifacts/                      # Original batches and migration audit
```

The extraction app and the offline repair tools are separate steps. Moving these folders does not trigger extraction. Generated exports, evidence, binary assets, ZIPs and caches are ignored by Git; the scripts, schema and documentation can be committed normally.

### Open the existing download

From this repository directory:

```bash
python3 tools/assessment_repair/serve_downloads.py --port 4185
```

Open <http://127.0.0.1:4185/>. This serves the current combined JSON, schema and readiness report without fetching assessment pages. Stop it with Ctrl+C. If the server is already running, open the URL directly.

### Rebuild and validate the saved assessment drafts

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r tools/assessment_repair/requirements.txt
python3 tools/assessment_repair/build_bundle.py
python3 tools/assessment_repair/validate_bundle.py
```

This uses the local evidence; it does not re-scrape NovoPsych. The schema 2.0 combined file is `assessment-exports/novopsych-all-186-assessments-repaired-20261113.json`. The 186 records include 185 recovered questionnaires and one SDQ record awaiting form selection. All remain review drafts. See [repair workflow](tools/assessment_repair/README.md) for limitations and source requirements.

## Response structure repair (schema 2.1)

The initial schema 2.1 export is `assessment-exports/novopsych-all-186-assessments-final-20261113.json`. It defines 87 previously untyped fields and adds eight unnumbered PARDI measurement fields. It includes 186 draft records; 185 have input definitions for every extracted field. SDQ remains catalogue-only, awaiting an authorized digital questionnaire and variant selection. No clinical scoring is enabled.

The consumer must support numeric, text and multiple-selection inputs; a choice-only importer will still reject these fields. See [response import contract and rebuild instructions](tools/assessment_repair/RESPONSE_IMPORT.md). This older export is retained as a rebuild/test input; the download server lists only the current package.

## Recovered PDF question wording

The preceding export is `assessment-exports/novopsych-all-186-assessments-questions-recovered-20261113.json`. It corrects 47 question stems and restores their omitted first scale options across CSI-16, CCQ, BSL-23 and both Vanderbilt forms. Shared PDF prompts are attached to 53 items across CAST, PAS and CCQ. The 186 records retain 4,927 items, existing item/option IDs and disabled clinical scoring.

See [PDF question recovery and validation](tools/assessment_repair/QUESTION_RECOVERY.md). Run this recovery step after the earlier bundle/response-repair commands when rebuilding. The previous exports are retained.

## Live source refresh (schema 2.2)

The schema 2.2 combined JSON is `assessment-exports/novopsych-all-186-assessments-refreshed-20261113.json`. All 186 pages were refreshed, with 349 PDF downloads. The file preserves 4,927 items, fixes option labels and selection modes, and embeds displayable choices in each item. 141 records have draft arithmetic rules; 44 retain guidance needing further scoring implementation, and LEC-5 has no formal numeric score. SDQ still has no questionnaire. Clinical scoring remains disabled.

See [refresh results, import contract and rebuild commands](tools/assessment_repair/LIVE_REFRESH.md). The accompanying `live-refresh-report-20261113.json` records failures and remaining gaps.

## Definition and scoring repairs (schema 2.3)

The retained schema 2.3 rebuild input is `assessment-exports/novopsych-all-186-assessments-definition-repaired-20261114.json`. It preserves all 186 records, 4,927 fields and source material. It adds 295 draft calculation rules across 42 previously flagged records (including partial MAPsy coverage), for 729 rules across 183 records, plus an asQ screening protocol. WSAS question 1 and its missing non-working response are repaired. Conditional questions, signed composites, per-rule reversals, optional-item means and ORT column consistency now have explicit runtime support.

These are draft implementations. SDQ still lacks a selected questionnaire; MAPsy has partial construct coverage; normative conversions, WHODAS IRT, source conflicts and other remaining work are listed per record. No clinical scoring is enabled. See [definition repair details and consumer contract](tools/assessment_repair/DEFINITION_REPAIR.txt), and `assessment-exports/definition-repair-report-20261114.json` for all 44 audited records.

Rebuild from the saved source bundle without fetching pages:

```bash
python3 tools/assessment_repair/repair_definitions.py --project . --output assessment-exports/novopsych-all-186-assessments-definition-repaired-20261114.json
python3 -m unittest discover -s tools/assessment_repair -p 'test_*.py' -v
```

Use `definition_runtime.py` and `definition-v2.3.schema.json` when testing the new rules; earlier consumers do not support their conditions and transforms. The download page at <http://127.0.0.1:4185/> lists only the current package. Earlier bundles referenced by rebuild scripts and regression tests are retained as inputs.
