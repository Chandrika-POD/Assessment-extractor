# Refreshed assessment bundle, schema 2.2

Latest file: `assessment-exports/novopsych-all-186-assessments-refreshed-20261113.json`.
Download: `http://127.0.0.1:4185/novopsych-all-186-assessments-refreshed-20261113.json`.

The 13 November 2026 refresh retrieved all 186 public assessment pages and 349 of 353 linked PDF URLs. Every selected questionnaire that was previously extracted matches the archived PDF hash. The source refresh captures embedded HTML tab panels, fresh sections and tables, and supplementary PDF text. It does not claim to execute external interactive tools or recursively collect every linked website.

The JSON keeps all 186 records and 4,927 extracted fields. 185 records have questionnaire fields; SDQ remains a catalogue record requiring an appropriate authorized form and variant selection. Existing question IDs, answer option IDs, printed values and previous source content are preserved. Previous exports remain available.

## Repairs and scoring

- 93 option-cell reading-order/spacing repairs, shared YSEX response labels on 28 items, PARDI endpoint labels on 22 items, five clipped IRIS labels restored from primary source evidence, and LEC-5 multiple-selection inputs on 17 items: 165 recorded repair events.
- Every choice item now includes `options` with a nonempty `text`, `id`, original `printed_value`, source label, optional draft score, and rule membership. Numeric/text questions intentionally have no options and use `input_spec.answer_schema`.
- Where a PDF prints only endpoint words, intermediate numbers remain numeric labels. Words are not invented. Option IDs are stable identifiers, not numeric weights.
- There are 434 draft arithmetic rules across 141 assessments: the previous 15 rules plus 419 source-bound additions. Methods include `sum`, `mean`, and `count_threshold`. Each new rule retains source evidence, item membership, numeric encoding and a missing-answer policy.
- 44 records retain scoring/protocol guidance requiring further implementation or review. LEC-5 is separately marked as a descriptive exposure inventory without a formal numeric score. Even assessments with draft rules may still need norms, interpretation, branching or other algorithms implemented.

All `scoring.enabled` and `review.ready_for_clinical_use` flags remain false. Extraction and arithmetic tests do not establish clinical approval. Read `live-refresh-report-20261113.json` for record-level status and failed source URLs.

## Consumer contract

Validate each definition against `definition-v2.2.schema.json`. Render `questionnaire.items[].options[].text` for choices; store option IDs. For numeric/text responses, validate the answer against `input_spec.answer_schema`. Honor multiple selection and supplied conditional fields; additional branching review remains necessary.

For a reviewed rule, use its `item_ids`, `method`, `value_field`, `multiplier` and, where present, `threshold`, `operator` and `item_thresholds`. A displayed response number can already encode reverse scoring. Do not reverse again based only on wording or a `reverse_scored` flag. A count rule converts source values to binary endorsements before aggregation; summing inline option scores would be incorrect. Different rules may use the same items differently.

`source_formulas.evaluate` is a draft test evaluator. It returns no result for missing required answers or explicit NA. Source-specific partial-answer prorating is not assumed. Diagnostic flags, percentiles, normative transformations and clinical interpretations are not inferred from an arithmetic total. Keep unsupported rules disabled rather than treating absent scores as zero.

Fresh scoring guidance and tables remain in `scoring.source_guidance` and `scoring.source_tables`. Full PDF page text is in `source_documents`; supplemental documents and sample reports have `runtime_context_allowed: false`. Do not send the entire source archive to a conversational model as instructions. The JSON contains text and asset references, not embedded PDF/image binaries.

## Rebuild

Use Python 3.12 and `tools/assessment_repair/requirements.txt`. Run the earlier question recovery first if its input bundle does not exist. To rebuild from this saved refresh without network requests:

```bash
python3 tools/assessment_repair/build_refreshed_bundle.py \
  --project "$PWD" --work "$PWD/artifacts/live-refresh-20261113"
python3 -m unittest discover -s tools/assessment_repair -p test_live_refresh.py -v
python3 tools/assessment_repair/serve_downloads.py --port 4185
```

To retry failed requests in this refresh, run `refresh_sources.py --project "$PWD" --work "$PWD/artifacts/live-refresh-20261113"`. Successful downloads are cached. This preserves TLS, public-address validation and robots restrictions. For a genuinely new refresh, use a new work directory and re-audit the PDF evidence; do not silently reuse old label/caption audits against a changed questionnaire.

After downloads, run `extract_refreshed_pdf_text.py` with the same `--project` and `--work`. Native text uses PyMuPDF; scanned pages require Tesseract. The optional `--ocr-command`, `--ocr-data` and `--ocr-library` arguments support an unpacked OCR installation. The builder requires completed retrieval and parsed text for every downloaded nonsample PDF. `--allow-incomplete` is for local test builds only.

`artifacts/live-refresh-20261113` retains the manifest, downloaded assets, parsed pages, PDF text, source-caption audit and option-cell audit. `live-refresh-report-20261113.json` lists repairs and remaining gaps. Older exports and the interactive extractor are unchanged by this separate refresh workflow.
