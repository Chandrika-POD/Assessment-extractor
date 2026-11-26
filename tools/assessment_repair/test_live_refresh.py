"""Source refresh regression tests, including saved-answer compatibility."""

import copy
import json
import os
import unittest
from pathlib import Path

from build_refreshed_bundle import INPUT_NAME, OUTPUT_NAME
from jsonschema import Draft202012Validator, ValidationError
from source_formulas import evaluate, parse_caption, parse_items

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("ASSESSMENT_PROJECT", str(HERE.parents[1])))
OUTPUT = Path(
    os.environ.get(
        "ASSESSMENT_REFRESH_JSON", str(PROJECT / "assessment-exports" / OUTPUT_NAME)
    )
)


class RefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = json.loads(OUTPUT.read_text())
        cls.previous = json.loads(
            (PROJECT / "assessment-exports" / INPUT_NAME).read_text()
        )
        cls.rows = {a["assessment_id"]: a for a in cls.bundle["assessments"]}

    def get(self, prefix):
        return next(a for key, a in self.rows.items() if key.startswith(prefix))

    def opts(self, a, iid):
        q = next(q for q in a["questionnaire"]["items"] if q["id"] == iid)
        return q["options"]

    def test_schema_all_items_and_references(self):
        validator = Draft202012Validator(
            json.loads((HERE / "definition-v2.2.schema.json").read_text())
        )
        self.assertEqual(len(self.rows), 186)
        self.assertEqual(
            sum(a["questionnaire"]["item_count"] for a in self.rows.values()), 4927
        )
        for a in self.rows.values():
            validator.validate(a)
            items = {q["id"]: q for q in a["questionnaire"]["items"]}
            rules = {r["id"]: r for r in a["scoring"]["rules"]}
            self.assertEqual(len(rules), len(a["scoring"]["rules"]))
            self.assertEqual(len(items), a["questionnaire"]["item_count"])
            sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
            for q in items.values():
                schema = Draft202012Validator(q["input_spec"]["answer_schema"])
                for o in q["options"]:
                    self.assertTrue(o["text"].strip())
                    self.assertTrue(set(o["used_by_scoring_rules"]) <= rules.keys())
                    schema.validate(
                        [o["id"]] if q["selection_mode"] == "multiple" else o["id"]
                    )
                self.assertEqual(
                    len(q["options"]),
                    len(sets[q["response_set_id"]]["options"])
                    if q["response_set_id"]
                    else 0,
                )
            for r in rules.values():
                self.assertTrue(set(r["item_ids"]) <= items.keys())

    def test_saved_answer_ids_values_and_existing_content_preserved(self):
        for old in self.previous["assessments"]:
            a = self.rows[old["assessment_id"]]
            for field in ["context_sections", "tables", "assets", "source_documents"]:
                for entry in old[field]:
                    self.assertIn(entry, a[field])
            self.assertEqual(old["administration"], a["administration"])
            self.assertEqual(
                [q["id"] for q in old["questionnaire"]["items"]],
                [q["id"] for q in a["questionnaire"]["items"]],
            )
            oldsets = {s["id"]: s for s in old["questionnaire"]["response_sets"]}
            newsets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
            for oq, q in zip(
                old["questionnaire"]["items"], a["questionnaire"]["items"]
            ):
                self.assertEqual(oq["text"], q["text"])
                if oq["response_set_id"]:
                    oldopts = oldsets[oq["response_set_id"]]["options"]
                    opts = newsets[q["response_set_id"]]["options"]
                    self.assertEqual(
                        [(o["id"], o["printed_value"]) for o in oldopts],
                        [(o["id"], o["printed_value"]) for o in opts],
                    )
                    for oo, no in zip(oldopts, opts):
                        if oo["score"] is not None:
                            self.assertEqual(oo["score"], no["score"])
            for r in old["scoring"]["rules"]:
                self.assertIn(r, a["scoring"]["rules"])

    def test_source_refresh_and_draft_flags(self):
        self.assertEqual(self.bundle["summary"]["live_pages_retrieved"], 186)
        for a in self.rows.values():
            self.assertEqual(a["source_refresh"]["page_status"], "retrieved")
            self.assertFalse(a["scoring"]["enabled"])
            self.assertFalse(a["review"]["ready_for_clinical_use"])
            if a["source_documents"]:
                self.assertTrue(
                    a["source_refresh"]["selected_questionnaire"][
                        "matches_archived_pdf"
                    ]
                )
            for d in a["source_documents"]:
                self.assertFalse(d["runtime_context_allowed"])
        sdq = self.get("strengths-and-difficulties")
        self.assertEqual(sdq["questionnaire"]["item_count"], 0)

    def test_explicit_endpoint_and_shared_labels(self):
        y = self.get("why-have-sex")
        for q in y["questionnaire"]["items"]:
            self.assertEqual(len(q["options"]), 5)
            self.assertTrue(all(o["source_label"] for o in q["options"]))
        pardi = [
            a
            for a in self.rows.values()
            if "pardi-ar-q" in a["assessment_id"]
            or a["assessment_id"].startswith("pica-arfid")
        ]
        self.assertEqual(len(pardi), 2)
        for a in pardi:
            for q in a["questionnaire"]["items"]:
                if q["source_label"].isdigit() and int(q["source_label"]) >= 19:
                    self.assertTrue(q["options"][0]["source_label"])
                    self.assertTrue(q["options"][-1]["source_label"])
                    self.assertEqual(len(q["options"]), 7)
        iris = self.get("indigenous-risk")
        self.assertEqual(self.opts(iris, "Q3")[-1]["text"], "MOST DAYS/EVERY DAY")
        self.assertEqual(
            self.opts(iris, "Q5")[-1]["text"], "I COULDN’T STOP OR CUT DOWN"
        )

    def test_lec_allows_multiple_exposures_without_numeric_score(self):
        a = self.get("life-events-checklist")
        self.assertEqual(
            a["scoring"]["calculation_status"], "not_applicable_no_formal_scoring"
        )
        self.assertFalse(a["scoring"]["rules"])
        for q in a["questionnaire"]["items"]:
            v = Draft202012Validator(q["input_spec"]["answer_schema"])
            v.validate([o["id"] for o in q["options"][:2]])
            with self.assertRaises(ValidationError):
                v.validate([q["options"][0]["id"]] * 2)

    def test_arithmetic_rejects_incomplete_or_unsupported_captions(self):
        self.assertEqual(parse_items("1–3, 5 and 7"), [1, 2, 3, 5, 7])
        for text in ["0", "301", "1,1", "3-1", "1;2", "1, all"]:
            with self.assertRaises(ValueError):
                parse_items(text)
        self.assertIsNone(parse_caption("Total (Items 1-10)"))
        self.assertIsNone(parse_caption("Total (sum of subscale scores)"))
        self.assertIsNone(parse_caption("Total (sum of items 1-10"))
        self.assertEqual(
            parse_caption("Total (sum of all 7 items)")["numbers"], list(range(1, 8))
        )
        self.assertEqual(
            parse_caption("Mean (Items 1-6, average of circled values)")["method"],
            "mean",
        )

    def test_source_specific_score_vectors(self):
        cfi = self.get("cognitive-flexibility")
        answers = {
            q["id"]: q["options"][0]["id"] for q in cfi["questionnaire"]["items"]
        }
        # First printed column is 7 for six reverse-keyed items, 1 for the other 14.
        self.assertEqual(evaluate(cfi, cfi["scoring"]["rules"][0], answers), 56)
        ccq = self.get("composite-caregiving")
        r = next(r for r in ccq["scoring"]["rules"] if r["id"] == "emotion_affection")
        self.assertEqual(
            evaluate(
                ccq, r, {iid: self.opts(ccq, iid)[0]["id"] for iid in r["item_ids"]}
            ),
            10,
        )
        bsl = self.get("borderline-symptom-list")
        r = bsl["scoring"]["rules"][0]
        self.assertNotIn("Q24", r["item_ids"])
        self.assertEqual(
            evaluate(
                bsl, r, {iid: self.opts(bsl, iid)[-1]["id"] for iid in r["item_ids"]}
            ),
            4,
        )
        asrs = self.get("adult-adhd-observer")
        r = next(r for r in asrs["scoring"]["rules"] if r["id"] == "inattentive_count")
        answers = {
            iid: next(o["id"] for o in self.opts(asrs, iid) if o["printed_value"] == 2)
            for iid in r["item_ids"]
        }
        self.assertEqual(evaluate(asrs, r, answers), 4)
        self.assertIsNone(evaluate(asrs, r, {}))
        answers[r["item_ids"][0]] = "invalid"
        with self.assertRaises(ValueError):
            evaluate(asrs, r, answers)

    def test_all_rule_bounds_and_missing_answers(self):
        for a in self.rows.values():
            for r in a["scoring"]["rules"]:
                self.assertIsNone(evaluate(a, r, {}))
                for extreme in [min, max]:
                    answers = {}
                    for iid in r["item_ids"]:
                        q = next(
                            q for q in a["questionnaire"]["items"] if q["id"] == iid
                        )
                        if q["options"]:
                            field = (
                                "score"
                                if r["value_field"] == "score"
                                else "printed_value"
                            )
                            answers[iid] = extreme(
                                q["options"], key=lambda o: o[field]
                            )["id"]
                        else:
                            answers[iid] = q["input_spec"]["answer_schema"].get(
                                "minimum" if extreme == min else "maximum", 0
                            )
                    score = evaluate(a, r, answers)
                    if r["method"] != "count_threshold" and score is not None:
                        expected = r["minimum" if extreme == min else "maximum"]
                        if expected is not None:
                            self.assertAlmostEqual(
                                score, expected, msg=a["assessment_id"] + ":" + r["id"]
                            )

    def test_additional_source_membership_and_reversed_values(self):
        y = self.get("why-have-sex")
        self.assertEqual(len(y["scoring"]["rules"]), 14)
        self.assertTrue(all(len(r["item_ids"]) == 2 for r in y["scoring"]["rules"]))
        fmps = self.get("frost-multidimensional")
        total = next(
            r for r in fmps["scoring"]["rules"] if r["id"] == "total_perfectionism"
        )
        self.assertEqual(len(total["item_ids"]), 29)
        self.assertTrue(
            set(total["item_ids"]).isdisjoint({"Q2", "Q7", "Q8", "Q27", "Q29", "Q31"})
        )
        for a in self.rows.values():
            if a["assessment_id"].startswith(
                (
                    "obsessional-compulsive-inventory-ocd-child",
                    "obsessional-compulsive-inventory-revised-parent",
                )
            ):
                self.assertEqual(len(a["scoring"]["rules"]), 6)
                used = {i for r in a["scoring"]["rules"] for i in r["item_ids"]}
                self.assertTrue(
                    used.isdisjoint({"Q11", "Q12", "Q13", "Q30", "Q31", "Q32"})
                )
        pro = self.get("the-professional-quality")
        burnout = next(r for r in pro["scoring"]["rules"] if r["id"] == "burnout")
        answers = {iid: self.opts(pro, iid)[0]["id"] for iid in burnout["item_ids"]}
        self.assertEqual(evaluate(pro, burnout, answers), 30)

    def test_na_does_not_silently_count_as_zero(self):
        a = copy.deepcopy(self.get("generalised-anxiety"))
        r = a["scoring"]["rules"][0]
        s = a["questionnaire"]["response_sets"][0]
        s["options"][0]["label"] = "Not Applicable"
        self.assertIsNone(
            evaluate(a, r, {iid: s["options"][0]["id"] for iid in r["item_ids"]})
        )


if __name__ == "__main__":
    unittest.main()
