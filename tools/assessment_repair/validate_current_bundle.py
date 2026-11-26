"""Validate a distribution bundle without enabling clinical use or fetching URLs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from export_clean_content import HOST, FRAGMENT, check_preservation
from scoring_verification import verification_errors


def report_errors(a):
    """Cross-check report configuration against this exact instrument."""
    errors = []
    c = a.get("reporting")
    if not c:
        return ["Missing report configuration"]
    rules = {r["id"]: r for r in a["scoring"]["rules"]}
    qs = {q["id"]: q for q in a["questionnaire"]["items"]}

    def require(ok, message):
        if not ok:
            errors.append(message)

    metrics = c["metrics"]
    require([m["rule_id"] for m in metrics] == list(rules), "Report must include every rule exactly once")
    require(c["coverage"]["rules_included"] == list(rules), "Coverage rule list mismatch")
    require(c["coverage"]["numeric_rule_count"] == len(rules), "Coverage rule count mismatch")
    require(c["coverage"]["questionnaire_available"] == bool(qs), "Questionnaire availability mismatch")
    expected_mode = ("unavailable" if not qs else "numeric_scores" if rules else
                     "screening_protocol" if a["scoring"].get("protocol") else "descriptive_responses")
    require(c["mode"] == expected_mode, "Incorrect report mode")
    require(not c["clinical_scoring_enabled"], "Draft clinical scoring must stay disabled")
    require(not c["percentiles"]["enabled"], "No verified percentile mapping is available")
    require(not c["interpretation"]["combine_metrics_into_new_total"], "Synthetic totals prohibited")
    require(c["coverage"]["missing_direction_rule_ids"] ==
            [m["rule_id"] for m in metrics if m["favourable_direction"] is None], "Direction coverage mismatch")

    def resolve(pointer):
        node = a
        for part in pointer.lstrip("/").split("/"):
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node

    for m in metrics:
        try:
            r = resolve(m["calculation_ref"])
            require(r["id"] == m["rule_id"], "Calculation pointer mismatch")
            require(m["item_ids"] == r["item_ids"], "Report item membership mismatch")
            require(m["calculation_method"] == r["method"], "Report calculation method mismatch")
            require((m["minimum"], m["maximum"]) == (r["minimum"], r["maximum"]), "Report scale mismatch")
            if m["severity_bands_ref"]:
                require(resolve(m["severity_bands_ref"]) == r["severity_bands"], "Descriptor pointer mismatch")
            else:
                require(not r.get("severity_bands"), "Existing descriptors omitted")
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append("Invalid calculation/descriptor pointer")
    history = c["item_history"]
    require([h["item_id"] for h in history] == list(qs), "Item history must include every question exactly once")
    for h in history:
        try:
            q = resolve(h["question_ref"])
            require(q["id"] == h["item_id"], "Question pointer mismatch")
            require(h["source_label"] == q.get("source_label"), "Source numbering mismatch")
            require(h["missing_value"] == "gap" and h["ineligible_value"] == "not_asked", "Missing item history must not become zero")
            require(h["response_type"] == q["response_type"], "History input type mismatch")
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append("Invalid question pointer")
    grouped = set()
    for g in c["response_groups"]:
        require(set(g["item_ids"]) <= qs.keys(), "Unknown response-group item")
        grouped.update(g["item_ids"])
        if g["rule_id"] is not None:
            require(g["rule_id"] in rules and g["item_ids"] == rules[g["rule_id"]]["item_ids"], "Response-group membership mismatch")
    require(grouped == qs.keys(), "Ungrouped responses")
    domain_charts = [ch for ch in c["charts"] if ch["kind"] == "domain_trend"]
    require([ch["series"][0]["id"] for ch in domain_charts] == list(rules), "Every metric needs a separate chart")
    for ch in domain_charts:
        r = rules.get(ch["series"][0]["id"])
        if r:
            require((ch["minimum"], ch["maximum"]) == (r["minimum"], r["maximum"]), "Chart scale mismatch")
    require(bool(c["protocol"]) == bool(a["scoring"].get("protocol")), "Protocol support mismatch")
    require(bool(c["paired_profile"]) == bool(a["scoring"].get("paired_profile")), "Paired-profile support mismatch")
    if c["protocol"]:
        require(not metrics and not c["protocol"]["numeric_total_applicable"], "Protocol has fabricated numeric score")
    if c["paired_profile"]:
        require(c["paired_profile"]["rule_ids"] == a["scoring"]["paired_profile"]["rule_ids"], "Paired-profile rule mismatch")
    return errors


def validate(bundle, schema, source=None, verify_assets=True):
    errors, assets, rows = [], {}, []
    validator = Draft202012Validator(schema)
    Draft202012Validator.check_schema(schema)

    def require(ok, message):
        if not ok:
            errors.append(message)

    def inspect(value, location):
        if isinstance(value, dict):
            path, sha = value.get("archive_path"), value.get("sha256")
            if path and sha:
                if path in assets:
                    require(assets[path] == sha, "Conflicting asset hashes: " + path)
                assets[path] = sha
            for k, v in value.items():
                inspect(v, location + "." + k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                inspect(v, location + f"[{i}]")
        elif isinstance(value, str):
            require(not HOST.search(value) and not FRAGMENT.search(value), "Provider URL: " + location)

    inspect(bundle, "bundle")
    assessments = bundle["assessments"]
    require(len({a["assessment_id"] for a in assessments}) == len(assessments), "Duplicate assessment IDs")
    require(bundle["summary"]["assessment_count"] == len(assessments), "Summary assessment count")
    require(bundle["summary"]["recovered_item_count"] == sum(len(a["questionnaire"]["items"]) for a in assessments), "Summary item count")
    require(bundle["summary"]["total_draft_scoring_rules"] == sum(len(a["scoring"]["rules"]) for a in assessments), "Summary rule count")
    if source is not None:
        try:
            check_preservation(source, bundle)
        except AssertionError as exc:
            errors.append("Content preservation: " + str(exc))

    for a in assessments:
        aid = a["assessment_id"]
        errors.extend(aid + ": " + message for message in verification_errors(a))
        for error in validator.iter_errors(a):
            errors.append(aid + ": " + error.json_path + ": " + error.message)
        qs = {q["id"]: q for q in a["questionnaire"]["items"]}
        sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
        rules = {r["id"]: r for r in a["scoring"]["rules"]}
        require(len(qs) == a["questionnaire"]["item_count"], aid + ": question count/duplicate IDs")
        require(len(sets) == len(a["questionnaire"]["response_sets"]), aid + ": duplicate response-set IDs")
        require(len(rules) == len(a["scoring"]["rules"]), aid + ": duplicate rule IDs")
        require(list(qs) == a["administration"]["item_order"], aid + ": question order")
        require(a["scoring"]["enabled"] is False and a["review"]["ready_for_clinical_use"] is False, aid + ": unexpected clinical enablement")
        context_keys = set()

        def check_condition(expr):
            if not expr:
                return
            if "context_key" in expr:
                context_keys.add(expr["context_key"])
            if "item_id" in expr:
                require(expr["item_id"] in qs, aid + ": unknown conditional item")
            for key in ("any", "all"):
                for child in expr.get(key, []):
                    check_condition(child)

        for q in qs.values():
            check_condition(q.get("display_if"))
            answer_schema = q["input_spec"]["answer_schema"]
            Draft202012Validator.check_schema(answer_schema)
            av = Draft202012Validator(answer_schema)
            if q["response_set_id"] is None:
                require(not q["options"], aid + ": fabricated non-choice options")
            else:
                require(q["response_set_id"] in sets, aid + ": missing response set")
                options = sets.get(q["response_set_id"], {}).get("options", [])
                require([(o["id"], o.get("printed_value")) for o in q["options"]] ==
                        [(o["id"], o.get("printed_value")) for o in options], aid + ": inline/response-set mismatch " + q["id"])
                require(len({o["id"] for o in options}) == len(options), aid + ": duplicate options")
                for o in q["options"]:
                    require(bool(o["text"].strip()), aid + ": empty option label")
                    value = [o["id"]] if q["selection_mode"] == "multiple" else o["id"]
                    require(av.is_valid(value), aid + ": option rejected by answer schema")
                    require(set(o["used_by_scoring_rules"]) <= rules.keys(), aid + ": unknown option rule")
        for rule in rules.values():
            require(set(rule["item_ids"]) <= qs.keys(), aid + ": unknown rule item")
            require(len(set(rule["item_ids"])) == len(rule["item_ids"]), aid + ": duplicate rule items")
            require(rule["minimum"] <= rule["maximum"], aid + ": invalid score range")
            check_condition(rule.get("applies_if"))
            for constraint in rule.get("context_constraints", []):
                context_keys.add(constraint["context_key"])
            # ASRS-O intentionally shares one instrument-wide threshold map
            # across its two subscales; only member items are evaluated.
            require(set(rule.get("item_thresholds", {})) <= qs.keys(), aid + ": unknown threshold item")
            for key in ("optional_item_ids", "item_transforms", "item_coefficients", "option_value_overrides"):
                require(set(rule.get(key, [])) <= set(rule["item_ids"]), aid + ": invalid " + key)
        report = a.get("reporting")
        errors.extend(aid + ": " + message for message in report_errors(a))
        if report:
            require(len({c["id"] for c in report["charts"]}) == len(report["charts"]), aid + ": duplicate chart IDs")
            for metric in report["metrics"]:
                r = rules.get(metric["rule_id"])
                require(r is not None, aid + ": unknown report metric")
                if r:
                    require((r["minimum"], r["maximum"]) == (metric["minimum"], metric["maximum"]), aid + ": metric range mismatch")
            for chart in report["charts"]:
                target = qs if chart["kind"] == "item_trend" else rules
                require(all(s["id"] in target for s in chart["series"]), aid + ": unknown chart series")
        rows.append({
            "assessment_id": aid, "name": a["assessment"]["name"], "questions": len(qs),
            "draft_rules": len(rules), "methods": " | ".join(sorted({r["method"] for r in rules.values()})),
            "report_configuration": "draft" if report else "not_configured",
            "report_mode": report["mode"] if report else "missing",
            "configured_metrics": len(report["metrics"]) if report else 0,
            "configured_item_histories": len(report["item_history"]) if report else 0,
            "uncompiled_score_directions": len(report["coverage"]["missing_direction_rule_ids"]) if report else 0,
            "required_context": " | ".join(sorted(context_keys)),
            "percentile_status": a["scoring"].get("percentile_status", ""),
            "clinical_ready": False,
            "technical_verification": a["verification"]["status"],
            "source_benchmarked_rules": sum(r["source_check"] == "selected_formula_checks_matched" for r in a["verification"]["rules"]),
            "verification_remaining_work": " | ".join(a["verification"]["remaining_work"]),
            "remaining_work": " | ".join(a["scoring"].get("remaining_work", [])),
            "review_issues": " | ".join(i["code"] for i in a["review"]["issues"]),
        })
    if verify_assets:
        for path, expected in assets.items():
            p = Path(path)
            if not p.is_file():
                errors.append("Missing retained asset: " + path)
            else:
                with p.open("rb") as handle:
                    actual = hashlib.file_digest(handle, "sha256").hexdigest()
                require(actual == expected, "Asset checksum mismatch: " + path)
    return {
        "status": "passed" if not errors else "failed",
        "scope": "Automated structural, source preservation and asset-integrity validation; not independent clinical approval.",
        "counts": {"assessments": len(assessments), "questions": sum(r["questions"] for r in rows),
                   "draft_rules": sum(r["draft_rules"] for r in rows),
                   "verification_records": sum("verification" in a for a in assessments),
                   "source_benchmarked_assessments": sum(bool(r["source_benchmarked_rules"]) for r in rows),
                   "source_benchmarked_rules": sum(r["source_benchmarked_rules"] for r in rows),
                   "report_configurations": sum("reporting" in a for a in assessments),
                   "configured_metrics": sum(r["configured_metrics"] for r in rows),
                   "configured_item_histories": sum(r["configured_item_histories"] for r in rows),
                   "report_modes": {mode: sum(r["report_mode"] == mode for r in rows)
                                    for mode in ("numeric_scores", "descriptive_responses", "screening_protocol", "unavailable")},
                   "asset_files_verified": len(assets) if verify_assets else 0},
        "error_count": len(errors), "errors": errors,
        "known_limitations": ["Clinical scoring remains disabled for every assessment.",
                              "SDQ has no selected questionnaire; MAPsy coverage remains partial.",
                              "Percentile rules are not implemented; BAM does not use percentiles.",
                              "Source-based benchmarks cover selected formulas in eight assessments, not complete source review of all 186.",
                              "YES NA/partial-response handling and CORE-10 one-missing prorating remain explicit gaps.",
                              "All records have report configuration; missing source content, uncompiled directions and clinical interpretation remain explicitly flagged.",
                              "The PHQ-9-assessment app still requires importer/scoring/report changes."],
    }, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    result, rows = validate(json.loads(args.bundle.read_text()), json.loads(args.schema.read_text()),
                            json.loads(args.source.read_text()))
    result["bundle_sha256"] = hashlib.sha256(args.bundle.read_bytes()).hexdigest()
    result["source_sha256"] = hashlib.sha256(args.source.read_bytes()).hexdigest()
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    with args.csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
