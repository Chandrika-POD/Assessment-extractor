import hashlib
import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from paths import BUNDLE
from scoring_rules import score_draft


class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
        cls.rows = cls.bundle["assessments"]

    def get(self, prefix):
        found = [d for d in self.rows if d["assessment_id"].startswith(prefix)]
        self.assertEqual(len(found), 1, prefix)
        return found[0]

    def answers(self, d, index):
        sets = {s["id"]: s for s in d["questionnaire"]["response_sets"]}
        return {
            q["id"]: sets[q["response_set_id"]]["options"][index]["id"]
            for q in d["questionnaire"]["items"]
        }

    def test_schema_and_references_all_186(self):
        schema = json.loads(
            Path(__file__)
            .with_name("definition.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual(len(self.rows), 186)
        self.assertEqual(len({d["assessment_id"] for d in self.rows}), 186)
        for d in self.rows:
            with self.subTest(assessment=d["assessment_id"]):
                validator.validate(d)
                qs = d["questionnaire"]["items"]
                sets = {s["id"]: s for s in d["questionnaire"]["response_sets"]}
                self.assertEqual(d["questionnaire"]["item_count"], len(qs))
                self.assertEqual(
                    [q["id"] for q in qs], d["administration"]["item_order"]
                )
                self.assertEqual([q["order"] for q in qs], list(range(1, len(qs) + 1)))
                self.assertEqual(len({q["id"] for q in qs}), len(qs))
                self.assertTrue(
                    all(
                        q["response_set_id"] in sets or q["response_set_id"] is None
                        for q in qs
                    )
                )
                for s in sets.values():
                    self.assertEqual(
                        len({o["id"] for o in s["options"]}), len(s["options"])
                    )
                for rule in d["scoring"]["rules"]:
                    self.assertTrue(
                        set(rule["item_ids"]) <= set(d["administration"]["item_order"])
                    )
                if not d["scoring"]["rules"]:
                    self.assertTrue(
                        all(
                            o["score"] is None
                            for s in sets.values()
                            for o in s["options"]
                        )
                    )

    def test_recovered_counts_and_bibliography_excluded(self):
        expected = {
            "generalised-anxiety-disorder-assessment-gad-7--": 7,
            "patient-health-questionnaire-depression-phq-9--": 9,
            "depression-anxiety-stress-scales-short-form-dass-21--": 21,
            "dar-5--": 5,
            "the-montgomery-asberg-rating-scale-madrs--": 10,
            "ptsd-checklist-5-pcl-5--": 20,
            "international-personality-item-pool-neo-120-item-version-ipip-neo-120--": 120,
            "general-behaviour-inventory-gbi--": 73,
            "clinical-outcomes-in-routine-evaluation-core-om--": 34,
            "clinical-outcomes-in-routine-evaluation-10-core-10--": 10,
            "young-persons-core-yp-core--": 10,
            "repetitive-behaviours-questionnaire-3--": 20,
            "valuing-questionnaire-vq--": 10,
            "eating-attitudes-test-26-eat-26--": 31,
            "problem-gambling-severity-index-pgsi--": 9,
        }
        for prefix, n in expected.items():
            self.assertEqual(self.get(prefix)["questionnaire"]["item_count"], n, prefix)
        dar = self.get("dar-5--")
        self.assertNotIn("Forbes", json.dumps(dar["questionnaire"]["items"]))
        madrs = self.get("the-montgomery-asberg-rating-scale-madrs--")
        for s in madrs["questionnaire"]["response_sets"]:
            self.assertEqual([o["printed_value"] for o in s["options"]], list(range(7)))

    def test_full_instructions_and_subquestions(self):
        dass = self.get("depression-anxiety-stress-scales-short-form-dass-21--")[
            "administration"
        ]["instructions"]
        for phrase in ["Never", "Sometimes", "Often", "Almost Always", "past week"]:
            self.assertIn(phrase, dass)
        pcl = self.get("ptsd-checklist-5-pcl-5--")["administration"]["instructions"]
        self.assertIn("last month", pcl.lower())
        bam = self.get("brief-addiction-monitor-bam--")["questionnaire"]["items"]
        self.assertEqual(
            [q["source_label"] for q in bam[6:13]],
            ["7A", "7B", "7C", "7D", "7E", "7F", "7G"],
        )
        self.assertEqual(bam[1]["printed_input_unit"], "days")
        self.assertTrue(bam[1]["text"].startswith("In the past 30 days"))
        crafft = self.get("crafft-substance-use-assessment-crafft-2-1-n--")[
            "questionnaire"
        ]["items"]
        self.assertIn("edibles", crafft[1]["text"])
        self.assertIn("synthetic", crafft[1]["text"])
        self.assertEqual(crafft[1]["printed_input_unit"], "days")

    def test_no_sample_report_in_model_context(self):
        for d in self.rows:
            for c in d["context_sections"]:
                self.assertFalse(c["title"].startswith("Document:"))
                self.assertFalse(re.search("sample (results|report)", c["title"], re.I))
            self.assertNotIn("assets", d["conversation_policy"]["context_allowlist"])
            self.assertFalse(d["review"]["ready_for_clinical_use"])
            self.assertFalse(d["scoring"]["enabled"])

    def test_nested_yes_no_cells_are_separate_from_question(self):
        for prefix, label in [
            ("brief-addiction-monitor-bam--", "14"),
            ("pardi-ar-q-arfid-questionnaire--", "3"),
            (
                "mascc-unmet-needs-assessment-for-cancer-related-cognitive-impairment-impact-mascc-cog--",
                "1",
            ),
        ]:
            d = self.get(prefix)
            q = next(
                q for q in d["questionnaire"]["items"] if q["source_label"] == label
            )
            sets = {s["id"]: s for s in d["questionnaire"]["response_sets"]}
            self.assertEqual(
                {o["label"] for o in sets[q["response_set_id"]]["options"]},
                {"YES", "NO"},
            )
            self.assertNotRegex(q["text"], r"\b(?:YES|NO)\b")

    def test_asset_paths_and_selected_pdf_hashes(self):
        checked = {}
        for d in self.rows:
            for a in d["assets"]:
                if a["archive_path"]:
                    self.assertTrue(
                        Path(a["archive_path"]).is_file(), a["archive_path"]
                    )
                if a["role"] == "selected_questionnaire":
                    p = Path(a["archive_path"])
                    if str(p) not in checked:
                        checked[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
                    self.assertEqual(checked[str(p)], a["sha256"])
            if d["questionnaire"]["items"]:
                self.assertTrue(
                    any(a["role"] == "selected_questionnaire" for a in d["assets"])
                )

    def test_gad7_boundary_scores_and_missing_invalid_answers(self):
        d = self.get("generalised-anxiety-disorder-assessment-gad-7--")
        for total, band in [
            (0, "None-Minimal"),
            (4, "None-Minimal"),
            (5, "Mild"),
            (9, "Mild"),
            (10, "Moderate"),
            (14, "Moderate"),
            (15, "Severe"),
            (21, "Severe"),
        ]:
            remaining = total
            answers = {}
            for q in d["questionnaire"]["items"]:
                value = min(remaining, 3)
                remaining -= value
                answers[q["id"]] = "O" + str(value + 1)
            result = score_draft(d, answers)["total_raw"]
            self.assertEqual(result, {"score": total, "band": band})
        answers = self.answers(d, 0)
        del answers["Q7"]
        self.assertIsNone(score_draft(d, answers)["total_raw"])
        with self.assertRaises(ValueError):
            score_draft(d, {"Q1": "O99"})
        with self.assertRaises(ValueError):
            score_draft(d, {"Q99": "O1"})

    def test_reverse_weights_not_double_reversed(self):
        d = self.get("clinical-outcomes-in-routine-evaluation-10-core-10--")
        answers = self.answers(d, 0)
        self.assertEqual(score_draft(d, answers)["total_raw"]["score"], 8)
        answers["Q2"] = "O5"
        answers["Q3"] = "O5"
        self.assertEqual(score_draft(d, answers)["total_raw"]["score"], 0)

    def test_dass_subscales_and_vq_no_invented_total(self):
        d = self.get("depression-anxiety-stress-scales-short-form-dass-21--")
        result = score_draft(d, self.answers(d, -1))
        self.assertEqual(result["total_raw"]["score"], 63)
        for scale in ["depression", "anxiety", "stress"]:
            self.assertEqual(result[scale + "_raw"]["score"], 21)
            self.assertEqual(result[scale + "_doubled"]["score"], 42)
        v = self.get("valuing-questionnaire-vq--")
        result = score_draft(v, self.answers(v, -1))
        self.assertEqual(set(result), {"progress", "obstruction"})
        self.assertTrue(all(r["score"] == 30 for r in result.values()))

    def test_sdq_blocked_instead_of_fabricated_questions(self):
        d = self.get("strengths-and-difficulties-questionnaire-sdq--")
        self.assertEqual(d["questionnaire"]["items"], [])
        self.assertIn(
            "variant_selection_required", [i["code"] for i in d["review"]["issues"]]
        )
        with self.assertRaises(ValueError):
            score_draft(d, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
