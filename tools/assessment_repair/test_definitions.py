"""Definition repair regressions: preserved source data and independently expected scores."""

import json
import os
import unittest
from pathlib import Path

from definition_runtime import (
    condition,
    evaluate,
    evaluate_profile,
    evaluate_protocol,
    interpret,
)
from jsonschema import Draft202012Validator, ValidationError
from repair_definitions import INPUT, OUTPUT

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("ASSESSMENT_PROJECT", str(HERE.parents[1])))
OUTPUT_PATH = Path(
    os.environ.get(
        "ASSESSMENT_DEFINITION_JSON", str(PROJECT / "assessment-exports" / OUTPUT)
    )
)


class DefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = json.loads(OUTPUT_PATH.read_text())
        cls.previous = json.loads((PROJECT / "assessment-exports" / INPUT).read_text())
        cls.changed = [
            a
            for a in cls.bundle["assessments"]
            if "definition_repair" in a["provenance"]
        ]
        cls.old = {a["assessment_id"]: a for a in cls.previous["assessments"]}

    def options(self, a, iid):
        return next(q["options"] for q in a["questionnaire"]["items"] if q["id"] == iid)

    def answers(self, a, value=0):
        result = {}
        for q in a["questionnaire"]["items"]:
            if q["options"]:
                matches = [
                    o
                    for o in q["options"]
                    if o["printed_value"] == value
                    and o["source_label"] not in ["NA", "N/A"]
                ]
                if matches:
                    result[q["id"]] = matches[0]["id"]
            elif q["response_type"] in ["integer", "number"]:
                result[q["id"]] = value
        return result

    def choice(self, a, iid, label):
        return next(o["id"] for o in self.options(a, iid) if o["source_label"] == label)

    def test_all_186_schema_and_references(self):
        schema = json.loads((HERE / "definition-v2.3.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        v = Draft202012Validator(schema)
        self.assertEqual(len(self.bundle["assessments"]), 186)
        self.assertEqual(
            sum(a["questionnaire"]["item_count"] for a in self.bundle["assessments"]),
            4927,
        )
        for a in self.bundle["assessments"]:
            with self.subTest(assessment=a["assessment_id"]):
                v.validate(a)
                qs = {q["id"]: q for q in a["questionnaire"]["items"]}
                rules = {r["id"]: r for r in a["scoring"]["rules"]}
                self.assertEqual(len(qs), a["questionnaire"]["item_count"])
                self.assertEqual(len(rules), len(a["scoring"]["rules"]))
                self.assertFalse(a["scoring"]["enabled"])
                self.assertFalse(a["review"]["ready_for_clinical_use"])
                for r in rules.values():
                    self.assertLessEqual(r["minimum"], r["maximum"])
                    self.assertTrue(set(r["item_ids"]) <= qs.keys())
                    for key in [
                        "optional_item_ids",
                        "item_transforms",
                        "item_coefficients",
                        "option_value_overrides",
                    ]:
                        self.assertTrue(set(r.get(key, [])) <= set(r["item_ids"]))
                sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
                for q in qs.values():
                    if q["response_set_id"]:
                        self.assertEqual(
                            [o["id"] for o in q["options"]],
                            [o["id"] for o in sets[q["response_set_id"]]["options"]],
                        )
                    sv = Draft202012Validator(q["input_spec"]["answer_schema"])
                    for o in q["options"]:
                        sv.validate(
                            [o["id"]] if q["selection_mode"] == "multiple" else o["id"]
                        )
                        self.assertTrue(set(o["used_by_scoring_rules"]) <= rules.keys())

    def test_source_preservation_and_old_rules_unchanged(self):
        before_rules = 0
        for a in self.bundle["assessments"]:
            old = self.old[a["assessment_id"]]
            for key in [
                "context_sections",
                "references",
                "tables",
                "assets",
                "rights",
                "source_documents",
                "source_refresh",
                "conversation_policy",
            ]:
                self.assertEqual(a[key], old[key], (a["assessment_id"], key))
            before_rules += len(old["scoring"]["rules"])
            self.assertEqual(
                a["scoring"]["rules"][: len(old["scoring"]["rules"])],
                old["scoring"]["rules"],
            )
            for q, oq in zip(
                a["questionnaire"]["items"], old["questionnaire"]["items"]
            ):
                self.assertEqual(q["id"], oq["id"])
                self.assertEqual(q["source_label"], oq["source_label"])
                if not (a == self.changed[14] and q["id"] == "Q1"):
                    self.assertEqual(q["text"], oq["text"])
                for o, oo in zip(q["options"], oq["options"]):
                    for key in ["id", "text", "source_label", "printed_value"]:
                        self.assertEqual(o[key], oo[key])
        self.assertEqual(before_rules, 434)
        self.assertEqual(len(self.changed), 44)

    def test_wsas_repaired_stem_and_distinct_nonworking_option(self):
        a = self.changed[14]
        q = a["questionnaire"]["items"][0]
        self.assertEqual(
            q["text"], "Because of my difficulties, my ability to work is impaired."
        )
        self.assertEqual(len(q["options"]), 10)
        self.assertIsNone(q["options"][-1]["printed_value"])
        ans = self.answers(a, 2)
        ans["Q1"] = "O10"
        self.assertEqual(evaluate(a, a["scoring"]["rules"][0], ans), 8)
        del ans["Q1"]
        self.assertIsNone(evaluate(a, a["scoring"]["rules"][0], ans))

    def test_crafft_skip_unknown_and_positive_routes(self):
        a = self.changed[1]
        r, h = a["scoring"]["rules"]
        ans = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0, "Q5": self.choice(a, "Q5", "YES")}
        self.assertEqual(evaluate(a, r, ans), 1)
        self.assertIsNone(evaluate(a, h, ans))
        del ans["Q2"]
        self.assertIsNone(evaluate(a, r, ans))
        ans["Q2"] = 1
        self.assertIsNone(evaluate(a, r, ans))
        for i in range(6, 11):
            ans["Q" + str(i)] = self.choice(a, "Q" + str(i), "NO")
        self.assertEqual(evaluate(a, r, ans), 1)
        ans["Q4"] = 2
        for i in range(11, 21):
            ans["Q" + str(i)] = self.choice(a, "Q" + str(i), "YES")
        self.assertEqual(evaluate(a, h, ans), 10)
        ans["Q1"] = -1
        with self.assertRaises(ValidationError):
            evaluate(a, r, ans)

    def test_bam_source_numbers_and_skip_zero(self):
        a = self.changed[2]
        r = a["scoring"]["rules"][0]
        self.assertEqual(r["item_ids"], ["Q4", "Q5", "Q6"])
        self.assertEqual(evaluate(a, r, {"Q4": 0, "Q6": 0}), 0)
        self.assertIsNone(evaluate(a, r, {"Q4": 1, "Q6": 0}))
        self.assertEqual(evaluate(a, r, {"Q4": 1, "Q5": 1, "Q6": 2}), 4)
        self.assertEqual(
            a["scoring"]["rules"][1]["item_ids"],
            ["Q1", "Q2", "Q3", "Q14", "Q17", "Q21"],
        )
        self.assertEqual(
            a["scoring"]["rules"][2]["item_ids"],
            ["Q15", "Q16", "Q18", "Q19", "Q20", "Q22"],
        )

    def test_mapsy_checklist_exclusivity_and_partial_scope(self):
        a = self.changed[0]
        r = a["scoring"]["rules"][0]
        ans = self.answers(a, 1)
        ans["Q74"] = ["O8"]
        self.assertIsNone(evaluate(a, r, ans))
        ans["Q74"] = ["O1"]
        self.assertEqual(evaluate(a, r, ans), 9)
        ans["Q74"] = ["O1", "O8"]
        with self.assertRaises(ValidationError):
            evaluate(a, r, ans)
        self.assertEqual(
            a["scoring"]["implementation_status"]["raw_calculation"], "partial"
        )

    def test_asq_protocol_and_dependency_validation(self):
        a = self.changed[12]
        ans = {f"Q{i}": self.choice(a, f"Q{i}", "NO") for i in range(1, 5)}
        self.assertEqual(evaluate_protocol(a, ans)["status"], "negative_core_screen")
        ans["Q2"] = self.choice(a, "Q2", "YES")
        self.assertEqual(
            evaluate_protocol(a, ans)["status"],
            "positive_core_screen_acuity_unanswered",
        )
        cond = next(
            q["display_if"] for q in a["questionnaire"]["items"] if q["id"] == "Q7"
        )
        self.assertTrue(condition(a, cond, {"Q2": ans["Q2"]}))
        self.assertIsNone(condition(a, cond, {}))
        ans["Q7"] = self.choice(a, "Q7", "YES")
        self.assertEqual(
            evaluate_protocol(a, ans)["status"], "positive_core_screen_current_ideation"
        )
        ans["Q1"] = "BAD"
        with self.assertRaises(ValidationError):
            condition(a, cond, ans)

    def test_signed_composites_and_rule_specific_reversal(self):
        a = self.changed[16]
        ans = self.answers(a, 1)
        self.assertEqual(evaluate(a, a["scoring"]["rules"][-2], ans), 10)
        self.assertEqual(evaluate(a, a["scoring"]["rules"][-1], ans), 7)
        self.assertEqual(
            [(r["minimum"], r["maximum"]) for r in a["scoring"]["rules"][-2:]],
            [(-5, 75), (-8, 57)],
        )
        a = self.changed[42]
        ans = self.answers(a, 1)
        for iid in ["Q1", "Q3", "Q5", "Q7", "Q10", "Q12"]:
            ans[iid] = next(
                o["id"] for o in self.options(a, iid) if o["printed_value"] == 5
            )
        self.assertEqual(
            [evaluate(a, r, ans) for r in a["scoring"]["rules"]], [30, 6, 24]
        )
        a = self.changed[37]
        ans = self.answers(a, 1)
        self.assertEqual(
            [evaluate(a, r, ans) for r in a["scoring"]["rules"]], [1, 1, 5]
        )

    def test_pwi_optional_denominator(self):
        a = self.changed[32]
        r = a["scoring"]["rules"][0]
        ans = self.answers(a, 4)
        del ans["Q9"]
        self.assertEqual(evaluate(a, r, ans), 40)
        ans["Q9"] = next(
            o["id"] for o in self.options(a, "Q9") if o["printed_value"] == 8
        )
        self.assertEqual(evaluate(a, r, ans), 45)
        del ans["Q2"]
        self.assertIsNone(evaluate(a, r, ans))

    def test_whodas_eligibility_context_and_auxiliary_exclusion(self):
        for n, count, key in [
            (29, 34, "attends_school"),
            (34, 36, "works_or_studies"),
            (35, 36, "works_or_studies"),
            (36, 36, "works_or_studies"),
        ]:
            a = self.changed[n]
            r = next(r for r in a["scoring"]["rules"] if r["label"] == "Overall mean")
            ans = self.answers(a, 2)
            self.assertEqual(len(r["item_ids"]), count)
            self.assertIsNone(evaluate(a, r, ans))
            self.assertEqual(evaluate(a, r, ans, {key: True}), 2)
            for q in a["questionnaire"]["items"]:
                if q.get("display_if", {}).get("context_key") == key:
                    ans.pop(q["id"], None)
            self.assertEqual(evaluate(a, r, ans, {key: False}), 2)
            self.assertIsNone(evaluate(a, r, ans, {key: True}))
            with self.assertRaises(ValueError):
                evaluate(a, r, ans, {key: 1})
        self.assertFalse(
            any(
                r["label"] == "Overall percent maximum"
                for r in self.changed[29]["scoring"]["rules"]
            )
        )

    def test_ort_consistent_source_columns(self):
        a = self.changed[38]
        r = a["scoring"]["rules"][0]
        for sex in ["female", "male"]:
            ans = {}
            for q in a["questionnaire"]["items"]:
                labels = {o["source_label"]: o["id"] for o in q["options"]}
                ans[q["id"]] = labels.get(
                    "YES (" + sex.upper() + ")", labels.get("YES")
                )
            self.assertIsNone(evaluate(a, r, ans))
            self.assertEqual(evaluate(a, r, ans, {"source_scoring_sex": sex}), 26)
            self.assertEqual(interpret(r, 26), "High Risk")
            ans["Q1"] = self.choice(
                a, "Q1", "YES (" + ("MALE" if sex == "female" else "FEMALE") + ")"
            )
            with self.assertRaises(ValueError):
                evaluate(a, r, ans, {"source_scoring_sex": sex})
        self.assertEqual(r["maximum"], 26)

    def test_na_is_not_numeric_zero(self):
        a = self.changed[27]
        r = a["scoring"]["rules"][0]
        ans = self.answers(a, 0)
        self.assertEqual(evaluate(a, r, ans), 0)
        iid = r["item_ids"][0]
        opts = self.options(a, iid)
        ans[iid] = next(o["id"] for o in opts if o["source_label"] in ["NA", "N/A"])
        self.assertIsNone(evaluate(a, r, ans))
        del ans[iid]
        self.assertIsNone(evaluate(a, r, ans))

    def test_paired_profile_and_threshold(self):
        a = self.changed[3]
        ans = self.answers(a, 0)
        self.assertEqual(evaluate_profile(a, ans), "Both below threshold")
        for i in range(1, 10):
            ans["Q" + str(i)] = next(
                o["id"]
                for o in self.options(a, "Q" + str(i))
                if o["printed_value"] == 2
            )
        self.assertEqual(evaluate_profile(a, ans), "PMQ-9 elevated only")
        del ans["Q10"]
        self.assertIsNone(evaluate_profile(a, ans))

    def test_counts_and_excluded_fields(self):
        a = self.changed[5]
        ans = self.answers(a, 1)
        self.assertEqual(
            [evaluate(a, r, ans) for r in a["scoring"]["rules"]], [73, 0, 0, 0]
        )
        ans = self.answers(a, 2)
        for r in a["scoring"]["rules"][1:]:
            self.assertAlmostEqual(evaluate(a, r, ans), 100)
        a = self.changed[7]
        r = a["scoring"]["rules"][0]
        self.assertEqual(len(r["item_ids"]), 31)
        self.assertFalse(
            {"Q3", "Q4", "Q12", "Q22", "Q26", "Q33", "Q38"} & set(r["item_ids"])
        )
        a = self.changed[43]
        self.assertEqual(len(a["scoring"]["rules"][-1]["item_ids"]), 38)
        self.assertNotIn("Q46", a["scoring"]["rules"][-1]["item_ids"])
        a = self.changed[24]
        self.assertEqual(a["scoring"]["rules"][0]["maximum"], 79)

    def test_known_complete_totals_and_overlapping_subscales(self):
        # Nonuniform item numbers catch aggregate and membership mistakes.
        a = self.changed[9]
        ans = self.answers(a, 1)
        self.assertEqual(
            [evaluate(a, r, ans) for r in a["scoring"]["rules"][:30]], [4] * 30
        )
        self.assertEqual(
            [evaluate(a, r, ans) for r in a["scoring"]["rules"][30:]], [24] * 5
        )
        a = self.changed[26]
        membership = [
            r["label"] for r in a["scoring"]["rules"] if "Q3" in r["item_ids"]
        ]
        self.assertEqual(len(membership), 2)
        a = self.changed[33]
        self.assertEqual(
            [len(r["item_ids"]) for r in a["scoring"]["rules"][:4]], [39, 14, 7, 20]
        )
        self.assertEqual(
            evaluate(a, a["scoring"]["rules"][-1], self.answers(a, 3)), 240
        )
        for n in [39, 40, 41]:
            a = self.changed[n]
            self.assertEqual(
                [
                    evaluate(a, r, self.answers(a, 2))
                    for r in a["scoring"]["rules"][-2:]
                ],
                [74, 94],
            )

    def test_existing_rules_match_previous_runtime(self):
        import sys

        sys.path.insert(0, str(PROJECT / "tools/assessment_repair"))
        from source_formulas import evaluate as previous_evaluate

        for a in self.bundle["assessments"]:
            old_rules = self.old[a["assessment_id"]]["scoring"]["rules"]
            if not old_rules:
                continue
            # A deterministic mixed-response vector exercises existing reverse
            # printed encodings and score-field rules without altering them.
            ans = {}
            for q in a["questionnaire"]["items"]:
                if q["options"] and q["selection_mode"] != "multiple":
                    valid = [
                        o
                        for o in q["options"]
                        if o["printed_value"] is not None
                        and o["source_label"] not in ["NA", "N/A", "NOT APPLICABLE"]
                    ]
                    if valid:
                        ans[q["id"]] = valid[q["order"] % len(valid)]["id"]
                elif q["response_type"] in ["integer", "number"]:
                    ans[q["id"]] = q["input_spec"]["answer_schema"].get("minimum", 0)
            for r in old_rules:
                with self.subTest(assessment=a["assessment_id"], rule=r["id"]):
                    self.assertEqual(evaluate(a, r, ans), previous_evaluate(a, r, ans))

    def test_gaps_and_source_conflicts_stay_explicit(self):
        self.assertEqual(self.changed[13]["questionnaire"]["item_count"], 0)
        self.assertEqual(self.changed[13]["scoring"]["rules"], [])
        self.assertIn(
            "Source conflict", " ".join(self.changed[11]["scoring"]["remaining_work"])
        )
        self.assertEqual(
            [r["maximum"] for r in self.changed[11]["scoring"]["rules"]], [42, 42]
        )
        for a in self.changed:
            self.assertTrue(a["scoring"]["remaining_work"])
        self.assertEqual(self.bundle["summary"]["total_draft_scoring_rules"], 729)


if __name__ == "__main__":
    unittest.main()
