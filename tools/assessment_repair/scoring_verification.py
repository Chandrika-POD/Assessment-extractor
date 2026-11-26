"""Version-bound technical evidence, explicitly separate from clinical approval."""

import copy
import json
import hashlib
from functools import lru_cache
from pathlib import Path

from audit_scoring import fingerprint

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "scoring_verification_registry.json"

VERIFICATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "checked_on", "definition_version", "scoring_content_sha256", "status",
                 "scope", "questionnaire", "rules", "interpretation", "percentiles", "protocol",
                 "source_references", "remaining_work", "clinical_approval", "runtime_policy", "evidence_build"],
    "properties": {
        "schema_version": {"const": "1.0.0"}, "checked_on": {"type": ["string", "null"]},
        "definition_version": {"type": "string"},
        "scoring_content_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "status": {"enum": ["technical_checks_passed", "technical_checks_with_limits", "no_numeric_rules", "issues_found", "not_checked", "stale"]},
        "scope": {"type": "string"}, "questionnaire": {"type": "object"},
        "rules": {"type": "array", "items": {"type": "object", "required": ["rule_id", "technical_status", "source_check", "clinical_approved"],
                  "properties": {"clinical_approved": {"const": False}}}},
        "interpretation": {"type": "array"}, "percentiles": {"type": "object"}, "protocol": {"type": "object"},
        "source_references": {"type": "array"}, "remaining_work": {"type": "array", "items": {"type": "string"}},
        "evidence_build": {"type": "object"},
        "clinical_approval": {"type": "object", "additionalProperties": False,
                              "required": ["approved", "reviewer", "reviewed_on", "approved_definition_version", "approved_scoring_sha256"],
                              "properties": {"approved": {"const": False}, "reviewer": {"const": None},
                                             "reviewed_on": {"const": None}, "approved_definition_version": {"const": None},
                                             "approved_scoring_sha256": {"const": None}}},
        "runtime_policy": {"type": "object", "required": ["clinical_scoring_enabled", "draft_label", "draft_requires_explicit_opt_in", "missing_rule_result"],
                           "properties": {"clinical_scoring_enabled": {"const": False},
                                          "draft_requires_explicit_opt_in": {"const": True},
                                          "missing_rule_result": {"const": "unavailable"}, "draft_label": {"type": "string"}}},
    },
}


@lru_cache(maxsize=1)
def registry():
    data = json.loads(REGISTRY.read_text())
    return {r["assessment_id"]: r["verification"] for r in data["assessments"]}


def verification_for(a):
    """Any relevant content change invalidates old evidence, even without a version bump."""
    expected = fingerprint(a)
    saved = registry().get(a["assessment_id"])
    if saved is None:
        raise ValueError("No verification inventory entry: " + a["assessment_id"])
    result = copy.deepcopy(saved)
    if result["scoring_content_sha256"] != expected:
        result["status"] = "stale"
        result["checked_on"] = None
        result["scoring_content_sha256"] = expected
        result["definition_version"] = a["definition_version"]
        result["rules"] = [{"rule_id": r["id"], "technical_status": "not_checked", "source_check": "not_checked",
                            "clinical_approved": False, "example_case_ids": []} for r in a["scoring"]["rules"]]
        result["interpretation"] = []
        result["source_references"] = []
        result["remaining_work"] = ["Scoring content changed after the evidence was recorded; rerun verification."]
    return result


def verification_errors(a):
    v = a.get("verification")
    if not v:
        return ["Missing per-component scoring verification"]
    errors = []
    if v["scoring_content_sha256"] != fingerprint(a):
        errors.append("Scoring verification content fingerprint mismatch")
    if v["definition_version"] != a["definition_version"]:
        errors.append("Scoring verification version mismatch")
    if v["status"] in ("stale", "not_checked", "issues_found"):
        errors.append("Scoring verification needs attention: " + v["status"])
    if [r["rule_id"] for r in v["rules"]] != [r["id"] for r in a["scoring"]["rules"]]:
        errors.append("Verification must enumerate every numeric rule exactly once")
    if v != verification_for(a):
        errors.append("Embedded verification differs from recorded evidence")
    for name, expected in v.get("evidence_build", {}).items():
        if name not in {"definition_runtime.py", "audit_scoring.py", "build_scoring_verification.py", "scoring_benchmarks.json"}:
            errors.append("Unknown evidence dependency: " + name)
        elif hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected:
            errors.append("Verification evidence dependency changed: " + name)
    return errors
