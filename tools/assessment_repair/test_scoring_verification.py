"""Evidence must detect scoring mutations and must never confer clinical approval."""

import copy
import json
import os
import unittest
from pathlib import Path

from audit_scoring import audit_rule, fingerprint
from build_scoring_verification import check_benchmark
from scoring_verification import verification_for, verification_errors, VERIFICATION_SCHEMA
from verification_corrections import apply_corrections, YES_ID, YES_OLD_MINIMUMS
from definition_runtime import evaluate
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("ASSESSMENT_PROJECT", str(HERE.parents[1])))
CURRENT = Path(os.environ.get("ASSESSMENT_CURRENT_DIR", str(PROJECT / "assessment-exports/current")))


class ScoringVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = json.loads((CURRENT / "all-assessments.json").read_text())
        cls.by_id = {a["assessment_id"]: a for a in cls.bundle["assessments"]}
        cls.benchmarks = json.loads((HERE / "scoring_benchmarks.json").read_text())

    def assessment(self, prefix):
        return next(a for a in self.by_id.values() if a["assessment_id"].startswith(prefix))

    def test_every_definition_has_current_version_bound_evidence(self):
        validator = Draft202012Validator(VERIFICATION_SCHEMA)
        for a in self.by_id.values():
            with self.subTest(a=a["assessment_id"]):
                validator.validate(a["verification"])
                self.assertEqual(verification_errors(a), [])
                self.assertEqual(a["verification"]["scoring_content_sha256"], fingerprint(a))
                self.assertFalse(a["verification"]["clinical_approval"]["approved"])
                self.assertIsNone(a["verification"]["clinical_approval"]["reviewer"])
                self.assertFalse(a["scoring"]["enabled"])

    def test_selected_primary_source_examples(self):
        known_gaps = []
        for spec in self.benchmarks["assessments"]:
            with self.subTest(a=spec["assessment_id"]):
                result = check_benchmark(self.by_id[spec["assessment_id"]], spec)
                self.assertEqual(result["failures"], [])
                known_gaps.extend(c["id"] for c in result["cases"]
                                  if any(r["status"] == "known_gap_confirmed" for r in c["results"].values()))
        self.assertEqual(len(known_gaps), 3)

    def test_all_rules_have_explicit_technical_status_and_source_scope(self):
        rows = [r for a in self.by_id.values() for r in a["verification"]["rules"]]
        self.assertEqual(len(rows), 729)
        self.assertEqual(sum(r["source_check"] == "selected_formula_checks_matched" for r in rows), 25)
        self.assertEqual(sum(r["technical_status"] == "conditional_review_required" for r in rows), 15)
        self.assertFalse(any(r["clinical_approved"] for r in rows))
        self.assertFalse(any(r["technical_status"] == "issues_found" for r in rows))

    def test_source_case_detects_wrong_membership_even_with_same_item_count(self):
        a = copy.deepcopy(self.assessment("depression-anxiety-stress-scales-short"))
        a["scoring"]["rules"][1]["item_ids"][0] = "Q1"
        spec = next(s for s in self.benchmarks["assessments"] if s["assessment_id"] == a["assessment_id"])
        self.assertTrue(check_benchmark(a, spec)["failures"])

    def test_source_case_detects_double_reverse_scoring(self):
        a = copy.deepcopy(self.assessment("clinical-outcomes-in-routine-evaluation-10"))
        a["scoring"]["rules"][0]["item_transforms"] = {"Q2": {"scale": -1, "offset": 4}}
        spec = next(s for s in self.benchmarks["assessments"] if s["assessment_id"] == a["assessment_id"])
        self.assertTrue(check_benchmark(a, spec)["failures"])

    def test_definition_edits_invalidate_evidence_without_version_change(self):
        a = copy.deepcopy(self.assessment("patient-health-questionnaire-depression"))
        a["scoring"]["rules"][0]["multiplier"] = 2
        stale = verification_for(a)
        self.assertEqual(stale["status"], "stale")
        self.assertIsNone(stale["checked_on"])
        self.assertEqual(stale["rules"][0]["source_check"], "not_checked")
        self.assertEqual(stale["source_references"], [])
        self.assertTrue(verification_errors(a))

    def test_clinical_approval_cannot_be_inferred_from_passed_checks(self):
        a = copy.deepcopy(self.assessment("patient-health-questionnaire-depression"))
        a["verification"]["clinical_approval"]["approved"] = True
        self.assertFalse(Draft202012Validator(VERIFICATION_SCHEMA).is_valid(a["verification"]))
        self.assertTrue(verification_errors(a))

    def test_yes_corrected_minima_match_answers_not_na_zero_codes(self):
        a = self.by_id[YES_ID]
        self.assertEqual(a["definition_version"], "1.0.0-draft.7")
        for r in a["scoring"]["rules"]:
            self.assertEqual((r["minimum"], r["maximum"]), (1, 5))
            self.assertEqual(evaluate(a, r, {i: "O1" for i in r["item_ids"]}), 1)
        rule = a["scoring"]["rules"][2]
        self.assertIsNone(evaluate(a, rule, {"Q6": "O3", "Q16": "O6"}))
        self.assertTrue(any("NA" in g for g in a["verification"]["remaining_work"]))

    def test_yes_correction_is_narrow_and_rejects_changed_source(self):
        original = json.loads((PROJECT / "assessment-exports/novopsych-all-186-assessments-definition-repaired-20261114.json").read_text())
        a = next(a for a in original["assessments"] if a["assessment_id"] == YES_ID)
        before = copy.deepcopy(a)
        apply_corrections(a)
        self.assertEqual(a["questionnaire"], before["questionnaire"])
        for old, new in zip(before["scoring"]["rules"], a["scoring"]["rules"]):
            expected = copy.deepcopy(old)
            if old["id"] in YES_OLD_MINIMUMS:
                expected["minimum"] = 1.0
            self.assertEqual(new, expected)
        with self.assertRaises(ValueError):
            apply_corrections(a)

    def test_audit_detects_response_set_scoring_drift(self):
        a = copy.deepcopy(self.assessment("patient-health-questionnaire-depression"))
        a["questionnaire"]["items"][0]["options"][0]["score"] = 3
        self.assertTrue(any("scoring mismatch" in e for e in audit_rule(a, a["scoring"]["rules"][0])["errors"]))

    def test_conditional_ranges_are_not_claimed_as_exhaustively_verified(self):
        a = self.assessment("crafft-substance")
        r = audit_rule(a, a["scoring"]["rules"][0])
        self.assertEqual(r["status"], "conditional_review_required")
        self.assertFalse(r["runtime_checks"])
        self.assertTrue(r["warnings"])

    def test_descriptive_protocol_and_unavailable_have_no_numeric_approval(self):
        for a in self.by_id.values():
            if not a["scoring"]["rules"]:
                self.assertEqual(a["verification"]["status"], "no_numeric_rules")
                self.assertFalse(a["verification"]["rules"])
                self.assertFalse(a["verification"]["clinical_approval"]["approved"])


if __name__ == "__main__":
    unittest.main()
