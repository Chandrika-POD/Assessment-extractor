"""Offline technical audit. Mathematical consistency is not clinical validation."""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from definition_runtime import evaluate


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def fingerprint(a):
    return digest({key: a[key] for key in
                   ("assessment_id", "definition_version", "administration", "questionnaire", "scoring")})


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def candidates(a, q, rule):
    """Get input/score pairs from this definition, not from an external oracle."""
    if q["response_set_id"]:
        options = next(s["options"] for s in a["questionnaire"]["response_sets"]
                       if s["id"] == q["response_set_id"])
        result = []
        for o in options:
            if re.fullmatch(r"N/?A|NOT APPLICABLE", o.get("label") or "", re.I):
                # Explicit overrides can intentionally assign NA a value.
                if o["id"] not in rule.get("option_value_overrides", {}).get(q["id"], {}):
                    continue
            value = rule.get("option_value_overrides", {}).get(q["id"], {}).get(
                o["id"], o.get(rule.get("value_field", "printed_value")))
            if finite(value):
                result.append((o["id"], value))
        return result
    schema = q["input_spec"]["answer_schema"]
    if schema.get("type") not in ("integer", "number"):
        return []
    values = [schema.get("minimum"), schema.get("maximum")]
    return [(v, v) for v in values if finite(v)] if all(map(finite, values)) else []


def contribution(rule, iid, value):
    t = rule.get("item_transforms", {}).get(iid, {})
    value = value * t.get("scale", 1) + t.get("offset", 0)
    if rule["method"] == "count_threshold":
        threshold = rule.get("item_thresholds", {}).get(iid, rule["threshold"])
        op = rule["operator"]
        if op not in (">=", "<="):
            raise ValueError("unsupported threshold operator")
        value = int(value >= threshold if op == ">=" else value <= threshold)
    return value * rule.get("item_coefficients", {}).get(iid, 1)


def audit_rule(a, rule):
    qs = {q["id"]: q for q in a["questionnaire"]["items"]}
    errors, warnings = [], []
    for iid in rule["item_ids"]:
        q = qs[iid]
        if not q["response_set_id"]:
            continue
        options = next(s["options"] for s in a["questionnaire"]["response_sets"] if s["id"] == q["response_set_id"])
        shared = {o["id"]: o for o in options}
        field = rule.get("value_field", "printed_value")
        if any(o["id"] not in shared or o.get(field) != shared[o["id"]].get(field) for o in q["options"]):
            errors.append("Inline/response-set scoring mismatch: " + iid)
    conditional = bool(rule.get("applies_if") or rule.get("context_constraints") or
                       rule.get("optional_item_ids") or
                       any(qs[i].get("display_if") for i in rule["item_ids"]))
    lo, hi, low_answers, high_answers = [], [], {}, {}
    for iid in rule["item_ids"]:
        pairs = candidates(a, qs[iid], rule)
        if not pairs:
            errors.append("No finite scoring inputs: " + iid)
            continue
        contributions = [(answer, contribution(rule, iid, value)) for answer, value in pairs]
        low, high = min(contributions, key=lambda x: x[1]), max(contributions, key=lambda x: x[1])
        lo.append(low[1]); hi.append(high[1])
        low_answers[iid], high_answers[iid] = low[0], high[0]
    bounds = None
    if len(lo) == len(rule["item_ids"]) and lo:
        divisor = len(lo) if rule["method"] == "mean" else 1
        bounds = sorted([sum(lo) / divisor * rule.get("multiplier", 1),
                         sum(hi) / divisor * rule.get("multiplier", 1)])
        if conditional:
            warnings.append("Endpoint equivalence not asserted: eligibility, optional items or context can change the feasible range.")
        elif not all(math.isclose(x, y, abs_tol=1e-9) for x, y in
                     zip(bounds, (rule["minimum"], rule["maximum"]))):
            errors.append("Declared range differs from attainable input range")
    runtime_checks = []
    if not conditional and not errors:
        for label, answers, expected in (("minimum", low_answers, bounds[0]),
                                         ("maximum", high_answers, bounds[1])):
            # Swap extremizing answers if the final multiplier is negative.
            if rule.get("multiplier", 1) < 0:
                answers = high_answers if label == "minimum" else low_answers
            actual = evaluate(a, rule, answers)
            passed = finite(actual) and math.isclose(actual, expected, abs_tol=1e-9)
            runtime_checks.append({"case": label, "expected": expected, "actual": actual, "passed": passed})
            if not passed:
                errors.append("Runtime endpoint mismatch: " + label)
        missing = evaluate(a, rule, {})
        runtime_checks.append({"case": "all_missing", "expected": None, "actual": missing, "passed": missing is None})
        if missing is not None:
            errors.append("All missing responses produced a score")
    bands = rule.get("severity_bands", [])
    for i, band in enumerate(bands):
        lower, upper = band["minimum_inclusive"], band["maximum_inclusive"]
        if not (rule["minimum"] <= lower <= upper <= rule["maximum"]):
            errors.append("Severity band outside declared range")
        if any(max(lower, b["minimum_inclusive"]) <= min(upper, b["maximum_inclusive"])
               for b in bands[:i]):
            errors.append("Overlapping severity bands")
    return {"rule_id": rule["id"], "method": rule["method"],
            "status": "issues_found" if errors else "conditional_review_required" if conditional else "passed",
            "scope": "Definition-derived arithmetic consistency; not independent source verification.",
            "declared_range": [rule["minimum"], rule["maximum"]], "unconditional_input_bounds": bounds,
            "conditional": conditional, "runtime_checks": runtime_checks, "errors": errors, "warnings": warnings}


def audit_bundle(bundle):
    records = []
    for a in bundle["assessments"]:
        rules = [audit_rule(a, r) for r in a["scoring"]["rules"]]
        records.append({"assessment_id": a["assessment_id"], "name": a["assessment"]["name"],
                        "definition_version": a["definition_version"], "scoring_content_sha256": fingerprint(a),
                        "rules": rules})
    return {"schema_version": "1.0.0", "checked_on": "2026-11-18", "clinical_approval": False,
            "scope": "All supplied numeric rules; conditional endpoints explicitly deferred. No clinical correctness claim.",
            "assessments": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit_bundle(json.loads(args.bundle.read_text()))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    rules = [r for a in result["assessments"] for r in a["rules"]]
    from collections import Counter
    print(json.dumps(dict(Counter(r["status"] for r in rules))))
    for a in result["assessments"]:
        for r in a["rules"]:
            if r["errors"]:
                print(a["assessment_id"], r["rule_id"], r["errors"], r["declared_range"], r["unconditional_input_bounds"])
