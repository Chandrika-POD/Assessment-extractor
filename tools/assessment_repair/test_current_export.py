"""Regression checks on the current distribution and its report contract."""

import json
import os
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from definition_runtime import evaluate, interpret, condition
from export_clean_content import clean, check_preservation

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("ASSESSMENT_PROJECT", str(HERE.parents[1])))
CURRENT = Path(os.environ.get("ASSESSMENT_CURRENT_DIR", str(PROJECT / "assessment-exports/current")))


class CurrentExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = json.loads((CURRENT / "all-assessments.json").read_text())
        cls.source = json.loads((PROJECT / "assessment-exports/novopsych-all-186-assessments-definition-repaired-20261114.json").read_text())
        cls.phq = next(a for a in cls.bundle["assessments"] if a["assessment_id"].startswith("patient-health-questionnaire-depression-phq-9--"))
        cls.bam = next(a for a in cls.bundle["assessments"] if a["assessment_id"].startswith("brief-addiction-monitor-bam--"))

    def numeric_answers(self, assessment, values):
        answers = {}
        for q in assessment["questionnaire"]["items"]:
            if q["id"] not in values:
                continue
            value = values[q["id"]]
            answers[q["id"]] = next(o["id"] for o in q["options"] if o["printed_value"] == value) if q["options"] else value
        return answers

    def test_all_records_validate_against_distribution_schema(self):
        schema = json.loads((CURRENT / "definition-clean-export.schema.json").read_text())
        validator = Draft202012Validator(schema)
        for a in self.bundle["assessments"]:
            with self.subTest(assessment=a["assessment_id"]):
                validator.validate(a)

    def test_original_content_and_disabled_scoring_preserved(self):
        check_preservation(self.source, self.bundle)
        self.assertTrue(all(a["scoring"]["enabled"] is False for a in self.bundle["assessments"]))
        self.assertEqual(sum("reporting" in a for a in self.bundle["assessments"]), 186)

    def test_url_cleanup_includes_pdf_fragments_and_preserves_attribution(self):
        value = {
            "url": "https://novopsych.com/assessment",
            "prose": "Read https://www.novopsych.com.au/test. More.",
            "fragment": "Reference https://novopsych.",
            "email": "support@novopsych.com", "author": "NovoPsych",
            "reference": "https://doi.org/10.1000/example",
        }
        result = clean(value)
        self.assertIsNone(result["url"])
        self.assertNotIn("https://novopsych", result["fragment"])
        self.assertEqual(result["prose"], "Read [link omitted]. More.")
        for key in ("email", "author", "reference"):
            self.assertEqual(result[key], value[key])

    def test_phq_all_possible_totals_and_severity_boundaries(self):
        r = self.phq["scoring"]["rules"][0]
        expected = (["No or minimal depression"] * 5 + ["Mild depression"] * 5 +
                    ["Moderate depression"] * 5 + ["Moderate-severe depression"] * 5 +
                    ["Severe depression"] * 8)
        for total in range(28):
            remaining, values = total, {}
            for i in range(1, 10):
                values[f"Q{i}"] = min(remaining, 3)
                remaining -= values[f"Q{i}"]
            score = evaluate(self.phq, r, self.numeric_answers(self.phq, values))
            self.assertEqual(score, total)
            self.assertEqual(interpret(r, score), expected[total])

    def test_phq_missing_and_invalid_answers_withhold_or_reject(self):
        rule = self.phq["scoring"]["rules"][0]
        answers = self.numeric_answers(self.phq, {f"Q{i}": 1 for i in range(1, 9)})
        self.assertIsNone(evaluate(self.phq, rule, answers))
        answers["Q9"] = "O99"
        with self.assertRaises(ValidationError):
            evaluate(self.phq, rule, answers)

    def test_bam_nonuniform_domain_scores(self):
        values = {"Q1": 15, "Q2": 7, "Q3": 6, "Q4": 4, "Q5": 1, "Q6": 2,
                  "Q14": 8, "Q17": 3, "Q21": 8, "Q15": 22, "Q16": 8,
                  "Q18": 8, "Q19": 17, "Q20": 30, "Q22": 16,
                  "Q7": 2, "Q23": 22}
        answers = self.numeric_answers(self.bam, values)
        self.assertEqual([evaluate(self.bam, r, answers) for r in self.bam["scoring"]["rules"]], [7, 47, 101])
        # Neither satisfaction nor drug-specific details alter domain totals.
        answers["Q7"], answers["Q23"] = 30, "O5"
        self.assertEqual([evaluate(self.bam, r, answers) for r in self.bam["scoring"]["rules"]], [7, 47, 101])

    def test_bam_domain_endpoints(self):
        for value, expected in [(0, [0, 0, 0]), (30, [90, 180, 180])]:
            answers = self.numeric_answers(self.bam, {q["id"]: value for q in self.bam["questionnaire"]["items"]})
            self.assertEqual([evaluate(self.bam, r, answers) for r in self.bam["scoring"]["rules"]], expected)

    def test_bam_conditional_zero_is_distinct_from_missing(self):
        rule = self.bam["scoring"]["rules"][0]
        self.assertEqual(evaluate(self.bam, rule, {"Q4": 0, "Q6": 0}), 0)
        self.assertIsNone(evaluate(self.bam, rule, {"Q4": 1, "Q6": 0}))
        self.assertIsNone(evaluate(self.bam, rule, {"Q6": 0}))
        for value in [-1, 31, 1.5, "3"]:
            with self.assertRaises(ValidationError):
                evaluate(self.bam, rule, {"Q4": value, "Q5": 1, "Q6": 0})

    def test_bam_report_units_direction_and_membership(self):
        r = self.bam["reporting"]
        self.assertEqual([m["favourable_direction"] for m in r["metrics"]], ["decrease", "decrease", "increase"])
        charts = {c["id"]: c for c in r["charts"]}
        self.assertEqual(charts["substance_use"]["axis_unit"], "days")
        self.assertEqual(charts["health"]["axis_unit"], "score")
        self.assertEqual([s["id"] for s in charts["satisfaction"]["series"]], ["Q23"])
        self.assertEqual(charts["satisfaction"]["series"][0]["value_field"], "printed_value")
        item_series = [s["id"] for c in r["charts"] if c["kind"] == "item_trend" for s in c["series"]]
        self.assertEqual(len(item_series), 23)
        self.assertEqual(set(item_series), {f"Q{i}" for i in range(1, 24)})
        self.assertFalse(r["percentiles"]["enabled"])
        self.assertIsNone(r["interpretation"]["overall_total"])
        self.assertTrue(all(not rule["severity_bands"] for rule in self.bam["scoring"]["rules"]))

    def test_report_comparisons_use_saved_dates_and_withhold_missing(self):
        for a in [self.phq, self.bam]:
            r = a["reporting"]
            self.assertEqual(r["comparisons"]["date_source"], "saved_session_completion_timestamp")
            self.assertEqual(r["comparisons"]["missing_result"], "withhold_comparison")
            self.assertEqual(r["interpretation"]["clinical_significance"], "not_implemented_requires_review")
            self.assertFalse(r["clinical_scoring_enabled"])


if __name__ == "__main__":
    unittest.main()
