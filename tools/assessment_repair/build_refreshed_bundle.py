"""Build a portable response/scoring review bundle from a completed live refresh."""

import argparse
import copy
import json
import re
from pathlib import Path

from option_repairs import option_repairs
from reviewed_live_rules import additions
from source_formulas import compile_formulas

INPUT_NAME = "novopsych-all-186-assessments-questions-recovered-20261113.json"
OUTPUT_NAME = "novopsych-all-186-assessments-refreshed-20261113.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def signature(rule):
    return (
        rule["method"],
        tuple(rule["item_ids"]),
        rule.get("multiplier", 1),
        rule.get("threshold"),
        rule.get("operator"),
        tuple(sorted(rule.get("item_thresholds", {}).items())),
    )


def build(project, work, allow_incomplete=False):
    previous = read(project / "assessment-exports" / INPUT_NAME)
    manifest = read(work / "manifest.json")
    if manifest["status"] != "finished" and not allow_incomplete:
        raise ValueError("Live retrieval has not finished")
    captions = {r["id"]: r["captions"] for r in read(work / "score-captions.json")}
    label_audit = read(work / "cell-label-audit.json")
    changes = label_audit["changes"]
    rows = []
    report = []
    all_changes = []
    for original in previous["assessments"]:
        a = copy.deepcopy(original)
        key = a["assessment_id"]
        url = a["provenance"]["source_url"]
        a["schema_version"] = "2.2.0"
        a["definition_version"] = "1.0.0-draft.5"
        page = manifest["pages"].get(
            url, {"status": "not_retrieved", "requested_url": url}
        )
        parsed = (
            read(work / "parsed-pages" / (key + ".json"))
            if page["status"] == "retrieved"
            else None
        )
        selected = a["source_documents"][0] if a["source_documents"] else None
        selected_check = manifest["pdfs"].get(selected["url"], {}) if selected else {}
        if selected_check.get("matches_archived_pdf") is False:
            raise ValueError(
                "Selected questionnaire changed; do not apply old edition repairs: "
                + key
            )
        fixes = option_repairs(a, changes)
        all_changes.extend({"assessment_id": key, **r} for r in fixes)
        related = [
            {"url": u, **d}
            for u, d in manifest["pdfs"].items()
            if key in d.get("assessment_ids", [])
        ]
        a["source_refresh"] = {
            "retrieved_at": page.get("retrieved_at"),
            "page_status": page["status"],
            "page_sha256": page.get("sha256"),
            "page_url": page.get("resolved_url", url),
            "capture_method": parsed.get("capture_method") if parsed else None,
            "embedded_tab_panel_count": parsed.get("panel_count") if parsed else None,
            "page_error": page.get("error"),
            "selected_questionnaire": selected_check,
            "documents": related,
            "sections": parsed["sections"] if parsed else [],
            "tables": parsed["tables"] if parsed else [],
            "coverage_note": "Fresh HTML includes embedded tab panels. External interactive media and every linked website are not recursively captured.",
        }
        if parsed:
            existing = {(c["title"], c["text"]) for c in a["context_sections"]}
            for c in parsed["sections"]:
                if (c["title"], c["text"]) not in existing and c["text"].strip():
                    a["context_sections"].append(
                        {
                            "id": "LIVE_C" + str(len(a["context_sections"]) + 1),
                            "title": c["title"],
                            "text": c["text"],
                            "source_url": c["source_url"],
                            "review_status": "fresh_source_text_needs_review",
                        }
                    )
                    existing.add((c["title"], c["text"]))
            seen_tables = {json.dumps(t, sort_keys=True) for t in a["tables"]}
            for t in parsed["tables"]:
                if json.dumps(t, sort_keys=True) not in seen_tables:
                    a["tables"].append(t)
        document_hashes = {d["sha256"] for d in a["source_documents"]}
        for d in related:
            if (
                d["status"] != "retrieved"
                or d["sha256"] in document_hashes
                or "sample" in d["url"].lower()
            ):
                continue
            cached = work / "pdf-text" / (d["sha256"] + ".json")
            if not cached.exists():
                if allow_incomplete:
                    continue
                raise ValueError("Downloaded PDF text not yet processed: " + d["url"])
            text = read(cached)
            a["source_documents"].append(
                {
                    "id": "live_pdf_" + str(len(a["source_documents"]) + 1),
                    "role": "supplemental_source_document",
                    "url": d["url"],
                    "sha256": d["sha256"],
                    "archive_path": d["path"],
                    "runtime_context_allowed": False,
                    "source_titles": d.get("roles", []),
                    **text,
                }
            )
            document_hashes.add(d["sha256"])
        for d in related:
            if d["status"] == "retrieved" and not any(
                asset.get("sha256") == d["sha256"] for asset in a["assets"]
            ):
                a["assets"].append(
                    {
                        "id": "LIVE_A" + str(len(a["assets"]) + 1),
                        "kind": "documents",
                        "role": "sample_report_not_runtime_context"
                        if "sample" in d["url"].lower()
                        else "reference_material",
                        "source_url": d["url"],
                        "sha256": d["sha256"],
                        "archive_path": d["path"],
                        "mime_type": d["mime_type"],
                        "status": "saved",
                        "runtime_context_allowed": False,
                    }
                )
        source_caps = (
            [
                {**c, "url": selected["url"], "sha256": selected["sha256"]}
                for c in captions[key]
            ]
            if selected
            else []
        )
        arithmetic, pending = compile_formulas(a, source_caps)
        if parsed:
            arithmetic.extend(
                additions(
                    a,
                    parsed["sections"],
                    {
                        "url": url,
                        "sha256": page["sha256"],
                        "retrieved_at": page["retrieved_at"],
                    },
                )
            )
        old_signatures = {signature(r) for r in a["scoring"]["rules"]}
        new = []
        for r in arithmetic:
            if signature(r) not in old_signatures:
                a["scoring"]["rules"].append(r)
                new.append(r)
                old_signatures.add(signature(r))
        a["scoring"]["source_guidance"] = (
            [
                c
                for c in parsed["sections"]
                if re.search(
                    r"scor|interpret|cut.?off|norm|percentile",
                    c["title"],
                    re.IGNORECASE,
                )
            ]
            if parsed
            else []
        )
        a["scoring"]["source_tables"] = parsed["tables"] if parsed else []
        a["scoring"]["unparsed_pdf_expressions"] = pending
        a["scoring"]["enabled"] = False
        a["scoring"]["calculation_status"] = (
            "draft_rules_available" if a["scoring"]["rules"] else "source_guidance_only"
        )
        if new and not original["scoring"]["rules"]:
            a["scoring"]["status"] = "source_arithmetic_draft"
        if key.startswith("life-events-checklist"):
            a["scoring"]["calculation_status"] = "not_applicable_no_formal_scoring"
            a["scoring"]["status"] = "descriptive_exposure_inventory"
        a["scoring"]["coverage"] = (
            "Implemented formulas have explicit item membership and numeric source evidence. Remaining expressions, diagnostic algorithms, percentiles, custom missing-answer policies and interpretation require review."
        )
        a["scoring"]["disabled_reason"] = (
            "Review draft: source arithmetic is extracted and tested, but clinical publication remains disabled."
        )
        a["scoring"]["reverse_scoring_policy"] = (
            "Printed values may already encode reverse scoring. Evaluate each rule once using its value_field; never reverse again solely because reverse_scored is true."
        )
        used = {q["id"]: [] for q in a["questionnaire"]["items"]}
        for r in a["scoring"]["rules"]:
            for iid in r["item_ids"]:
                used[iid].append(r["id"])
        sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
        numeric_rule_items = {
            iid
            for r in a["scoring"]["rules"]
            if r.get("value_field") == "printed_value"
            for iid in r["item_ids"]
        }
        for q in a["questionnaire"]["items"]:
            opts = sets[q["response_set_id"]]["options"] if q["response_set_id"] else []
            if q["id"] in numeric_rule_items:
                for o in opts:
                    if o["score"] is None:
                        o["score"] = o["printed_value"]
                if (
                    sets[q["response_set_id"]]["mapping_status"]
                    == "printed_values_only_scores_unverified"
                ):
                    sets[q["response_set_id"]]["mapping_status"] = (
                        "source_arithmetic_draft"
                    )
            q["options"] = [
                {
                    "id": o["id"],
                    "text": o["display_label"],
                    "source_label": o["label"],
                    "label_origin": o["display_label_origin"],
                    "printed_value": o["printed_value"],
                    "score": o["score"] if used[q["id"]] else None,
                    "score_status": "draft_rule_value"
                    if used[q["id"]] and o["score"] is not None
                    else "not_assigned",
                    "used_by_scoring_rules": used[q["id"]],
                }
                for o in opts
            ]
            q["score_encoding"] = (
                "Evaluate explicit scoring rules; printed reverse-coded values are used once."
                if used[q["id"]]
                else "No numeric scoring rule is assigned to this item."
            )
        # Some sets are shared with later scored items; resync inline snapshots after all weights exist.
        for q in a["questionnaire"]["items"]:
            if q["response_set_id"] and used[q["id"]]:
                for inline, o in zip(
                    q["options"], sets[q["response_set_id"]]["options"]
                ):
                    inline["score"] = o["score"]
                    inline["score_status"] = (
                        "draft_rule_value" if o["score"] is not None else "not_assigned"
                    )
        a["review"]["ready_for_clinical_use"] = False
        a["review"]["questionnaire_completeness_verified"] = False
        a["review"]["required_input_widgets"] = sorted(
            {q["input_spec"]["kind"] for q in a["questionnaire"]["items"]}
        )
        a["review"]["option_refresh"] = {
            "corrected_cells_or_fields": len(fixes),
            "unrenderable_option_count": sum(
                not o["text"] for q in a["questionnaire"]["items"] for o in q["options"]
            ),
            "numeric_only_options_are_not_missing": True,
            "selection_modes_still_needing_review": sum(
                bool(q["input_spec"].get("selection_mode_review_required"))
                for q in a["questionnaire"]["items"]
            ),
        }
        a["provenance"]["live_refresh"] = {
            "date": "2026-11-13",
            "previous_bundle": INPUT_NAME,
            "corrections": fixes,
        }
        row = {
            "assessment_id": key,
            "name": a["assessment"]["name"],
            "item_count": len(a["questionnaire"]["items"]),
            "page_status": page["status"],
            "selected_pdf_matches_archive": selected_check.get("matches_archived_pdf"),
            "option_corrections": len(fixes),
            "new_arithmetic_rules": len(new),
            "total_draft_rules": len(a["scoring"]["rules"]),
            "scoring_status": a["scoring"]["calculation_status"],
            "unparsed_pdf_caption_count": len(pending),
            "pdf_failures": sum(d["status"] != "retrieved" for d in related),
            "unrenderable_options": a["review"]["option_refresh"][
                "unrenderable_option_count"
            ],
        }
        rows.append(a)
        report.append(row)
    summary = {
        **previous["summary"],
        "live_pages_retrieved": sum(
            d["status"] == "retrieved" for d in manifest["pages"].values()
        ),
        "live_pdfs_retrieved": sum(
            d["status"] == "retrieved" for d in manifest["pdfs"].values()
        ),
        "live_pdf_failures": sum(
            d["status"] != "retrieved" for d in manifest["pdfs"].values()
        ),
        "option_correction_events": len(all_changes),
        "new_source_arithmetic_rules": sum(r["new_arithmetic_rules"] for r in report),
        "assessments_with_draft_rules": sum(bool(a["scoring"]["rules"]) for a in rows),
        "assessments_with_source_guidance_only": sum(
            a["scoring"]["calculation_status"] == "source_guidance_only" for a in rows
        ),
        "unrenderable_option_count": sum(r["unrenderable_options"] for r in report),
    }
    final = {
        "schema_version": "2.2.0",
        "bundle_version": "2026-11-13-live-refresh",
        "status": "review_draft",
        "summary": summary,
        "import_contract": {
            **previous["import_contract"],
            "schema_version": "2.2.0",
            "inline_options": "Each item has options with nonempty text. Numeric/text inputs have an empty options list and use input_spec.",
            "scoring": "Use scoring.rules, including method, item_ids, value_field, multiplier and per-item thresholds. Do not sum every field or use option IDs as numeric weights.",
            "supported_scoring_methods": ["sum", "mean", "count_threshold"],
            "unimplemented_scoring": "source_guidance and unparsed_pdf_expressions are evidence, not executable formulas. Some unparsed captions have manually implemented equivalents in rules.",
            "missing_answers": "Draft evaluator withholds incomplete results. NA is not numeric zero. Source-specific prorating is not assumed.",
            "version_notice": "Schema 2.2 adds inline options, source refresh evidence and arithmetic methods; update a consumer that only supports sum.",
        },
        "usage_notes": previous["usage_notes"]
        + [
            "All content remains a review draft. Fresh source retrieval and tests do not establish full clinical scoring coverage."
        ],
        "assessments": rows,
    }
    audit = {
        "summary": summary,
        "assessments": report,
        "option_changes": all_changes,
        "cell_audit": {
            "checked": label_audit["checked"],
            "numeric_mismatches": len(label_audit["mismatches"]),
        },
        "source_manifest": str(work / "manifest.json"),
        "failed_sources": [
            {"url": url, **entry}
            for group in ["pages", "pdfs"]
            for url, entry in manifest[group].items()
            if entry["status"] != "retrieved"
        ],
    }
    return final, audit


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Local test builds only; not a final export",
    )
    args = p.parse_args()
    result, report = build(args.project, args.work, args.allow_incomplete)
    output = args.output or args.project / "assessment-exports" / OUTPUT_NAME
    save(output, result)
    save(output.with_name("live-refresh-report-20261113.json"), report)
    print(json.dumps(result["summary"], indent=2))
    print(output)


if __name__ == "__main__":
    main()
