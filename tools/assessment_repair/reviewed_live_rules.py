"""Explicit arithmetic for source-checked ASRS/Vanderbilt/IRIS definitions."""


def additions(a, sections, source):
    key = a["assessment_id"]
    text = "\n".join(
        s["text"]
        for s in sections
        if any(word in s["title"].lower() for word in ["scor", "interpret"])
    )
    rules = []

    def add(
        rid, label, nums, method="sum", threshold=None, operator=">=", thresholds=None
    ):
        items = {q["id"]: q for q in a["questionnaire"]["items"]}
        sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
        by_number = {q["source_label"]: q["id"] for q in items.values()}
        ids = [by_number[str(n)] for n in nums]
        values = [
            [o["printed_value"] for o in sets[items[i]["response_set_id"]]["options"]]
            for i in ids
        ]
        if any(any(v is None for v in opts) for opts in values):
            raise ValueError("Missing source value in explicit rule")
        r = {
            "id": rid,
            "label": label,
            "item_ids": ids,
            "method": method,
            "multiplier": 1,
            "value_field": "printed_value",
            "minimum": 0
            if method == "count_threshold"
            else sum(min(v) for v in values),
            "maximum": len(ids)
            if method == "count_threshold"
            else sum(max(v) for v in values),
            "severity_bands": [],
            "status": "source_arithmetic_draft",
            "enabled": False,
            "source": {
                **source,
                "section": "Scoring & Interpretation",
                "method": "reviewed_explicit_source_rule",
            },
            "missing_item_policy": "withhold_if_any_required_answer_is_missing",
            "coverage": "Raw dimensional or symptom-count output only. Diagnosis and normative percentiles are not inferred.",
        }
        if method == "count_threshold":
            r.update(
                threshold=threshold, operator=operator, item_thresholds=thresholds or {}
            )
        if method == "mean":
            r["minimum"] /= len(ids)
            r["maximum"] /= len(ids)
        rules.append(r)

    if key.startswith(
        (
            "adult-adhd-self-report-scale-asrs--",
            "adult-adhd-observer-report-scale-asrs-o--",
        )
    ):
        if "Part A" not in text or "Part B" not in text or "72" not in text:
            raise ValueError("ASRS source guidance changed")
        for rid, nums in [
            ("part_a_raw", range(1, 7)),
            ("part_b_raw", range(7, 19)),
            ("total_raw", range(1, 19)),
        ]:
            add(rid, rid.replace("_", " ").title(), nums)
        if key.startswith("adult-adhd-observer"):
            if "items 1-3, 9, 12, 16, 18" not in text:
                raise ValueError("ASRS-O endorsement source changed")
            thresholds = {"Q" + str(i): 2 for i in [1, 2, 3, 9, 12, 16, 18]}
            add(
                "inattentive_count",
                "Inattentiveness symptom count",
                [1, 2, 3, 4, 7, 8, 9, 10, 11],
                "count_threshold",
                3,
                thresholds=thresholds,
            )
            add(
                "hyperactive_impulsive_count",
                "Hyperactivity/Impulsivity symptom count",
                [5, 6, 12, 13, 14, 15, 16, 17, 18],
                "count_threshold",
                3,
                thresholds=thresholds,
            )
    elif key.startswith(
        ("vanderbilt-adhd-diagnostic-parent", "vanderbilt-adhd-diagnostic-teacher")
    ):
        if (
            "sum scores for each subscale" not in text
            or "often" not in text
            or "scores of 1 or 2" not in text
        ):
            raise ValueError("Vanderbilt scoring source changed")
        parent = key.startswith("vanderbilt-adhd-diagnostic-parent")
        groups = [
            ("inattentive", range(1, 10)),
            ("hyperactive_impulsive", range(10, 19)),
            ("combined", range(1, 19)),
        ]
        groups += (
            [
                ("oppositional", range(19, 27)),
                ("conduct", range(27, 41)),
                ("anxiety_depression", range(41, 48)),
            ]
            if parent
            else [
                ("oppositional_conduct", range(19, 29)),
                ("anxiety_depression", range(29, 36)),
            ]
        )
        for name, nums in groups:
            add(name + "_raw", name.replace("_", " ").title() + " raw score", nums)
            add(
                name + "_symptom_count",
                name.replace("_", " ").title() + " symptom count",
                nums,
                "count_threshold",
                2,
            )
        add(
            "impaired_performance_domains",
            "Number of performance domains rated problematic",
            range(48, 56) if parent else range(36, 44),
            "count_threshold",
            2,
            "<=",
        )
    elif key.startswith("indigenous-risk"):
        if "7-28" not in text or "6-18" not in text:
            raise ValueError("IRIS source ranges changed")
        add("alcohol_drug_risk", "Alcohol and other drug risk", range(1, 8))
        add(
            "mental_health_risk",
            "Mental health and emotional wellbeing risk",
            range(8, 14),
        )
    elif key.startswith("athens-insomnia"):
        if (
            "eight item scores are summed" not in text
            or "average item score" not in text
        ):
            raise ValueError("AIS source changed")
        add("total_raw", "Total", range(1, 9))
        add("sleep_difficulty_mean", "Sleep Difficulty", range(1, 6), "mean")
        add("daytime_consequences_mean", "Daytime Consequences", range(6, 9), "mean")
    elif key.startswith("alexian-brothers"):
        if "sum of the five items" not in text:
            raise ValueError("ABUSI source changed")
        add("total_raw", "Total urge severity", range(1, 6))
    elif key.startswith("borderline-symptom-list"):
        if "summing responses to all 23 items and dividing by 23" not in text:
            raise ValueError("BSL source changed")
        add("total_mean", "Mean of the 23 symptom items", range(1, 24), "mean")
        rules[-1]["coverage"] = (
            "Complete-answer mean only. The source permits at least 21 answers; partial-answer prorating requires review. Item 24 is a separate wellbeing response."
        )
    elif key.startswith("cognitive-flexibility-inventory"):
        if "Sum items 2, 4, 7, 9, 11, 15, 17" not in text:
            raise ValueError("CFI source changed")
        add("total_raw", "Total", range(1, 21))
        add(
            "alternatives_raw",
            "Alternatives",
            [1, 3, 5, 6, 8, 10, 12, 13, 14, 16, 18, 19, 20],
        )
        add("control_raw", "Control", [2, 4, 7, 9, 11, 15, 17])
    elif key.startswith("composite-caregiving"):
        if (
            "A total score is not computed" not in text
            or "items 31, 36, 41 are reverse-scored" not in text
        ):
            raise ValueError("CCQ source changed")
        for rid, nums in [
            ("empathy_understanding", range(4, 10)),
            ("emotion_affection", range(10, 16)),
            ("hostility", range(16, 21)),
            ("caregiving_helplessness", range(21, 28)),
            ("parental_mentalising", range(28, 46)),
        ]:
            add(rid, rid.replace("_", " ").title(), nums)
    elif key.startswith("depression-anxiety-stress-scale-dass-10"):
        if (
            "Items 1, 4, 6, 7, 8, 9" not in text
            or "dividing the raw score by the number of items" not in text
        ):
            raise ValueError("DASS-10 source changed")
        for rid, nums in [
            ("total", range(1, 11)),
            ("anxiety_stress", [1, 4, 6, 7, 8, 9]),
            ("depression", [2, 3, 5, 10]),
        ]:
            add(rid + "_raw", rid.replace("_", " ").title(), nums)
            add(rid + "_mean", rid.replace("_", " ").title() + " mean", nums, "mean")
    elif key.startswith("depression-anxiety-stress-scale-youth"):
        if (
            "between 0 and 63" not in text
            or "Items 3, 5, 10, 13, 16, 17, 21" not in text
        ):
            raise ValueError("DASS-Y source changed")
        add("total_raw", "Total", range(1, 22))
        for name, nums in [
            ("depression", [3, 5, 10, 13, 16, 17, 21]),
            ("anxiety", [2, 4, 7, 9, 15, 19, 20]),
            ("stress", [1, 6, 8, 11, 12, 14, 18]),
        ]:
            add(name + "_raw", name.title(), nums)
    elif key.startswith("depression-anxiety-stress-scales-long-form"):
        if (
            "between 0 and 126" not in text
            or "Items 3, 5, 10, 13, 16, 17, 21, 24, 26, 31, 34, 37, 38, 42" not in text
        ):
            raise ValueError("DASS-42 source changed")
        add("total_raw", "Total", range(1, 43))
        for name, nums in [
            ("depression", [3, 5, 10, 13, 16, 17, 21, 24, 26, 31, 34, 37, 38, 42]),
            ("anxiety", [2, 4, 7, 9, 15, 19, 20, 23, 25, 28, 30, 36, 40, 41]),
            ("stress", [1, 6, 8, 11, 12, 14, 18, 22, 27, 29, 32, 33, 35, 39]),
        ]:
            add(name + "_raw", name.title(), nums)
    elif key.startswith("why-have-sex"):
        if "Each of the 14 subscales is scored by summing its two items" not in text:
            raise ValueError("YSEX scoring changed")
        names = [
            "Stress Reduction",
            "Pleasure",
            "Physical Desirability",
            "Experience Seeking",
            "Resources",
            "Reproduction",
            "Social Status",
            "Revenge",
            "Practical",
            "Love and Commitment",
            "Expression",
            "Self-Esteem Boost",
            "Duty/Pressure",
            "Mate Guarding",
        ]
        for n, label in enumerate(names, 1):
            if f"{label} | {n}, {n + 14} |" not in text:
                raise ValueError("YSEX item membership changed")
            add("subscale_" + str(n), label, [n, n + 14])
    elif key.startswith("children-eating-attitudes"):
        if "Items are summed to obtain a total score" not in text:
            raise ValueError("ChEAT scoring changed")
        add("total_raw", "Total", range(1, 27))
        for label, nums in [
            ("Dieting", [1, 2, 6, 10, 11, 12, 14, 16, 17, 22, 23, 24]),
            ("Restricting and Purging", [2, 7, 9, 10, 17, 22, 23, 24, 26]),
            ("Food Preoccupation", [3, 4, 18, 20, 21]),
            ("Oral Control", [8, 13, 15, 20]),
        ]:
            add(
                label.lower().replace(" ", "_") + "_mean", label + " mean", nums, "mean"
            )
    elif key.startswith("five-facet-mindfulness"):
        if (
            "Average scores are calculated by summing the responses and dividing by the number of items"
            not in text
        ):
            raise ValueError("FFMQ scoring changed")
        add("total_mean", "Total mean", range(1, 16), "mean")
        for n, label in enumerate(
            [
                "Observation",
                "Description",
                "Acting with Awareness",
                "Non-judgmental",
                "Non-reactivity",
            ],
            1,
        ):
            add("subscale_" + str(n), label, [n, n + 5, n + 10], "mean")
    elif key.startswith("frost-multidimensional"):
        if "sum of three of the four subscales (29 items" not in text:
            raise ValueError("FMPS scoring changed")
        groups = [
            (
                "concern_mistakes_doubts",
                [9, 10, 13, 14, 17, 18, 21, 23, 25, 28, 32, 33, 34],
            ),
            ("parental_expectations_criticism", [1, 3, 5, 11, 15, 20, 22, 26, 35]),
            ("personal_standards", [4, 6, 12, 16, 19, 24, 30]),
            ("organisation", [2, 7, 8, 27, 29, 31]),
        ]
        add(
            "total_perfectionism",
            "Total Perfectionism",
            sorted(n for _, nums in groups[:3] for n in nums),
        )
        for label, nums in groups:
            add(label, label.replace("_", " ").title(), nums)
    elif key.startswith(
        (
            "obsessional-compulsive-inventory-ocd-child",
            "obsessional-compulsive-inventory-revised-parent",
        )
    ):
        if "six raw scores by summing item responses" not in text:
            raise ValueError("ChOCI scoring changed")
        groups = [
            ("compulsion_symptoms", list(range(1, 11))),
            ("obsession_symptoms", list(range(20, 30))),
            ("compulsion_impairment", list(range(14, 20))),
            ("obsession_impairment", list(range(33, 39))),
        ]
        for label, nums in groups:
            add(label, label.replace("_", " ").title(), nums)
        add("total_symptoms", "Total Symptoms", groups[0][1] + groups[1][1])
        add("total_impairment", "Total Impairment", groups[2][1] + groups[3][1])
    elif key.startswith("adverse-childhood-experiences"):
        if "responses summed to create a total score ranging from 0 to 10" not in text:
            raise ValueError("ACE-Q scoring changed")
        add("total_raw", "Total adverse experiences", range(1, 11))
    elif key.startswith("the-professional-quality-of-life"):
        if (
            "Each of the three ProQOL subscales is scored by summing its 10 items"
            not in text
        ):
            raise ValueError("ProQOL scoring changed")
        for label, nums in [
            ("compassion_satisfaction", [3, 6, 12, 16, 18, 20, 22, 24, 27, 30]),
            ("burnout", [1, 4, 8, 10, 15, 17, 19, 21, 26, 29]),
            ("secondary_traumatic_stress", [2, 5, 7, 9, 11, 13, 14, 23, 25, 28]),
        ]:
            add(label, label.replace("_", " ").title(), nums)
    return rules
