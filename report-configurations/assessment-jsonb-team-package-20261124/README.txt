ASSESSMENT JSONB TEAM HANDOFF — 2026-11-24

CONTENTS
assessments/: 186 individual JSON files, one complete extracted configuration draft per assessment.
assessment-report-config.schema.json: JSON Schema for validating configuration structure.
manifest.json: titles, assessment IDs, source definition versions, draft status and file checksums.
SHA256SUMS.txt: checksums for all other package files.

JSONB STORAGE
JSONB is PostgreSQL's internal storage type; .json is the portable exchange format.
For each assessment file, parse the full JSON object and store it in a config JSONB column.
Do not store only the filename/path, and do not put all assessments in one database row.
The manifest config_file paths are package navigation metadata, not runtime dependencies.
Recommended row fields: assessment_id, version, status, config, checksum, created_at, validated_at.
Use an existing suitable table; this package does not create tables or change a database.
Enforce uniqueness of (assessment_id, version). Assign a new version when content changes;
do not overwrite a published version. The supplied definitionVersion comes from the source
questionnaire definition and may not uniquely version subsequent report-layout changes.
Use draft status on import. Preserve all disabled rules and readiness flags inside config.
Do not set validated_at based on structural validation alone.
Patient responses/results belong in separate records. Sessions should reference the exact
published configuration version. Query and render only explicitly enabled, validated versions.
Use parameterized database inserts and a transaction; check existing versions before importing.
The recorded SHA256 is over original UTF-8 file bytes. JSONB reserialization may differ, so
verify it against the original file before import, not against database-generated JSON text.

CURRENT READINESS
All 186 files passed JSON Schema validation and matched source-manifest checksums during packaging.
All 186 remain drafts; zero are marked readyForApplicationImport in this package.
These are not 186 finished, clinically approved or renderer-equivalent implementations.
Missing score-to-plot bindings, percentile/normative conversions, table semantics, interpretation
rules and report-variant logic must be resolved where flagged in each file's exceptions.
A compatible version-2 application renderer and per-assessment report comparison are required.
AIS, RIS and DASS-21 retain their earlier dedicated profiles as embedded reference content;
the enclosing draft configurations have not been validated for direct application import.
Some preserved pilot profiles include sample validation fixtures: these are test evidence,
not patient records and must not be used as a current patient's answers or scores.
No real patient records are added to this handoff.

RUNTIME DESIGN
The intended runtime uses database configuration, patient responses and application code.
No archived PDF/PNG files or extraction-folder access is required by the configuration contract.
This package does not include source evidence archives, report URLs, PDF/PNG files or the
combined duplicate bundle. Source identity hashes are retained in individual configurations.
No application, database or source configuration was modified by creating this package.
