"""Regression tests for recovered PDF wording, scales and stable saved answers."""

import copy
import os
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from recover_pdf_questions import (
    INPUT_NAME,
    OUTPUT_NAME,
    checked_pdf,
    read,
    recover,
    source_text,
)

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("ASSESSMENT_PROJECT", str(HERE.parents[1])))
OUTPUT = Path(
    os.environ.get(
        "ASSESSMENT_QUESTION_JSON", str(PROJECT / "assessment-exports" / OUTPUT_NAME)
    )
)


class QuestionRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = read(OUTPUT)
        cls.old = read(PROJECT / "assessment-exports" / INPUT_NAME)
        cls.rules = read(HERE / "reviewed-question-recoveries.json")
        cls.rows = {a["assessment_id"]: a for a in cls.bundle["assessments"]}
        cls.previous = {a["assessment_id"]: a for a in cls.old["assessments"]}

    def get(self, prefix):
        return next(a for k, a in self.rows.items() if k.startswith(prefix))

    def question(self, a, i):
        return next(q for q in a["questionnaire"]["items"] if q["id"] == i)

    def options(self, a, q):
        return next(
            s["options"]
            for s in a["questionnaire"]["response_sets"]
            if s["id"] == q["response_set_id"]
        )

    def test_all_records_validate_and_references_resolve(self):
        validator = Draft202012Validator(read(HERE / "definition-v2.1.schema.json"))
        self.assertEqual(len(self.rows), 186)
        self.assertEqual(
            sum(len(a["questionnaire"]["items"]) for a in self.rows.values()), 4927
        )
        for a in self.rows.values():
            validator.validate(a)
            self.assertEqual(
                a["questionnaire"]["item_count"], len(a["questionnaire"]["items"])
            )
            sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
            for q in a["questionnaire"]["items"]:
                Draft202012Validator.check_schema(q["input_spec"]["answer_schema"])
                if q["response_set_id"] is not None:
                    opts = sets[q["response_set_id"]]["options"]
                    self.assertEqual(len(opts), len({o["id"] for o in opts}))
                    if q["selection_mode"] == "single":
                        for o in opts:
                            Draft202012Validator(
                                q["input_spec"]["answer_schema"]
                            ).validate(o["id"])

    def test_existing_answers_ids_and_content_preserved(self):
        repaired = {(r["assessment_id"], r["item_id"]) for r in self.rules["questions"]}
        modified = {
            r["assessment_id"] for r in self.rules["questions"] + self.rules["contexts"]
        }
        for key, a in self.rows.items():
            old = self.previous[key]
            if key not in modified:
                self.assertEqual(a, old)
            for field in [
                "context_sections",
                "references",
                "tables",
                "assets",
                "source_documents",
                "scoring",
                "administration",
            ]:
                self.assertEqual(a[field], old[field])
            self.assertEqual(
                [q["id"] for q in a["questionnaire"]["items"]],
                [q["id"] for q in old["questionnaire"]["items"]],
            )
            for oq in old["questionnaire"]["items"]:
                q = self.question(a, oq["id"])
                if (key, q["id"]) not in repaired:
                    self.assertEqual(q["text"], oq["text"])
                if oq["response_set_id"] is not None:
                    new_options = {o["id"]: o for o in self.options(a, q)}
                    for option in self.options(old, oq):
                        self.assertEqual(new_options[option["id"]], option)

    def test_all_47_stems_match_the_archived_pdf(self):
        self.assertEqual(len(self.rules["questions"]), 47)
        for rule in self.rules["questions"]:
            a = self.rows[rule["assessment_id"]]
            q = self.question(a, rule["item_id"])
            with checked_pdf(a, rule["source_sha256"]) as pdf:
                self.assertEqual(
                    q["text"], source_text(pdf, rule["stem_page"], rule["stem_bbox"])
                )
            self.assertNotRegex(q["text"], r"^\d+ [A-Z ]+$")
            self.assertEqual(q["response_type"], "single_choice")

    def test_vanderbilt_full_wording_and_five_options(self):
        for prefix, start, end in [
            ("vanderbilt-adhd-diagnostic-parent", 48, 55),
            ("vanderbilt-adhd-diagnostic-teacher", 36, 43),
        ]:
            a = self.get(prefix)
            for n in range(start, end + 1):
                q = self.question(a, "Q" + str(n))
                opts = self.options(a, q)
                self.assertEqual([o["printed_value"] for o in opts], [1, 2, 3, 4, 5])
                self.assertEqual(opts[0]["label"], "PROBLEMATIC")
                self.assertEqual(opts[0]["id"], "O5")
        self.assertEqual(
            self.question(self.get("vanderbilt-adhd-diagnostic-parent"), "Q49")["text"],
            "How is your child doing in reading?",
        )

    def test_ccq_scales_and_context(self):
        a = self.get("composite-caregiving")
        for n in range(4, 28):
            q = self.question(a, "Q" + str(n))
            values = [o["printed_value"] for o in self.options(a, q)]
            self.assertEqual(
                values,
                list(range(10, -1, -1))
                if n == 15
                else list(range(11))
                if n <= 20
                else list(range(1, 6)),
            )
        self.assertEqual(
            self.question(a, "Q4")["text"],
            "I am able to explain things patiently to my child.",
        )
        self.assertIn("last 4 weeks", self.question(a, "Q16")["context_text"])
        self.assertIn("18 statements", self.question(a, "Q28")["context_text"])

    def test_csi_semantic_pairs_and_bsl_percentage_scale(self):
        csi = self.get("couples-satisfaction-index-csi-16")
        pairs = [
            ("INTERESTING", "BORING"),
            ("BAD", "GOOD"),
            ("FULL", "EMPTY"),
            ("STURDY", "FRAGILE"),
            ("DISCOURAGING", "HOPEFUL"),
            ("ENJOYABLE", "MISERABLE"),
        ]
        for n, pair in zip(range(11, 17), pairs):
            q = self.question(csi, "Q" + str(n))
            opts = self.options(csi, q)
            self.assertIn("how you feel about your relationship", q["text"])
            self.assertEqual(len(opts), 6)
            self.assertEqual((opts[0]["label"], opts[-1]["label"]), pair)
            self.assertEqual(sorted(o["printed_value"] for o in opts), list(range(6)))
        bsl = self.get("borderline-symptom-list")
        q = self.question(bsl, "Q24")
        self.assertIn("overall personal state", q["text"])
        self.assertEqual(
            [o["printed_value"] for o in self.options(bsl, q)], list(range(0, 101, 10))
        )

    def test_shared_prompts_and_review_limits(self):
        self.assertEqual(
            self.bundle["summary"]["items_with_recovered_shared_prompts"], 53
        )
        self.assertIn(
            "diagnosed",
            self.question(self.get("childhood-autism-spectrum-test"), "Q39")[
                "context_text"
            ],
        )
        self.assertIn(
            "since the event",
            self.question(self.get("preschool-anxiety"), "Q31")["context_text"],
        )
        self.assertEqual(
            self.get("strengths-and-difficulties")["questionnaire"]["items"], []
        )
        for a in self.rows.values():
            self.assertFalse(a["scoring"]["enabled"])
            self.assertFalse(a["review"]["ready_for_clinical_use"])
            self.assertFalse(a["review"]["questionnaire_completeness_verified"])

    def test_changed_source_or_input_fails_closed(self):
        wrong = copy.deepcopy(self.rules)
        wrong["questions"][0]["old_text"] = "wrong text"
        with self.assertRaisesRegex(ValueError, "differs from reviewed input"):
            recover(self.old, wrong)
        wrong = copy.deepcopy(self.rules)
        wrong["questions"][0]["text"] = "not the source question"
        with self.assertRaisesRegex(ValueError, "no longer matches PDF"):
            recover(self.old, wrong)


if __name__ == "__main__":
    unittest.main(verbosity=2)
