# PDF question recovery, 13 November 2026

The latest combined file is `assessment-exports/novopsych-all-186-assessments-questions-recovered-20261113.json`. It supersedes the earlier `final-20261113.json` export, which is retained as the repair input and comparison snapshot.

The PDF audit found a layout error: when a question appeared above a horizontal scale, the original table parser treated the first answer cell as the question and omitted that option from the response set. The repair uses the archived PDF's question coordinates and verifies its SHA-256 before applying the reviewed corrections.

| Assessment | Corrected items |
| --- | ---: |
| CSI-16 | 6 |
| CCQ | 24 |
| BSL-23 | 1 |
| Vanderbilt Teacher | 8 |
| Vanderbilt Parent | 8 |

Each of the 47 items now includes the full scale, including its previously omitted first option. CSI-16's six semantic differential items use the actual shared PDF instruction and their distinct endpoint labels. CCQ's reversed printed scale is retained in its original order without inferring scoring. Shared source prompts are attached to 53 items across CAST, PAS and CCQ, including the CCQ four-week timeframe.

The bundle still has 186 records and 4,927 items. These are wording/option repairs to existing items, not newly numbered questions. Existing item IDs and existing option ID meanings are preserved. A restored option receives a new ID and is placed first in the display order. Resolve each item's `response_set_id`; do not assume an option's ID suffix is its score or display position. Original response sets remain available for comparison.

Changed records use `definition_version: 1.0.0-draft.4`. Schema 2.1 accepts both draft.3 and draft.4. The top-level `bundle_version` identifies this revision as `2026-11-13-pdf-question-recovery`. Per-item provenance includes the previous text, PDF hash, source page and coordinates.

The audit checked numbered-question candidates and text outside extracted row bounds across the selected downloaded questionnaires. The remaining flagged numbering cases were split printed numbers, BAM's lettered subitems, response values or references. These checks do not prove exhaustive coverage of every PDF layout, OCR page or supplemental document. SDQ still lacks an authorized digital questionnaire; clinical scoring and completeness verification remain disabled.

From the repository root, with the repair dependencies installed:

```bash
python3 tools/assessment_repair/recover_pdf_questions.py
python3 tools/assessment_repair/test_question_recovery.py
python3 tools/assessment_repair/serve_downloads.py --port 4185
```

This step reads the existing `final-20261113.json` and downloaded PDFs. It does not fetch webpages. For a full rebuild, run the earlier bundle and response-repair steps first, then this recovery step. The localhost download page lists the newest file first. Audit evidence is under `artifacts/question-audit-20261113/`, and the downloadable change report is `assessment-exports/question-recovery-report-20261113.json`.
