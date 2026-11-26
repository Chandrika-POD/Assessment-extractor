"""Regression checks for the source-driven response repair and consumer contract."""

import json
import os
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("ASSESSMENT_PROJECT", str(HERE.parents[1])))
FINAL = Path(
    os.environ.get(
        "ASSESSMENT_FINAL_JSON",
        str(
            PROJECT
            / "assessment-exports/novopsych-all-186-assessments-final-20261113.json"
        ),
    )
)


class ResponseBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = json.loads(FINAL.read_text())
        cls.rows = cls.bundle["assessments"]
        old = (
            PROJECT
            / "assessment-exports/novopsych-all-186-assessments-repaired-20261113.json"
        )
        cls.old = {
            a["assessment_id"]: a for a in json.loads(old.read_text())["assessments"]
        }

    def get(self, prefix):
        rows = [a for a in self.rows if a["assessment_id"].startswith(prefix)]
        self.assertEqual(len(rows), 1, prefix)
        return rows[0]

    def item(self, a, i):
        return next(q for q in a["questionnaire"]["items"] if q["id"] == i)

    def valid(self, q, value):
        Draft202012Validator(q["input_spec"]["answer_schema"]).validate(value)

    def invalid(self, q, value):
        with self.assertRaises(ValidationError):
            self.valid(q, value)

    def test_schema_all_records_and_all_answer_schemas(self):
        schema = json.loads((HERE / "definition-v2.1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual(len(self.rows), 186)
        self.assertEqual({a["assessment_id"] for a in self.rows}, set(self.old))
        for a in self.rows:
            with self.subTest(assessment=a["assessment_id"]):
                validator.validate(a)
                ids = [q["id"] for q in a["questionnaire"]["items"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(ids, a["administration"]["item_order"])
                self.assertEqual(len(ids), a["questionnaire"]["item_count"])
                for q in a["questionnaire"]["items"]:
                    Draft202012Validator.check_schema(q["input_spec"]["answer_schema"])

    def test_all_previously_untyped_fields_resolved_and_no_data_dropped(self):
        resolved = 0
        extra = 0
        for a in self.rows:
            old = self.old[a["assessment_id"]]
            new = {q["id"]: q for q in a["questionnaire"]["items"]}
            self.assertEqual(a["context_sections"], old["context_sections"])
            self.assertEqual(a["references"], old["references"])
            self.assertEqual(a["tables"], old["tables"])
            self.assertEqual(a["scoring"], old["scoring"])
            for q in old["questionnaire"]["items"]:
                self.assertIn(q["id"], new)
                if q["response_type"] == "unverified":
                    self.assertNotEqual(new[q["id"]]["response_type"], "unverified")
                    resolved += 1
                if not (
                    a["assessment_id"].startswith("multilevel-") and q["id"] == "Q74"
                ):
                    self.assertEqual(q["text"], new[q["id"]]["text"])
            extra += len(new) - len(old["questionnaire"]["items"])
        self.assertEqual(resolved, 87)
        self.assertEqual(extra, 8)
        self.assertEqual(self.bundle["summary"]["recovered_item_count"], 4927)

    def test_nonchoice_inputs_do_not_fabricate_response_sets(self):
        for a in self.rows:
            sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
            for q in a["questionnaire"]["items"]:
                if q["response_type"] in ["integer", "number", "text"]:
                    self.assertIsNone(q["response_set_id"])
                    self.assertIsNone(q["selection_mode"])
                else:
                    self.assertIn(q["response_set_id"], sets)
                    self.assertGreaterEqual(
                        len(sets[q["response_set_id"]]["options"]), 2
                    )
                    for opt in sets[q["response_set_id"]]["options"]:
                        self.assertTrue(opt["display_label"])
                        if opt["label"] is None:
                            self.assertEqual(
                                opt["display_label"], str(opt["printed_value"])
                            )

    def test_numeric_count_bounds_and_na_preserved(self):
        bam = self.get("brief-addiction-monitor-bam--")
        q = self.item(bam, "Q2")
        for value in [0, 17, 30]:
            self.valid(q, value)
        for value in [-1, 31, 1.5, "NA", "5"]:
            self.invalid(q, value)
        ed = self.get("eating-disorder-15ed-15--")
        for iid in ["Q11", "Q12", "Q13"]:
            self.valid(self.item(ed, iid), "NA")
            self.valid(self.item(ed, iid), 0)
        self.valid(self.item(ed, "Q13"), 7)
        self.invalid(self.item(ed, "Q13"), 8)
        self.invalid(self.item(ed, "Q14"), "NA")
        q = self.item(
            self.get("kessler-psychological-distress-scale-plus-k10--"), "Q13"
        )
        self.valid(q, 40)
        self.invalid(q, 1.5)

    def test_map_sy_checkbox_options_and_exclusive_none(self):
        a = self.get("multilevel-assessment-of-psychopathology-mapsy--")
        q = self.item(a, "Q74")
        self.assertEqual(q["response_type"], "multiple_choice")
        self.valid(q, ["O1", "O3"])
        self.valid(q, ["O8"])
        for value in [["O8", "O1"], ["O1", "O1"], [], "O1", ["O99"]]:
            self.invalid(q, value)
        opts = next(
            s["options"]
            for s in a["questionnaire"]["response_sets"]
            if s["id"] == q["response_set_id"]
        )
        self.assertEqual(len(opts), 8)
        self.assertTrue(all(o["score"] is None for o in opts))
        self.assertEqual(
            q["text"],
            "In the past year, which of the following substances have you used?",
        )

    def test_pardi_unnumbered_measurements_and_units(self):
        for prefix in [
            "pardi-ar-q-arfid-questionnaire--",
            "pica-arfid-and-rumination-disorder-interview-arfid-questionnaire-informant-report-par--",
        ]:
            a = self.get(prefix)
            self.assertEqual(a["questionnaire"]["item_count"], 33)
            for iid in [
                "Q1_height_cm",
                "Q1_height_feet",
                "Q1_height_inches",
                "Q2_weight",
            ]:
                q = self.item(a, iid)
                self.valid(q, 12.5)
                self.invalid(q, -1)
                self.assertEqual(
                    q["source"]["method"], "unnumbered_pdf_field_visually_checked"
                )
            weight = self.item(a, "Q2_weight")
            self.assertEqual(weight["input_spec"]["unit_from_item"]["item_id"], "Q2")
            for iid in ["Q13", "Q15", "Q17"]:
                q = self.item(a, iid)
                self.assertEqual(q["response_type"], "text")
                self.valid(q, "Product name and amount")
                self.invalid(q, 3)
                self.assertEqual(q["printed_input_unit"], "days")

    def test_written_fields_and_group_instructions(self):
        css = self.get("client-satisfaction-survey-css--")
        self.valid(self.item(css, "Q9"), "Communication")
        self.invalid(self.item(css, "Q9"), 1)
        choci = self.get("obsessional-compulsive-inventory-ocd-child-self-report--")
        for iid in ["Q11", "Q12", "Q13"]:
            self.assertIn("habit", self.item(choci, iid)["context_text"].lower())
        for iid in ["Q30", "Q31", "Q32"]:
            self.assertIn("thought", self.item(choci, iid)["context_text"].lower())
        ccq = self.get("composite-caregiving-questionnaire-ccq--")
        self.valid(self.item(ccq, "Q2"), "4 years and 6 months")

    def test_conditions_reference_existing_items_and_options(self):
        for a in self.rows:
            qs = {q["id"]: q for q in a["questionnaire"]["items"]}
            sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
            for q in qs.values():
                if "display_if" not in q:
                    continue
                condition = q["display_if"]
                self.assertIn(condition["item_id"], qs)
                previous = qs[condition["item_id"]]
                self.assertIn(
                    condition["value"],
                    [o["id"] for o in sets[previous["response_set_id"]]["options"]],
                )
        asq = self.get("ask-suicide-screening-questionnaire-asq--")
        self.assertEqual(self.item(asq, "Q5")["display_if"]["item_id"], "Q4")
        self.assertEqual(self.item(asq, "Q8")["display_if"]["item_id"], "Q7")

    def test_live_source_checks_and_source_page_text(self):
        checks = json.loads((HERE / "source-checks.json").read_text())
        self.assertEqual(len(checks), 24)
        self.assertTrue(
            all(
                c["matches_archived_pdf"] and c["status"] == "verified_live"
                for c in checks
            )
        )
        pages = 0
        ocr = 0
        for a in self.rows:
            for d in a["source_documents"]:
                self.assertEqual(d["page_count"], len(d["pages"]))
                self.assertEqual(
                    [p["page"] for p in d["pages"]], list(range(1, d["page_count"] + 1))
                )
                self.assertFalse(d["runtime_context_allowed"])
                for p in d["pages"]:
                    self.assertFalse(p["image_only_text_unresolved"])
                    self.assertTrue(p["text"].strip())
                    pages += 1
                    ocr += p["method"] == "ocr"
        self.assertEqual(pages, 432)
        self.assertEqual(ocr, 14)

    def test_sdq_remains_explicitly_blocked_and_scoring_disabled(self):
        sdq = self.get("strengths-and-difficulties-questionnaire-sdq--")
        self.assertEqual(sdq["questionnaire"]["items"], [])
        self.assertFalse(sdq["review"]["response_structure_complete"])
        self.assertEqual(
            sdq["rights"]["digital_questionnaire_status"],
            "publisher_authorization_required",
        )
        self.assertEqual(
            sum(a["review"]["response_structure_complete"] for a in self.rows), 185
        )
        for a in self.rows:
            self.assertFalse(a["scoring"]["enabled"])
            self.assertFalse(a["review"]["ready_for_clinical_use"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
