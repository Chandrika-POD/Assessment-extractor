INDIVIDUAL ASSESSMENT REPORT CONFIGURATIONS — 2026-11-24

Open index.html to find all 186 individual JSON configurations.
assessments/: one portable source-specific authoring JSON per assessment.
all-assessment-report-configs.json: the same 186 objects in one bundle.
evidence/: source text, sample-table cells and chart geometry for review ONLY.
audits/: URL results, source hash checks, chart-type decisions and remaining exceptions.

The configurations embed questionnaires, draft scoring rules, source-specific page order,
plot kinds, axes, colours, metric candidates, table geometry, interpretation guidance,
variants and explicit missing-information policies. Three pre-existing AIS/RIS/DASS-21
profiles are preserved inside their respective configuration; they were not upgraded to
fully validated status. The previously authored YSEX-SF implementation is also retained.
No generic chart has been substituted for a source-specific chart.

These are NOT complete equivalents of the three implemented pilot renderers for all 186
assessments. A version-2 renderer, verified metric/series bindings, normative conversions,
static table transcription, dynamic interpretation and full visual comparison are still
required. Never import these drafts into an enabled production-report path. The files
explicitly set readyForApplicationImport=false and rendererEquivalent=false.

All 416 previously detected plot candidates were inspected visually; 77 response-table
regions were removed. Seven missed visual regions were added after reviewing every page
of reports whose earlier extraction detected no charts. This does not prove exhaustive
detection or exact dimensions on every other source page. Alternative report documents
remain separate; do not concatenate them into one patient report.

Runtime configuration contains no source URLs, absolute paths, PNG assets or reusable
sample patient narratives. Prior profile validation fixtures remain test evidence only. Evidence files contain public sample values for review only.
All 516 detected body raster fills were extracted as numeric colour stops. They require
background/series role review; no image file is needed for these fill styles.
No database or application files were changed. JSON alone does not implement a renderer.
