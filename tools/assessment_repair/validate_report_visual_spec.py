"""Validate source-bound report visual specifications.

JSON Schema validation runs when jsonschema is installed. Semantic validation is
always run because cross-references and source-file hashes are not expressible in
the JSON Schema alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
DEFAULT_SCHEMA = HERE / "report-visual-spec.schema.json"


def _duplicates(values):
    seen = set()
    return sorted({value for value in values if value in seen or seen.add(value)})


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_errors(spec, schema_path=DEFAULT_SCHEMA, require_jsonschema=False):
    """Return JSON Schema errors, or an explicit dependency error when required."""
    schema = json.loads(Path(schema_path).read_text())
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        return (["jsonschema is not installed"] if require_jsonschema else [])
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(spec), key=lambda item: list(item.absolute_path)):
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        errors.append(f"{location}: {error.message}")
    return errors


def semantic_errors(spec, project=PROJECT, verify_files=True):
    """Check IDs, bindings, ranges, variants and retained-source integrity."""
    errors = []
    collections = {
        "metric": spec.get("metricBindings", []),
        "variant": spec.get("variants", []),
        "section": spec.get("sections", []),
        "chart": spec.get("charts", []),
        "table": spec.get("tables", []),
        "asset": spec.get("assets", []),
        "source": spec.get("sources", []),
        "interpretation": spec.get("interpretationRules", []),
    }
    ids = {}
    for label, rows in collections.items():
        row_ids = [row.get("id") for row in rows]
        for duplicate in _duplicates(row_ids):
            errors.append(f"Duplicate {label} id: {duplicate}")
        ids[label] = set(row_ids)

    required_rules = set(spec.get("definitionRef", {}).get("requiredRuleIds", []))
    bound_rules = {row.get("ruleId") for row in collections["metric"]}
    if required_rules != bound_rules:
        errors.append(
            "Metric rule bindings differ from definitionRef.requiredRuleIds: "
            f"missing={sorted(required_rules - bound_rules)}, extra={sorted(bound_rules - required_rules)}"
        )

    for metric in collections["metric"]:
        if metric.get("minimum", 0) >= metric.get("maximum", 0):
            errors.append(f"Metric {metric.get('id')} minimum must be below maximum")

    chart_by_id = {row.get("id"): row for row in collections["chart"]}
    for chart in collections["chart"]:
        chart_id = chart.get("id")
        if chart.get("variantId") not in ids["variant"]:
            errors.append(f"Chart {chart_id} references unknown variant {chart.get('variantId')}")
        for series in chart.get("series", []):
            if series.get("metricId") not in ids["metric"]:
                errors.append(f"Chart {chart_id} references unknown metric {series.get('metricId')}")
        for axis_name in ("xAxis", "yAxis"):
            axis = chart.get(axis_name, {})
            if axis.get("minimum", 0) >= axis.get("maximum", 0):
                errors.append(f"Chart {chart_id} {axis_name} minimum must be below maximum")
        y_axis = chart.get("yAxis", {})
        for band in chart.get("bands", []):
            if band.get("from", 0) >= band.get("to", 0):
                errors.append(f"Chart {chart_id} has an invalid band range")
            if band.get("from", 0) < y_axis.get("minimum", 0) or band.get("to", 0) > y_axis.get("maximum", 0):
                errors.append(f"Chart {chart_id} has a band outside its y-axis")
        gradient = chart.get("gradient")
        if gradient and not y_axis.get("minimum", 0) <= gradient.get("from", 0) < gradient.get("to", 0) <= y_axis.get("maximum", 0):
            errors.append(f"Chart {chart_id} gradient is outside or reversed on its y-axis")

    for variant in collections["variant"]:
        variant_id = variant.get("id")
        for chart_id in variant.get("chartIds", []):
            if chart_id not in ids["chart"]:
                errors.append(f"Variant {variant_id} references unknown chart {chart_id}")
            elif chart_by_id[chart_id].get("variantId") != variant_id:
                errors.append(f"Variant {variant_id} includes chart {chart_id} owned by another variant")
        for section_id in variant.get("sectionIds", []):
            if section_id not in ids["section"]:
                errors.append(f"Variant {variant_id} references unknown section {section_id}")

    for section in collections["section"]:
        section_id = section.get("id")
        if section.get("chartId") and section["chartId"] not in ids["chart"]:
            errors.append(f"Section {section_id} references unknown chart {section['chartId']}")
        if section.get("tableId") and section["tableId"] not in ids["table"]:
            errors.append(f"Section {section_id} references unknown table {section['tableId']}")

    for table in collections["table"]:
        table_id = table.get("id")
        width = sum(column.get("widthPercent", 0) for column in table.get("columns", []))
        if abs(width - 100) > 0.01:
            errors.append(f"Table {table_id} column widths sum to {width}, not 100")
        image_asset_id = table.get("imageAssetId")
        if image_asset_id and image_asset_id not in ids["asset"]:
            errors.append(f"Table {table_id} references unknown image asset {image_asset_id}")
        if table.get("type") == "image_only" and not image_asset_id:
            errors.append(f"Image-only table {table_id} must reference an asset")

    validation = spec.get("validation", {})
    expected_by_variant = {
        "first_administration": validation.get("expectedFirstVisitChartCount"),
        "repeat_administration": validation.get("expectedRepeatVisitChartCount"),
    }
    for variant in collections["variant"]:
        expected = expected_by_variant.get(variant.get("id"))
        if expected is not None and expected != len(variant.get("chartIds", [])):
            errors.append(
                f"Variant {variant.get('id')} has {len(variant.get('chartIds', []))} charts; expected {expected}"
            )

    if verify_files:
        for kind in ("source", "asset"):
            for row in collections[kind]:
                relative = row.get("archivePath") if kind == "source" else row.get("path")
                if not relative:
                    continue
                path = Path(relative)
                if not path.is_absolute():
                    path = Path(project) / path
                if not path.is_file():
                    errors.append(f"Missing {kind} file for {row.get('id')}: {path}")
                elif _sha256(path) != row.get("sha256"):
                    errors.append(f"SHA-256 mismatch for {kind} {row.get('id')}: {path}")
    return errors


def validate(path, schema_path=DEFAULT_SCHEMA, require_jsonschema=False, verify_files=True):
    spec = json.loads(Path(path).read_text())
    return schema_errors(spec, schema_path, require_jsonschema) + semantic_errors(
        spec, project=PROJECT, verify_files=verify_files
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--require-jsonschema", action="store_true")
    parser.add_argument("--skip-file-checks", action="store_true")
    args = parser.parse_args()
    errors = validate(
        args.spec,
        schema_path=args.schema,
        require_jsonschema=args.require_jsonschema,
        verify_files=not args.skip_file_checks,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(f"OK: {args.spec}")


if __name__ == "__main__":
    main()
