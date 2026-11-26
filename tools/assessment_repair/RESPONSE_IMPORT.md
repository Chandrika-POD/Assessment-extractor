# Response structure repair: schema 2.1

The latest combined export is `assessment-exports/novopsych-all-186-assessments-final-20261113.json`. It contains 186 draft records and 4,927 extracted fields. Of these, 185 records have input definitions for every extracted field. This is a structural check, not a claim that every source detail or clinical rule has been verified.

The previous import treated written answers, day counts and a checkbox group as missing response sets. This revision defines 87 such fields and adds eight unnumbered height/weight fields across the two PARDI forms. The 24 affected PDF URLs were fetched again and matched the archived SHA-256 hashes. Existing context sections, tables, references and scoring definitions are retained. Scoring stays disabled.

## Importing answers

Read each item's `input_spec.answer_schema` as a JSON Schema for its answer. Do not require a response set for every item.

| Response type | Input | Saved value |
| --- | --- | --- |
| `choice`, `single_choice` | Source response set | Option ID string |
| `multiple_choice` | Checkboxes | Array of unique option IDs |
| `integer` | Whole-number field | JSON integer |
| `number` | Numeric field permitting decimals | JSON number |
| `text` | Written response | Nonempty string |

For example, a day count with an explicit 30-day window has this input definition:

```json
{
  "response_type": "integer",
  "response_set_id": null,
  "input_spec": {
    "kind": "integer",
    "unit": "days",
    "answer_schema": {"type": "integer", "minimum": 0, "maximum": 30}
  }
}
```

Render options using `display_label`. Where a PDF labels only scale endpoints, intermediate options display their printed number; no verbal labels were invented. Preserve option IDs, not display text, as answers.

Use `display_if` for supplied field dependencies. Missing dependency answers leave eligibility unresolved. The PARDI height fields depend on the selected unit, and the weight field has `unit_from_item` with the source unit mapping. Preserve the existing question IDs; additional fields use IDs such as `Q1_height_cm`.

Keep unanswered/skipped status separate from a numeric zero. Allow the string `NA` only where it is explicitly present in the answer schema. For the MAPsy substance checkbox group, the schema disallows selecting "none" together with other substances.

`selection_mode_review_required` marks original choice fields whose selection mode still needs source review. Full branching and clinical scoring also need instrument review. A choice-only importer will still reject numeric/text fields until it implements these types; this export does not change the Assessment Library application.

## Source text and remaining limitations

`source_documents` retains text for 432 pages of the selected questionnaire-source PDFs, including OCR on 14 pages. Source hashes and archive paths allow comparison with the originals. OCR is explicitly marked for review. Images and diagrams remain in the original assets; the text is not a validated interpretation of them. Supplemental linked research PDFs and every website resource are not certified complete by this repair.

The SDQ download from NovoPsych is a version-selection guide, not its questionnaire. Its record has no invented questions and remains catalogue-only. It includes the [publisher's form index](https://www.sdqinfo.org/py/sdqinfo/b0.py), the required respondent/age variant, and the [publisher's electronic-use authorization notice](https://www.sdqinfo.org/).

## Rebuild and validate

Run from the repository root with `tools/assessment_repair/requirements.txt` installed. `pdftotext` must be available. The saved PDF-text cache makes this rebuild offline:

```bash
python3 tools/assessment_repair/complete_response_bundle.py --work artifacts/response-repair-20261113
python3 tools/assessment_repair/test_response_bundle.py
python3 tools/assessment_repair/serve_downloads.py --port 4185
```

Open <http://127.0.0.1:4185/> to download the combined JSON. Reading or downloading it does not run extraction.

For a fresh text cache, install Tesseract with English data and pass `--ocr-command /path/to/tesseract`. Optional `--ocr-data` and `--ocr-library` flags support a separately installed OCR runtime. Missing or failed OCR remains explicitly flagged. The checked PDF hashes and recorded live checks accompany the scripts; changed PDFs need new review before overrides can be reused.

The previous schema 2.0 bundle is retained under its original filename. Use the new `final-20261113.json` file for this revision; "final" identifies the delivered export, not clinical approval.
