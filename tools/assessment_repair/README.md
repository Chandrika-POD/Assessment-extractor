# Assessment JSON repair

For the latest schema 2.2 export and refreshed source evidence, see [LIVE_REFRESH.md](LIVE_REFRESH.md). The instructions below describe the earlier base repair stage.

This creates a uniform **review draft**, not clinically approved definitions. The previous exports and original extraction repository are preserved.

The source is the saved `cleaned-assessments-20261112` asset archive. PDF table geometry separates question cells from response values; stacked rating forms are handled separately. This avoids treating rating anchors and bibliography entries as questions. CORE-10, CORE-OM, YP-CORE and the RBQ-3 self-report appendix have hash-bound transcriptions checked against rendered form images. VQ and RBQ source PDFs recovered on 2026-11-13 are retained under `repair-20261113/evidence`.

The output uses one schema, including GAD-7. It retains assessment context, reference citations, source tables and asset references. Original full-page captures and PDF binaries remain in the archive. Sample report document text is excluded from the model context. Assets are references, not embedded binary content; downloading the JSON alone does not download the PDF/image archive.

## Rebuild and test

Python 3.12, the packages in this folder's `requirements.txt`, and Poppler `pdftotext` are required. Install dependencies from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r tools/assessment_repair/requirements.txt
```

All directory locations come from `paths.py`, relative to the repository. No hardcoded home-directory path is required by the code. Saved evidence and exported JSON retain absolute provenance paths, which must be migrated if the repository is moved again.

From the repository root:

```bash
python3 tools/assessment_repair/build_bundle.py
python3 tools/assessment_repair/validate_bundle.py
```

`build_bundle.py` reads the durable parsed evidence and image transcriptions. `inventory.py` can re-run layout extraction from the saved assets without contacting NovoPsych. It preserves separately recovered VQ/RBQ evidence when the old manifest has no usable PDF. Changing source PDF versions requires rechecking the hash-bound transcriptions.

The bundle is written to `assessment-exports/novopsych-all-186-assessments-repaired-20261113.json`. Individual definitions, a CSV/JSON review report and manifest are in the adjacent `repaired-assessments-20261113` directory. `definition.schema.json` documents the common structure.

## Review requirements

- SDQ remains blocked because the saved source is a version guide. Choose age range, respondent and standard/follow-up form before adding its questionnaire.
- Printed values are not automatically treated as scoring weights. Eight instruments have explicitly implemented draft formulas; the others retain source guidance and require rule review. No scoring definition is enabled for clinical use.
- The scoring helper is a test harness. Missing required answers withhold a result; this conservative application choice does not override source prorating rules. Percentiles are not inferred.
- Numeric/free-response constraints, section stems, conditional questions and selection modes require review. A recovered field count does not prove completeness. Extra follow-up fields and subquestions can differ from the instrument's nominal item count.
- Original extraction gaps and source discrepancies remain in provenance. A schema pass does not establish clinical validity or full website capture.

## Download locally

```bash
python3 tools/assessment_repair/serve_downloads.py --port 4185
```

Open `http://127.0.0.1:4185/` in a browser on this computer. Stop the server with Ctrl+C. This only serves saved files; it does not re-extract assessments.
