"""Explicit draft rules checked against saved source text; never clinical approval."""

import re


def band(label, low, high):
    return {"label": label, "minimum_inclusive": low, "maximum_inclusive": high}


def configure(key, items, response_sets, source_text):
    rules = []
    kind = None
    bands = []
    tokens = {
        "generalised-anxiety-disorder-assessment-gad-7--": ("GAD7", 7, 0, 3),
        "patient-health-questionnaire-depression-phq-9--": ("PHQ9", 9, 0, 3),
        "depression-anxiety-stress-scales-short-form-dass-21--": ("DASS21", 21, 0, 3),
        "dar-5--": ("DAR5", 5, 1, 5),
        "the-montgomery-asberg-rating-scale-madrs--": ("MADRS", 10, 0, 6),
        "ptsd-checklist-5-pcl-5--": ("PCL5", 20, 0, 4),
        "clinical-outcomes-in-routine-evaluation-10-core-10--": ("CORE10", 10, 0, 4),
        "valuing-questionnaire-vq--": ("VQ", 10, 0, 6),
    }
    sets = {s["id"]: s for s in response_sets}
    for token, settings in tokens.items():
        if not key.startswith(token):
            continue
        kind, n, low, high = settings
        assert len(items) == n and [q["source_label"] for q in items] == [
            str(i) for i in range(1, n + 1)
        ]
        for q in items:
            options = sets[q["response_set_id"]]["options"]
            assert sorted(o["printed_value"] for o in options) == list(
                range(low, high + 1)
            ), (key, q["id"])
            for o in options:
                o["score"] = o["printed_value"]
            q["reverse_scored"] = (
                (q["source_label"] in ["2", "3"]) if kind == "CORE10" else False
            )
        if kind == "GAD7":
            bands = [
                band("None-Minimal", 0, 4),
                band("Mild", 5, 9),
                band("Moderate", 10, 14),
                band("Severe", 15, 21),
            ]
        elif kind == "PHQ9":
            bands = [
                band("No or minimal depression", 0, 4),
                band("Mild depression", 5, 9),
                band("Moderate depression", 10, 14),
                band("Moderate-severe depression", 15, 19),
                band("Severe depression", 20, 27),
            ]
        elif kind == "MADRS":
            bands = [
                band("Normal / no symptoms", 0, 6),
                band("Mild", 7, 19),
                band("Moderate", 20, 30),
                band("Severe", 31, 39),
                band("Extremely severe", 40, 60),
            ]
        elif kind == "CORE10":
            bands = [
                band("Healthy", 0, 5),
                band("Low Level", 6, 10),
                band("Mild", 11, 14),
                band("Moderate", 15, 19),
                band("Moderate-to-Severe", 20, 24),
                band("Severe", 25, 40),
            ]

        def rule(name, nums, multiplier=1):
            return {
                "id": name,
                "method": "sum",
                "item_ids": ["Q" + str(i) for i in nums],
                "multiplier": multiplier,
                "value_field": "score",
                "minimum": low * len(nums) * multiplier,
                "maximum": high * len(nums) * multiplier,
                "severity_bands": [],
            }

        if kind not in ("VQ",):
            total = rule("total_raw", list(range(1, n + 1)))
            total["severity_bands"] = bands
            rules.append(total)
        if kind == "DASS21":
            for name, nums in [
                ("depression", [3, 5, 10, 13, 16, 17, 21]),
                ("anxiety", [2, 4, 7, 9, 15, 19, 20]),
                ("stress", [1, 6, 8, 11, 12, 14, 18]),
            ]:
                rules.append(rule(name + "_raw", nums))
                rules.append(rule(name + "_doubled", nums, 2))
        if kind == "VQ":
            rules = [
                rule("progress", [3, 4, 5, 7, 9]),
                rule("obstruction", [1, 2, 6, 8, 10]),
            ]
        break
    candidates = []
    for line in source_text.splitlines():
        if re.search(
            r"\b(sum|average|reverse.scor|multiply|divid|cut.?off|threshold)\b",
            line,
            re.I,
        ):
            text = " ".join(line.split())
            if text and text not in candidates:
                candidates.append(text)
    return {
        "status": "source_checked_draft" if rules else "requires_rule_review",
        "enabled": False,
        "disabled_reason": "Independent clinical and administration review is still required before publishing this definition.",
        "rules": rules,
        "coverage": "Selected draft totals/subscales only; additional source thresholds, norms, branching and special administration rules may remain unimplemented.",
        "rules_provenance": "Archived questionnaire printed response values and corresponding scoring context sections; formulas tested separately."
        if rules
        else None,
        "source_rule_excerpts": candidates,
        "missing_item_policy": {
            "origin": "application_policy",
            "action": "withhold_result_if_any_required_response_is_missing",
            "note": "Conservative prototype policy, not a claim that the source prohibits prorating. Source exceptions require an explicit reviewed rule.",
        },
        "percentile_rules": [],
        "percentile_status": "not_implemented_no_unverified_lookup",
        "limitations": [
            "Rules do not establish a diagnosis.",
            "No normative percentile is inferred from sample results or approximate distribution data.",
        ]
        + (
            [
                "DASS-21 raw and doubled outputs are explicit. Severity bands and percentile mappings remain unimplemented."
            ]
            if kind == "DASS21"
            else []
        ),
    }


def score_draft(definition, answers):
    """Test harness for source-checked formulas; not a published runtime endpoint."""
    if definition["scoring"]["status"] != "source_checked_draft":
        raise ValueError("Rules not checked")
    items = {i["id"]: i for i in definition["questionnaire"]["items"]}
    sets = {s["id"]: s for s in definition["questionnaire"]["response_sets"]}
    if set(answers) - set(items):
        raise ValueError("Unknown item")
    selected = {}
    for iid, option_id in answers.items():
        opts = sets[items[iid]["response_set_id"]]["options"]
        opt = next((o for o in opts if o["id"] == option_id), None)
        if opt is None or opt["score"] is None:
            raise ValueError("Invalid or unscored option")
        selected[iid] = opt["score"]
    result = {}
    for r in definition["scoring"]["rules"]:
        if not set(r["item_ids"]) <= set(selected):
            result[r["id"]] = None
            continue
        score = sum(selected[i] for i in r["item_ids"]) * r["multiplier"]
        result[r["id"]] = {
            "score": score,
            "band": next(
                (
                    b["label"]
                    for b in r["severity_bands"]
                    if b["minimum_inclusive"] <= score <= b["maximum_inclusive"]
                ),
                None,
            ),
        }
    return result
