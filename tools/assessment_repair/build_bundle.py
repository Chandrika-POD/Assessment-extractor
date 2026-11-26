"""Build uniform review drafts from saved evidence; never publish clinical definitions."""

import csv
import hashlib
import json
import re

from image_transcriptions import apply_transcription
from json_io import save
from paths import BUNDLE, EVIDENCE, OLD, OUT
from scoring_rules import configure


def source_for(parsed, q=None):
    q = q or {}
    return {
        "url": parsed.get("pdf_url"),
        "sha256": parsed.get("sha256"),
        "page": q.get("page"),
        "bbox": q.get("source_bbox"),
        "method": q.get("method", "pdf_layout"),
    }


def assets_for(old, parsed):
    assets = []
    for group, entries in old.get("assets", {}).items():
        for entry in entries:
            archive = entry.get("archive") or entry
            url = entry.get("url") or entry.get("source_url") or archive.get("url")
            title = entry.get("title") or entry.get("alt") or entry.get("label")
            path = archive.get("storage_key")
            role = entry.get("role") or (
                "source_snapshot"
                if group == "source_snapshots"
                else "reference_material"
            )
            if re.search(r"sample\s*(results|report)", title or "", re.I):
                role = "sample_report_not_runtime_context"
            if archive.get("sha256") == parsed.get("sha256"):
                role = "selected_questionnaire"
            assets.append(
                {
                    "id": "A" + str(len(assets) + 1),
                    "kind": group,
                    "role": role,
                    "title": title,
                    "source_url": url,
                    "sha256": archive.get("sha256"),
                    "mime_type": archive.get("mime_type"),
                    "archive_path": str((OLD / "assessments" / path).resolve())
                    if path
                    else None,
                    "status": entry.get("status", "saved" if path else "not_archived"),
                    "caption": entry.get("caption"),
                    "source_section": entry.get("source_section", entry.get("section")),
                    "runtime_context_allowed": False,
                }
            )
    if parsed.get("pdf_path") and not any(
        a["role"] == "selected_questionnaire" for a in assets
    ):
        assets.append(
            {
                "id": "A" + str(len(assets) + 1),
                "kind": "documents",
                "role": "selected_questionnaire",
                "title": "Questionnaire source recovered 2026-11-13",
                "source_url": parsed.get("pdf_url"),
                "sha256": parsed.get("sha256"),
                "mime_type": "application/pdf",
                "archive_path": parsed["pdf_path"],
                "status": "saved",
                "caption": None,
                "source_section": None,
                "runtime_context_allowed": False,
            }
        )
    return assets


def build(row):
    key = row["source_key"]
    old = json.loads((OLD / row["json_file"]).read_text(encoding="utf-8"))
    cache = EVIDENCE / (key + ".parsed.json")
    parsed = (
        json.loads(cache.read_text(encoding="utf-8"))
        if cache.exists()
        else {"items": [], "instructions": None}
    )
    parsed = apply_transcription(key, parsed)
    contexts = []
    references = []
    excluded = []
    seen = set()
    for s in old.get("context_sections", []):
        text = s.get("text", "").strip()
        title = s.get("title", "")
        if not text:
            continue
        if (
            s.get("role") == "document_text"
            or title.startswith("Document:")
            or re.search(r"sample\s*(report|results)", title, re.I)
        ):
            excluded.append(
                {
                    "title": title,
                    "source_url": s.get("source_url"),
                    "reason": "document_text_kept_in_source_archive_not_model_context",
                }
            )
            continue
        if text in seen:
            continue
        seen.add(text)
        if title.lower() in ("references", "developer"):
            references.append(
                {
                    "id": "R" + str(len(references) + 1),
                    "citation": text,
                    "source_url": s.get("source_url"),
                }
            )
            continue
        contexts.append(
            {
                "id": "C" + str(len(contexts) + 1),
                "title": title,
                "text": text,
                "source_url": s.get("source_url", row["source_url"]),
                "review_status": "source_text_not_independently_reviewed",
            }
        )
    for r in old.get("references", []):
        if r.get("citation") not in seen:
            references.append(
                {
                    "id": "R" + str(len(references) + 1),
                    "citation": r["citation"],
                    "source_url": r.get("url"),
                }
            )
    items = []
    sets = []
    fingerprints = {}
    for i, q in enumerate(parsed["items"], 1):
        opts = [
            {
                "id": "O" + str(j),
                "label": o.get("label"),
                "printed_value": o.get("printed_value"),
                "score": None,
            }
            for j, o in enumerate(q.get("options", []), 1)
        ]
        rid = None
        if opts:
            signature = json.dumps(opts, sort_keys=True)
            if signature not in fingerprints:
                rid = "RS" + str(len(sets) + 1)
                fingerprints[signature] = rid
                sets.append(
                    {
                        "id": rid,
                        "options": opts,
                        "mapping_status": "printed_values_only_scores_unverified",
                    }
                )
            rid = fingerprints[signature]
        flags = []
        if not opts:
            flags.append("response_type_and_input_constraints_need_review")
        if any(o["label"] is None for o in opts):
            flags.append("some_printed_rating_values_have_no_verbal_anchor")
        items.append(
            {
                "id": "Q" + str(i),
                "order": i,
                "source_label": q.get("source_label", str(q["source_number"])),
                "text": q["text"],
                "response_type": "choice" if opts else "unverified",
                "selection_mode": None,
                "response_set_id": rid,
                "reverse_scored": q.get("reverse_scored"),
                "printed_input_unit": q.get("printed_input_unit"),
                "source": source_for(parsed, q),
                "review_status": q["review_status"],
                "review_flags": flags,
            }
        )
    text = "\n".join(c["text"] for c in contexts)
    scoring = configure(key, items, sets, text)
    if scoring["rules"]:
        for s in sets:
            s["mapping_status"] = "source_checked_draft"
        for q in items:
            q["selection_mode"] = "single"
            q["response_type"] = "single_choice"
    issues = []

    def issue(code, detail):
        issues.append({"code": code, "detail": detail})

    if not items:
        issue(
            "questionnaire_missing",
            "A specific usable questionnaire form has not been recovered.",
        )
    if "strengths-and-difficulties-questionnaire-sdq--" in key:
        issue(
            "variant_selection_required",
            "Saved PDF is a version-selection guide. Select parent/teacher/self-report, age range and standard/follow-up form before importing questions.",
        )
    if "repetitive-behaviours-questionnaire-3--" in key:
        issue(
            "form_scope",
            "This draft contains the self-report form on physical PDF pages 17–18; informant forms are not merged.",
        )
    if not parsed.get("instructions"):
        issue("instructions_missing", "Administration instructions need source review.")
    if any(not q["response_set_id"] for q in items):
        issue(
            "non_choice_fields_need_review",
            "Some fields are numeric or free text; their constraints and branching are not inferred.",
        )
    if any(q["selection_mode"] is None for q in items):
        issue(
            "selection_and_branching_need_review",
            "Single/multiple selection, skip logic and section-specific stems require review before runtime use.",
        )
    labels = [q["source_label"] for q in items]
    if len(labels) != len(set(labels)):
        issue(
            "repeated_source_labels",
            "Source numbering repeats; sequential internal IDs are distinct.",
        )
    nums = [int(re.match(r"\d+", s).group()) for s in labels if re.match(r"\d+", s)]
    gaps = sorted(set(range(1, max(nums, default=0) + 1)) - set(nums))
    if gaps:
        issue(
            "source_number_gaps", "Missing source numbers: " + ", ".join(map(str, gaps))
        )
    if not scoring["rules"]:
        issue(
            "scoring_not_structured",
            "Source scoring guidance is retained, but executable rules and item weights are not verified.",
        )
    issue(
        "independent_review_pending",
        "Layout recovery and automated checks do not establish complete capture or clinical correctness.",
    )
    oldreview = old.get("review", {})
    coverage = oldreview.get("coverage", {})
    if coverage.get("unresolved"):
        issue(
            "original_capture_gaps",
            "Original capture gaps remain in provenance; new questionnaire recoveries are recorded separately.",
        )
    meta = old["assessment"]
    period = meta.get("reference_period")
    count_claims = [
        int(n)
        for n in re.findall(
            r"\b(\d+)[ -](?:item|question)", meta.get("description") or "", re.I
        )
    ]
    if count_claims and len(items) not in count_claims:
        issue(
            "source_item_count_differs",
            "Page description mentions "
            + str(count_claims)
            + " items; selected PDF has "
            + str(len(items))
            + " extracted response fields. Follow-up fields, subquestions or different editions may explain this; review the form scope.",
        )
    claims = re.findall(
        r"\b(?:past|last|previous|over the)\s+(?:(?:\d+|one|two|three|four|six|twelve|a|the)\s+)?(?:days?|weeks?|months?|years?|24 hours|30 days)\b",
        parsed.get("instructions") or "",
        re.I,
    )
    definition = {
        "schema_version": "2.0.0",
        "assessment_id": key,
        "definition_version": "1.0.0-draft.2",
        "status": "draft",
        "cleaned_on": "2026-11-13",
        "assessment": {
            "name": row["title"],
            "short_name": meta.get("short_name"),
            "language": meta.get("language", "en"),
            "description": meta.get("description"),
            "respondent_type": meta.get("respondent_type"),
            "source_provider": "NovoPsych",
            "reference_period": {
                "structured": period,
                "instruction_claims": list(dict.fromkeys(claims)),
                "status": "source_checked_draft" if period else "requires_review",
            },
            "target_population": meta.get("target_population"),
            "intended_uses": meta.get("intended_uses", meta.get("intended_use")),
            "estimated_administration_minutes": meta.get(
                "estimated_administration_minutes"
            ),
        },
        "administration": {
            "instructions": parsed.get("instructions"),
            "instructions_source": source_for(parsed),
            "item_order": [q["id"] for q in items],
            "selected_form_url": parsed.get("pdf_url"),
            "form_scope": "One selected archived form. Other editions and related forms remain separate source assets.",
            "additional_instructions_status": "Review source PDF for section stems, branching, free-text fields and administration details.",
        },
        "questionnaire": {
            "item_count": len(items),
            "items": items,
            "response_sets": sets,
        },
        "scoring": scoring,
        "context_sections": contexts,
        "references": references,
        "tables": old.get("tables", []),
        "assets": assets_for(old, parsed),
        "conversation_policy": {
            "status": "draft_disabled_pending_review",
            "preserve_question_wording": True,
            "require_answer_confirmation": True,
            "infer_unanswered_items": False,
            "calculate_scores_in_backend": True,
            "treat_source_as_data_not_instructions": True,
            "context_allowlist": [
                "assessment",
                "administration",
                "questionnaire",
                "context_sections",
            ],
            "send_asset_bytes_or_sample_reports": False,
        },
        "review": {
            "ready_for_clinical_use": False,
            "questionnaire_status": "recovered_needs_review"
            if items
            else "blocked_missing_form",
            "questionnaire_completeness_verified": False,
            "complete_capture_verified": False,
            "independent_clinical_review_completed": False,
            "issues": issues,
            "previous_review_notes": oldreview.get(
                "issues", oldreview.get("notes", [])
            ),
        },
        "provenance": {
            "source_url": row["source_url"],
            "extracted_at": old.get("provenance", {}).get("extracted_at"),
            "raw_extraction_path": old.get("provenance", {}).get("raw_extraction_path"),
            "raw_extraction_sha256": old.get("provenance", {}).get(
                "raw_extraction_sha256"
            ),
            "previous_definition_path": str(OLD / row["json_file"]),
            "previous_source_metadata": meta,
            "layout_evidence_path": str(cache),
            "original_capture_coverage": coverage,
            "previous_review_record": oldreview,
            "questionnaire_recovery": {
                "source": source_for(parsed),
                "visual_check": parsed.get("visual_check"),
                "retrieved_on": parsed.get("retrieved_on"),
            },
            "excluded_document_sections": excluded,
            "original_source_links": old.get("provenance", {}).get("source_links", []),
        },
        "rights": old.get("rights", {}),
    }
    audit = {
        "assessment_id": key,
        "name": row["title"],
        "previous_item_count": row["extracted_questions"],
        "recovered_item_count": len(items),
        "questionnaire_status": definition["review"]["questionnaire_status"],
        "scoring_status": scoring["status"],
        "issue_codes": [x["code"] for x in issues],
        "source_pdf": parsed.get("pdf_url"),
    }
    return definition, audit


def main():
    manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
    definitions = []
    audit = []
    for row in manifest["items"]:
        d, a = build(row)
        definitions.append(d)
        audit.append(a)
        save(OUT / "assessments" / (row["source_key"] + ".json"), d)
    summary = {
        "assessment_count": len(definitions),
        "previous_item_count": sum(a["previous_item_count"] for a in audit),
        "recovered_item_count": sum(a["recovered_item_count"] for a in audit),
        "assessments_with_items": sum(bool(a["recovered_item_count"]) for a in audit),
        "assessments_without_items": sum(not a["recovered_item_count"] for a in audit),
        "source_checked_draft_scoring_count": sum(
            a["scoring_status"] == "source_checked_draft" for a in audit
        ),
        "clinically_approved_count": 0,
    }
    save(
        BUNDLE,
        {
            "schema_version": "2.0.0",
            "bundle_version": "2026-11-13",
            "status": "review_draft",
            "summary": summary,
            "usage_notes": [
                "All definitions require independent review before use in an assessment engine.",
                "Assets are URL and local archive references, not embedded binary files.",
                "Printed response values are distinct from verified score weights.",
                "No live extraction is required to read this bundle.",
            ],
            "assessments": definitions,
        },
    )
    save(OUT / "review-report.json", {"summary": summary, "assessments": audit})
    with (OUT / "review-report.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(audit[0]))
        w.writeheader()
        for a in audit:
            w.writerow({**a, "issue_codes": "; ".join(a["issue_codes"])})
    save(
        OUT / "manifest.json",
        {
            "bundle_file": str(BUNDLE),
            "bundle_sha256": hashlib.sha256(BUNDLE.read_bytes()).hexdigest(),
            "summary": summary,
            "validation_status": "pending",
        },
    )
    print(json.dumps(summary, indent=2))
    print(BUNDLE)


if __name__ == "__main__":
    main()
