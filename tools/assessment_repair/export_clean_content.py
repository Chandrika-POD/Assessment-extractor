"""Create a content-preserving distribution copy without NovoPsych website links."""

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from report_configuration import report_configuration, REPORT_SCHEMA
from verification_corrections import apply_corrections, YES_ID
from scoring_verification import verification_for, VERIFICATION_SCHEMA

VERSION = "2.3.0-clean-export.4"
# Emails and provider/author names are attribution, not website links.
HOST = re.compile(
    r"(?<![\w@.-])(?:[a-z0-9-]+\.)*novopsych\.com(?:\.au)?(?![\w-])", re.IGNORECASE
)
URL = re.compile(r'(?:https?://|//)[^\s<>"\u201c\u201d]+', re.IGNORECASE)
BARE = re.compile(
    r'(?<![\w@.-])(?:[a-z0-9-]+\.)*novopsych\.com(?:\.au)?(?:/[^\s<>"\u201c\u201d]*)?',
    re.IGNORECASE,
)
# PDF extraction can split a URL at the domain or at a line boundary.
FRAGMENT = re.compile(
    r'(?:https?://|//)(?:[a-z0-9-]+\.)*novopsych(?:\.[a-z]+)*(?:\.)?(?:/[^\s<>"\u201c\u201d]*)?',
    re.IGNORECASE,
)


def redact_string(value):
    def replacement(match):
        token = match[0]
        if not HOST.search(token):
            return token
        # Preserve punctuation following a link in prose/Markdown.
        suffix = token[len(token.rstrip(".,;:)]}")) :]
        return "[link omitted]" + suffix

    changed = URL.sub(replacement, value)
    changed = BARE.sub("[link omitted]", changed)
    changed = FRAGMENT.sub("[link omitted]", changed)
    if changed.strip() == "[link omitted]":
        return None
    return changed


def clean(value):
    if isinstance(value, dict):
        return {key: clean(child) for key, child in value.items()}
    if isinstance(value, list):
        return [clean(child) for child in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def build(source):
    original = json.loads(source.read_text())
    bundle = clean(original)
    bundle["schema_version"] = VERSION
    bundle["bundle_version"] = "2026-11-18-scoring-verification-export"
    reconciled = 0
    for assessment in bundle["assessments"]:
        assessment["schema_version"] = VERSION
        apply_corrections(assessment)
        config = report_configuration(assessment)
        if config is not None:
            assessment["reporting"] = config
        assessment["verification"] = verification_for(assessment)
        for issue in assessment["review"]["issues"]:
            if (
                issue["code"] == "scoring_not_structured"
                and assessment["scoring"]["rules"]
            ):
                issue["code"] = "draft_scoring_review_pending"
                issue["detail"] = (
                    "Structured draft rules are present. Source-specific scoring coverage and independent review remain incomplete; scoring is disabled."
                )
                reconciled += 1
    bundle["import_contract"]["schema_version"] = VERSION
    bundle["import_contract"]["reporting"] = (
        "Reporting configuration is supplied for all 186 records. Numeric reports use all available explicit rules; descriptive, protocol and unavailable records have distinct modes. Null score directions require neutral presentation. Read coverage and review gates; configuration does not enable clinical scoring."
    )
    bundle["export_notes"] = {
        "created_on": "2026-11-18",
        "source_bundle_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_schema_version": original["schema_version"],
        "link_handling": "Provider website URLs are omitted, including links embedded in prose. Standalone removed links are null; inline links use [link omitted]. Other reference links, author/provider names and email attribution are preserved.",
        "content_handling": "All records, fields, response structures and source evidence are retained. Six YES rule minimums are corrected in the distribution only, with before/after provenance and a definition-version bump. Verification evidence is additive; no clinical approval is granted.",
        "asset_handling": "Asset metadata and existing archive paths are retained; external image/PDF file bytes are not embedded by this export.",
        "schema_note": "Distribution variant of 2.3: source URL fields may be null. Use definition-clean-export.schema.json for record validation. Existing runtime input-type limitations are unchanged.",
        "reconciled_stale_scoring_warning_count": reconciled,
        "report_configuration_count": sum("reporting" in a for a in bundle["assessments"]),
        "validation_scope": "Structural integrity, preservation, source-file hashes and selected calculation regressions. Independent clinical approval remains pending.",
        "scoring_verification": "All 729 rules audited for technical consistency; selected primary-source benchmarks are recorded separately from clinical approval. Six YES mean minima corrected with an explicit provenance record. No scoring was clinically enabled.",
        "verification_contract": "Every assessment has version/content-bound verification and separate calculation, interpretation and clinical-approval fields. Source URLs are evidence only; no runtime fetch is required.",
    }
    return original, bundle


def cleaned_schema(source_schema):
    schema = copy.deepcopy(json.loads(source_schema.read_text()))
    schema["title"] = (
        "Assessment content distribution record with omitted provider links"
    )
    schema["$id"] = "urn:assessment:definition-clean-export:4"
    schema["properties"]["schema_version"] = {"const": VERSION}
    schema["properties"]["definition_version"] = {"enum": ["1.0.0-draft.6", "1.0.0-draft.7"]}
    schema.setdefault("allOf", []).append({
        "if": {"properties": {"assessment_id": {"const": YES_ID}}},
        "then": {"properties": {"definition_version": {"const": "1.0.0-draft.7"}}},
        "else": {"properties": {"definition_version": {"const": "1.0.0-draft.6"}}},
    })
    schema["properties"]["reporting"] = copy.deepcopy(REPORT_SCHEMA)
    schema["properties"]["verification"] = copy.deepcopy(VERIFICATION_SCHEMA)
    schema["required"].append("verification")
    if "reporting" not in schema["required"]:
        schema["required"].append("reporting")
    schema["$defs"]["item"]["properties"]["source"]["properties"]["url"]["type"] = [
        "string",
        "null",
    ]
    return schema


def check_preservation(original, output):
    assert len(output["assessments"]) == len(original["assessments"]) == 186
    # Compare every content leaf; only documented metadata and stale warning
    # reconciliation may differ beyond website link redaction.
    for before, after in zip(original["assessments"], output["assessments"]):
        expected = clean(before)
        expected["schema_version"] = VERSION
        apply_corrections(expected)
        config = report_configuration(expected)
        if config is not None:
            expected["reporting"] = config
        expected["verification"] = verification_for(expected)
        expected["review"]["issues"] = after["review"]["issues"]
        assert expected == after, before["assessment_id"]
        assert len(before["review"]["issues"]) == len(after["review"]["issues"])
        for old, new in zip(before["review"]["issues"], after["review"]["issues"]):
            if old["code"] == "scoring_not_structured" and before["scoring"]["rules"]:
                assert new["code"] == "draft_scoring_review_pending"
            else:
                assert clean(old) == new
    assert sum(a["questionnaire"]["item_count"] for a in output["assessments"]) == 4927
    assert sum(len(a["scoring"]["rules"]) for a in output["assessments"]) == 729

    def check(value):
        if isinstance(value, dict):
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
        elif isinstance(value, str):
            assert not HOST.search(value), value[:200]
            assert not FRAGMENT.search(value), value[:200]

    check(output)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--source-schema", required=True, type=Path)
    args = p.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError("The original evidence bundle must remain unchanged.")
    original, bundle = build(args.input)
    check_preservation(original, bundle)
    schema = cleaned_schema(args.source_schema)
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for a in bundle["assessments"]:
        validator.validate(a)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    args.output.with_name("definition-clean-export.schema.json").write_text(
        json.dumps(schema, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "records": len(bundle["assessments"]),
                "questions": 4927,
                "draft_rules": 729,
                "stale_warnings_reconciled": bundle["export_notes"][
                    "reconciled_stale_scoring_warning_count"
                ],
                "bytes": args.output.stat().st_size,
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
