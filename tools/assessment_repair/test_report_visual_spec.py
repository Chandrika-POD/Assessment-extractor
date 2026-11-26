"""Tests for the report visual specification contract and AIS pilot."""

import copy
import json
import unittest
from pathlib import Path

from validate_report_visual_spec import DEFAULT_SCHEMA, PROJECT, schema_errors, semantic_errors


AIS = (
    PROJECT
    / "assessment-exports/report-specifications/assessments"
    / "athens-insomnia-scale-ais--456d2e3fe9f5.visual.json"
)


class ReportVisualSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(DEFAULT_SCHEMA.read_text())
        cls.ais = json.loads(AIS.read_text())

    def test_schema_and_pilot_are_json_objects(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.ais["schemaVersion"], "report-visual-spec/1.0.0")

    def test_ais_semantics_and_retained_file_hashes(self):
        self.assertEqual(semantic_errors(self.ais, verify_files=True), [])

    def test_json_schema_when_dependency_is_available(self):
        self.assertEqual(schema_errors(self.ais), [])

    def test_ais_has_two_charts_for_each_visit_mode(self):
        variants = {variant["id"]: variant for variant in self.ais["variants"]}
        self.assertEqual(len(variants["first_administration"]["chartIds"]), 2)
        self.assertEqual(len(variants["repeat_administration"]["chartIds"]), 2)
        self.assertEqual(
            {chart["type"] for chart in self.ais["charts"] if chart["variantId"] == "first_administration"},
            {"vertical_bar"},
        )
        self.assertEqual(
            {chart["type"] for chart in self.ais["charts"] if chart["variantId"] == "repeat_administration"},
            {"line", "multi_line"},
        )

    def test_ais_scoring_and_chart_bindings_are_complete(self):
        metrics = {metric["id"]: metric for metric in self.ais["metricBindings"]}
        self.assertEqual(metrics["metric_total"]["calculation"], "sum(Q1..Q8)")
        self.assertEqual(metrics["metric_sleep_difficulty"]["calculation"], "mean(Q1..Q5)")
        self.assertEqual(metrics["metric_daytime_consequences"]["calculation"], "mean(Q6..Q8)")
        bound = {
            series["metricId"]
            for chart in self.ais["charts"]
            for series in chart["series"]
        }
        self.assertEqual(bound, set(metrics))

    def test_validator_rejects_unknown_metric_and_wrong_table_width(self):
        invalid = copy.deepcopy(self.ais)
        invalid["charts"][0]["series"][0]["metricId"] = "missing_metric"
        invalid["tables"][0]["columns"][0]["widthPercent"] = 1
        errors = semantic_errors(invalid, verify_files=False)
        self.assertTrue(any("unknown metric" in error for error in errors))
        self.assertTrue(any("column widths" in error for error in errors))

    def test_validator_rejects_chart_count_and_invalid_range(self):
        invalid = copy.deepcopy(self.ais)
        invalid["variants"][0]["chartIds"].pop()
        invalid["metricBindings"][0]["minimum"] = 24
        errors = semantic_errors(invalid, verify_files=False)
        self.assertTrue(any("expected 2" in error for error in errors))
        self.assertTrue(any("minimum must be below maximum" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
