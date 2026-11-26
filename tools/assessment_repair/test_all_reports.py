"""Catalogue-wide reporting coverage and instrument-specific rendering contracts."""

import copy
import json
import os
import unittest
from pathlib import Path

from definition_runtime import evaluate, evaluate_profile, evaluate_protocol
from validate_current_bundle import report_errors

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("ASSESSMENT_PROJECT", str(HERE.parents[1])))
CURRENT = Path(os.environ.get("ASSESSMENT_CURRENT_DIR", str(PROJECT / "assessment-exports/current")))


class AllReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((CURRENT / "all-assessments.json").read_text())["assessments"]

    def get(self, prefix):
        return next(a for a in self.rows if a["assessment_id"].startswith(prefix))

    def choice_values(self, a, value):
        return {q["id"]: next(o["id"] for o in q["options"] if o["printed_value"] == value)
                for q in a["questionnaire"]["items"] if q["options"]}

    def test_all_186_have_consistent_report_contracts(self):
        self.assertEqual(len(self.rows), 186)
        for a in self.rows:
            with self.subTest(assessment=a["assessment_id"]):
                self.assertEqual(report_errors(a), [])
                self.assertTrue(a["reporting"]["sections"])
                self.assertFalse(a["reporting"]["clinical_scoring_enabled"])
        self.assertEqual(sum(len(a["reporting"]["metrics"]) for a in self.rows), 729)
        self.assertEqual(sum(len(a["reporting"]["item_history"]) for a in self.rows), 4927)

    def test_numeric_descriptive_protocol_and_unavailable_modes(self):
        counts = {mode: sum(a["reporting"]["mode"] == mode for a in self.rows)
                  for mode in ["numeric_scores", "descriptive_responses", "screening_protocol", "unavailable"]}
        self.assertEqual(counts, {"numeric_scores": 183, "descriptive_responses": 1,
                                 "screening_protocol": 1, "unavailable": 1})
        lec = self.get("life-events")
        self.assertFalse(lec["reporting"]["metrics"])
        self.assertEqual(len(lec["reporting"]["item_history"]), 17)
        self.assertFalse(lec["reporting"]["interpretation"]["combine_metrics_into_new_total"])
        sdq = self.get("strengths-and-difficulties")
        self.assertFalse(sdq["reporting"]["coverage"]["questionnaire_available"])
        self.assertFalse(sdq["reporting"]["charts"])
        self.assertTrue(sdq["reporting"]["coverage"]["remaining_work"])

    def test_dass_raw_and_doubled_metrics_have_distinct_scales(self):
        a = self.get("depression-anxiety-stress-scales")
        scores = {r["id"]: evaluate(a, r, self.choice_values(a, 1)) for r in a["scoring"]["rules"]}
        self.assertEqual(scores, {"total_raw": 21, "depression_raw": 7, "depression_doubled": 14,
                                  "anxiety_raw": 7, "anxiety_doubled": 14, "stress_raw": 7, "stress_doubled": 14})
        metrics = {m["rule_id"]: m for m in a["reporting"]["metrics"]}
        self.assertEqual(metrics["depression_raw"]["maximum"], 21)
        self.assertEqual(metrics["depression_doubled"]["maximum"], 42)
        self.assertNotEqual(metrics["depression_raw"]["label"], metrics["depression_doubled"]["label"])

    def test_negative_and_nonzero_minimum_scales_are_preserved(self):
        spane = self.get("scale-of-positive-and-negative")
        self.assertEqual(spane["reporting"]["metrics"][-1]["minimum"], -24)
        self.assertEqual(spane["reporting"]["charts"][-1]["minimum"], -24)
        pswq = self.get("penn-state-worry")
        self.assertEqual(pswq["reporting"]["charts"][0]["minimum"], 16)
        self.assertEqual(pswq["reporting"]["charts"][0]["maximum"], 80)
        self.assertIn("{minimum}", pswq["reporting"]["interpretation"]["score_template"])

    def test_mean_and_count_charts_use_the_correct_units(self):
        for a in self.rows:
            by_id = {r["id"]: r for r in a["scoring"]["rules"]}
            for m in a["reporting"]["metrics"]:
                method = by_id[m["rule_id"]]["method"]
                expected = {"mean": "mean score", "count_threshold": "item count"}.get(method, "score")
                self.assertEqual(m["axis_unit"], expected)

    def test_whodas_context_is_explicit(self):
        rows = [a for a in self.rows if "whodas" in a["assessment_id"]]
        self.assertEqual(len(rows), 4)
        for a in rows:
            fields = a["reporting"]["required_context"]
            self.assertTrue(any(f["key"] in ("works_or_studies", "attends_school") for f in fields))
            self.assertTrue(all(f["type"] == "boolean" for f in fields))
            self.assertTrue(a["reporting"]["comparisons"]["require_compatible_respondent_context"])

    def test_paired_profile_is_preserved_without_new_total(self):
        a = self.get("manic-and-depression")
        self.assertEqual(a["reporting"]["paired_profile"]["rule_ids"], a["scoring"]["paired_profile"]["rule_ids"])
        self.assertIsNone(a["reporting"]["interpretation"]["overall_total"])
        self.assertEqual(evaluate_profile(a, self.choice_values(a, 0)), "Both below threshold")
        self.assertEqual(evaluate_profile(a, self.choice_values(a, 3)), "Both elevated")
        self.assertIsNone(evaluate_profile(a, {}))

    def test_asq_states_use_protocol_without_score_or_actions(self):
        a = self.get("ask-suicide")
        answers = self.choice_values(a, 0)
        states = a["reporting"]["protocol"]["state_labels"]
        self.assertIn(evaluate_protocol(a, answers)["status"], states)
        self.assertIn(evaluate_protocol(a, {})["status"], states)
        q = next(q for q in a["questionnaire"]["items"] if q["id"] == "Q1")
        answers["Q1"] = next(o["id"] for o in q["options"] if o["printed_value"] == 1)
        self.assertIn(evaluate_protocol(a, answers)["status"], states)
        self.assertFalse(a["reporting"]["protocol"]["clinical_actions_enabled"])
        self.assertFalse(a["reporting"]["metrics"])

    def test_text_and_multiple_responses_are_not_numeric_histories(self):
        for a in self.rows:
            qs = {q["id"]: q for q in a["questionnaire"]["items"]}
            for h in a["reporting"]["item_history"]:
                q = qs[h["item_id"]]
                if q["response_type"] == "text":
                    self.assertEqual(h["presentation"], "text_history")
                    self.assertIsNone(h["maximum"])
                elif q["response_type"] == "multiple_choice" or q.get("selection_mode") == "multiple":
                    self.assertEqual(h["presentation"], "multiple_choice_history")
                self.assertEqual(h["missing_value"], "gap")
                self.assertEqual(h["ineligible_value"], "not_asked")

    def test_partial_scoring_and_unknown_directions_are_visible(self):
        mapsy = self.get("multilevel-assessment")
        self.assertEqual(mapsy["reporting"]["coverage"]["raw_calculation_status"], "partial")
        self.assertTrue(mapsy["reporting"]["coverage"]["remaining_work"])
        for a in self.rows:
            c = a["reporting"]
            self.assertFalse(c["coverage"]["full_source_coverage_verified"])
            self.assertFalse(c["percentiles"]["enabled"])
            for m in c["metrics"]:
                if m["favourable_direction"] is None:
                    self.assertEqual(m["direction_status"], "not_compiled")
                    self.assertIn(m["rule_id"], c["coverage"]["missing_direction_rule_ids"])
                    self.assertEqual(c["comparisons"]["unknown_direction"],
                                     "report_numeric_change_without_improvement_or_deterioration_label")

    def test_validator_detects_wrong_scale_missing_metric_and_bad_pointer(self):
        a = copy.deepcopy(self.get("depression-anxiety-stress-scales"))
        a["reporting"]["charts"][0]["minimum"] = -1
        self.assertIn("Chart scale mismatch", report_errors(a))
        a = copy.deepcopy(self.get("depression-anxiety-stress-scales"))
        a["reporting"]["metrics"].pop()
        self.assertIn("Report must include every rule exactly once", report_errors(a))
        a = copy.deepcopy(self.get("depression-anxiety-stress-scales"))
        a["reporting"]["item_history"][0]["question_ref"] = "/questionnaire/items/9999"
        self.assertIn("Invalid question pointer", report_errors(a))


if __name__ == "__main__":
    unittest.main()
