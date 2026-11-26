"""Audit all rules and run selected source-based examples; never grant clinical approval."""

import argparse
import json
import math
import hashlib
from pathlib import Path

from jsonschema import ValidationError
from audit_scoring import audit_bundle, fingerprint
from definition_runtime import evaluate, interpret


def matches(actual, expected):
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, abs_tol=1e-9)
    return actual == expected


def check_benchmark(a, spec):
    rules = {r["id"]: r for r in a["scoring"]["rules"]}
    questions = {q["id"]: q for q in a["questionnaire"]["items"]}
    failures, cases = [], []
    for assertion in spec["rule_assertions"]:
        r = rules.get(assertion["rule_id"], {})
        for field, value in assertion["expected"].items():
            default = {} if field in ("item_transforms", "item_coefficients", "option_value_overrides", "item_thresholds") else None
            if r.get(field, default) != value:
                failures.append(f"{assertion['rule_id']}: source assertion mismatch for {field}")
    for assertion in spec["response_assertions"]:
        q = questions[assertion["item_id"]]
        inline = {o["id"]: o for o in q["options"]}
        shared = {o["id"]: o for s in a["questionnaire"]["response_sets"] if s["id"] == q["response_set_id"] for o in s["options"]}
        fields = {"printed_value"} | {r.get("value_field", "printed_value") for r in rules.values() if q["id"] in r["item_ids"]}
        for oid, expected in assertion["expected_option_values"].items():
            for options in (inline, shared):
                if oid not in options or any(options[oid].get(field) != expected for field in fields):
                    failures.append(f"{q['id']}/{oid}: source response-value assertion mismatch")
    for case in spec["cases"]:
        results = {}
        for rid, expected in case["expected_scores"].items():
            try:
                actual = evaluate(a, rules[rid], case["answers"], case.get("context"))
                error = None
            except (ValidationError, ValueError, KeyError) as exc:
                actual, error = None, type(exc).__name__
            band = interpret(rules[rid], actual) if error is None else None
            passed = (error == case["expected_error"] if case.get("expected_error") else
                      error is None and matches(actual, expected))
            if rid in case.get("expected_bands", {}):
                passed = passed and band == case["expected_bands"][rid]
            known = case["kind"] == "known_source_gap"
            status = "passed" if passed else "known_gap_confirmed" if known and error is None else "failed"
            results[rid] = {"status": status, "expected": expected, "actual": actual, "error": error,
                            "expected_band": case.get("expected_bands", {}).get(rid), "actual_band": band}
            if status == "failed":
                failures.append(case["id"] + ": " + rid + " does not match expected result")
        cases.append({"id": case["id"], "kind": case["kind"], "results": results})
    return {"assessment_id": a["assessment_id"], "source_id": spec["source_id"],
            "scope": spec["review_scope"], "failures": failures, "cases": cases}


def build(bundle, benchmarks):
    audit = audit_bundle(bundle)
    aud = {a["assessment_id"]: a for a in audit["assessments"]}
    specs = {s["assessment_id"]: s for s in benchmarks["assessments"]}
    entries, benchmark_results = [], []
    here = Path(__file__).resolve().parent
    evidence_build = {name: hashlib.sha256((here / name).read_bytes()).hexdigest() for name in
                      ("definition_runtime.py", "audit_scoring.py", "build_scoring_verification.py", "scoring_benchmarks.json")}
    for a in bundle["assessments"]:
        aid = a["assessment_id"]
        spec = specs.get(aid)
        result = check_benchmark(a, spec) if spec else None
        if result:
            benchmark_results.append(result)
        errors = [e for r in aud[aid]["rules"] for e in r["errors"]] + (result["failures"] if result else [])
        has_limits = any(r["conditional"] for r in aud[aid]["rules"]) or bool(spec and spec["additional_gaps"])
        rules = []
        for rule, check in zip(a["scoring"]["rules"], aud[aid]["rules"]):
            rid = rule["id"]
            examples = [c for c in result["cases"] if rid in c["results"]] if result else []
            source_checked = bool(spec and any(t["rule_id"] == rid for t in spec["rule_assertions"]))
            rules.append({"rule_id": rid, "technical_status": check["status"],
                          "source_check": "selected_formula_checks_matched" if source_checked and not result["failures"] else "not_checked",
                          "source_scope": spec["review_scope"] if source_checked else None,
                          "source_ids": [spec["source_id"]] if source_checked else [],
                          "example_case_ids": [c["id"] for c in examples],
                          "example_result_counts": {status: sum(c["results"][rid]["status"] == status for c in examples)
                                                    for status in ("passed", "known_gap_confirmed", "failed")},
                          "clinical_approved": False})
        interpretation = []
        for rule in a["scoring"]["rules"]:
            checked = bool(spec and any(rule["id"] in c.get("expected_bands", {}) for c in spec["cases"]))
            interpretation.append({"rule_id": rule["id"], "status": "selected_boundaries_checked" if checked else
                                   "pending_source_review" if rule.get("severity_bands") else "not_encoded",
                                   "clinical_approved": False})
        remaining = list(a["scoring"].get("remaining_work", []))
        if spec:
            remaining.extend(spec["additional_gaps"])
        remaining.extend(i["detail"] for i in a["review"]["issues"])
        if not spec:
            remaining.append("No independent primary-source benchmark was added for this assessment in this pass.")
        verification = {
            "schema_version": "1.0.0", "checked_on": "2026-11-18", "definition_version": a["definition_version"],
            "scoring_content_sha256": fingerprint(a),
            "status": "issues_found" if errors else "no_numeric_rules" if not rules else "technical_checks_with_limits" if has_limits else "technical_checks_passed",
            "scope": "AI-assisted technical checks. Definition-derived range tests are distinct from selected primary-source examples. No human clinical sign-off.",
            "questionnaire": {"status": "pending_independent_review" if a["questionnaire"]["items"] else "unavailable",
                              "complete_wording_review": False},
            "rules": rules, "interpretation": interpretation,
            "percentiles": {"status": "not_implemented", "clinical_approved": False},
            "protocol": {"status": "pending_independent_review" if a["scoring"].get("protocol") or a["scoring"].get("paired_profile") else "not_encoded",
                         "clinical_approved": False},
            "source_references": [{"id": spec["source_id"], **benchmarks["sources"][spec["source_id"]],
                                    "location": spec["source_location"]}] if spec else [],
            "evidence_build": evidence_build,
            "remaining_work": list(dict.fromkeys(remaining)),
            "clinical_approval": {"approved": False, "reviewer": None, "reviewed_on": None,
                                  "approved_definition_version": None, "approved_scoring_sha256": None},
            "runtime_policy": {"clinical_scoring_enabled": False, "draft_label": "Draft score — not clinically validated",
                               "draft_requires_explicit_opt_in": True, "missing_rule_result": "unavailable",
                               "reject_stale_verification": True, "source_links_are_evidence_only": True},
        }
        entries.append({"assessment_id": aid, "verification": verification})
    return {"schema_version": "1.0.0", "created_on": "2026-11-18", "assessments": entries}, audit, benchmark_results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--bundle", type=Path)
    inputs.add_argument("--source", type=Path, help="Retained source bundle; apply export redaction and documented corrections before auditing.")
    p.add_argument("--benchmarks", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--registry-output", type=Path)
    args = p.parse_args()
    bundle = json.loads((args.source or args.bundle).read_text())
    if args.source:
        from export_clean_content import clean
        from verification_corrections import apply_corrections
        bundle = clean(bundle)
        for a in bundle["assessments"]:
            apply_corrections(a)
    registry, audit, results = build(bundle, json.loads(args.benchmarks.read_text()))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (("scoring_verification_registry.json", registry), ("technical-scoring-audit.json", audit),
                        ("source-benchmark-results.json", results)):
        target = args.registry_output if name == "scoring_verification_registry.json" and args.registry_output else args.output_dir / name
        target.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    errors = [e for a in audit["assessments"] for r in a["rules"] for e in r["errors"]]
    errors += [e for r in results for e in r["failures"]]
    from collections import Counter
    all_rules = [r for a in audit["assessments"] for r in a["rules"]]
    all_results = [v for r in results for c in r["cases"] for v in c["results"].values()]
    summary = {
        "checked_on": "2026-11-18", "status": "failed" if errors else "completed_with_known_gaps",
        "scope": "Technical verification pass; no independent human clinical approval and no claim that all source gaps are resolved.",
        "counts": {"assessments": len(registry["assessments"]), "numeric_rules_audited": len(all_rules),
                   "technical_rule_status": dict(Counter(r["status"] for r in all_rules)),
                   "definition_derived_runtime_checks": sum(len(r["runtime_checks"]) for r in all_rules),
                   "primary_source_benchmark_assessments": len(results),
                   "primary_source_benchmarked_rules": sum(r["source_check"] == "selected_formula_checks_matched" for a in registry["assessments"] for r in a["verification"]["rules"]),
                   "benchmark_cases": sum(len(r["cases"]) for r in results),
                   "benchmark_score_assertions": dict(Counter(r["status"] for r in all_results)),
                   "human_clinically_approved_assessments": 0},
        "source_benchmark_assessment_ids": [r["assessment_id"] for r in results],
        "known_gap_cases": [{"assessment_id": r["assessment_id"], **c} for r in results for c in r["cases"]
                            if any(v["status"] == "known_gap_confirmed" for v in c["results"].values())],
        "corrections": [{"assessment_id": a["assessment_id"], **a["provenance"]["scoring_verification_corrections"]}
                        for a in bundle["assessments"] if "scoring_verification_corrections" in a["provenance"]],
        "errors": errors,
    }
    (args.output_dir / "scoring-verification-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"assessments": len(registry["assessments"]), "benchmark_assessments": len(results), "errors": errors}))
    raise SystemExit(bool(errors))
