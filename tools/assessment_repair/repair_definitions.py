"""Source-bound repairs for the audited 44 records. Produces a new version."""

# Helpers are invoked synchronously within each record; none escape the loop.
# ruff: noqa: B023
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

INPUT = "novopsych-all-186-assessments-refreshed-20261113.json"
OUTPUT = "novopsych-all-186-assessments-definition-repaired-20261114.json"


def read(p):
    return json.loads(p.read_text())


def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def nums(s):
    s = s.replace("–", "-").replace("—", "-").replace(" and ", ",").replace("&", ",")
    if not re.fullmatch(r"[\d,\s-]+", s):
        raise ValueError("Not an explicit item list: " + s)
    result = []
    for x in s.split(","):
        x = x.strip()
        if not x:
            continue
        if "-" in x:
            lo, hi = map(int, x.split("-"))
            assert 0 < lo <= hi <= 300
            result += list(range(lo, hi + 1))
        else:
            result.append(int(x))
    assert result and len(result) == len(set(result))
    return result


def build(project):
    input_sha = hashlib.sha256(
        (project / "assessment-exports" / INPUT).read_bytes()
    ).hexdigest()
    if input_sha != "ad61263ec3326923960a6dba7625983c5e2fc85deed33207e96c77818144f194":
        raise ValueError(
            "Input changed: re-audit the source-bound repair map before rebuilding."
        )
    previous = read(project / "assessment-exports" / INPUT)
    bundle = copy.deepcopy(previous)
    audited = [
        a
        for a in bundle["assessments"]
        if a["scoring"]["calculation_status"] == "source_guidance_only"
    ]
    assert len(audited) == 44
    report = []
    for n, a in enumerate(audited):
        qmap = {q["id"]: q for q in a["questionnaire"]["items"]}
        source_labels = {q["source_label"]: q["id"] for q in qmap.values()}
        sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
        selected = a["source_documents"][0] if a["source_documents"] else None
        evidence = {
            "questionnaire_url": selected["url"] if selected else None,
            "questionnaire_sha256": selected["sha256"] if selected else None,
            "page_url": a["provenance"]["source_url"],
            "page_sha256": a["source_refresh"]["page_sha256"],
            "method": "reviewed_saved_source_membership_and_arithmetic",
        }
        fixes = []
        remaining = [
            "Normative conversions and clinical publication require separate source-specific review."
        ]
        new = []
        alltext = "\n".join(c["text"] for c in a["context_sections"])
        # Retain exact archived scoring text omitted by fresh heading selection.
        if not a["scoring"]["source_guidance"]:
            for c in a["context_sections"]:
                if re.search(r"scor|interpret", c["title"], re.IGNORECASE):
                    a["scoring"]["source_guidance"].append(
                        {
                            "title": c["title"],
                            "text": c["text"],
                            "source_url": c["source_url"],
                            "origin": "retained_context_section",
                            "context_id": c["id"],
                        }
                    )
            if a["scoring"]["source_guidance"]:
                fixes.append(
                    "Restored scoring.source_guidance from preserved context sections."
                )

        def rule(label, numbers, method="sum", **extra):
            ids = [source_labels[str(x)] for x in numbers]
            assert len(ids) == len(set(ids)) and ids
            r = {
                "id": "source_draft_" + str(len(new) + 1),
                "label": label,
                "item_ids": ids,
                "method": method,
                "value_field": "printed_value",
                "multiplier": 1,
                "severity_bands": [],
                "status": "source_arithmetic_draft",
                "enabled": False,
                "source": evidence,
                "missing_item_policy": "withhold_if_required_answer_or_eligibility_is_unknown",
                **extra,
            }
            bounds = []
            for iid in ids:
                q = qmap[iid]
                if q["response_set_id"]:
                    overrides = r.get("option_value_overrides", {}).get(iid, {})
                    values = [
                        overrides.get(o["id"], o["printed_value"])
                        for o in sets[q["response_set_id"]]["options"]
                        if not re.fullmatch(
                            r"N/?A|NOT APPLICABLE", o.get("label") or "", re.IGNORECASE
                        )
                    ]
                else:
                    assert q["response_type"] in ["integer", "number"]
                    spec = q["input_spec"]["answer_schema"]
                    values = [spec["minimum"], spec["maximum"]]
                assert all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in values
                ), (a["assessment_id"], iid, values)
                tr = r.get("item_transforms", {}).get(iid, {})
                values = [v * tr.get("scale", 1) + tr.get("offset", 0) for v in values]
                if method == "count_threshold":
                    values = [0, 1]
                coefficient = r.get("item_coefficients", {}).get(iid, 1)
                values = [v * coefficient for v in values]
                bounds.append((min(values), max(values)))
            factor = r["multiplier"]
            div = len(ids) if method == "mean" else 1
            r["minimum"] = sum(b[0] for b in bounds) / div * factor
            r["maximum"] = sum(b[1] for b in bounds) / div * factor
            if (
                r.get("optional_item_ids")
                or r.get("ineligible_item_policy") == "exclude"
            ):
                r["minimum"] = min(b[0] for b in bounds) * factor
                r["maximum"] = max(b[1] for b in bounds) * factor
            if r.get("ineligible_item_policy") == "zero":
                r["minimum"] = min(0, r["minimum"])
            new.append(r)
            return r

        def groups_from_captions(method="sum"):
            added = []
            for cap in a["scoring"]["unparsed_pdf_expressions"]:
                m = re.match(r"(.+?)\s*\([Ii]tems?\s+([\d,\s–—-]+)\)", cap["text"])
                if m:
                    rr = rule(m[1].strip(), nums(m[2]), method)
                    rr["source"] = {**evidence, "pdf_caption": cap}
                    added.append(rr)
            return added

        def bands(r, values):
            r["severity_bands"] = [
                {"label": label, "minimum_inclusive": lo, "maximum_inclusive": hi}
                for label, lo, hi in values
            ]

        def gt(i, v=0):
            return {
                "item_id": "Q" + str(i),
                "operator": "gt",
                "value": v,
                "value_field": "printed_value",
            }

        def eq(i, oid):
            return {
                "item_id": "Q" + str(i),
                "operator": "equals",
                "value": oid,
                "value_field": "answer_id",
            }

        def yes_id(i):
            return next(
                o["id"]
                for o in sets[qmap["Q" + str(i)]["response_set_id"]]["options"]
                if o["label"] == "YES"
            )

        if n == 0:
            options = sets[qmap["Q74"]["response_set_id"]]["options"]
            positive = [o["id"] for o in options if o["label"] != "None of the above"]
            cond = {
                "item_id": "Q74",
                "operator": "contains_any",
                "value": positive,
                "value_field": "answer_id",
            }
            for i in range(75, 84):
                qmap["Q" + str(i)]["display_if"] = cond
            rule(
                "Harmful Substance Use raw spectrum score",
                range(75, 84),
                applies_if=cond,
            )
            remaining += [
                "MAPsy other spectra, clusters, facets and disorder-scale mappings have not been recovered as a verified executable key. Only Harmful Substance Use raw arithmetic is implemented; this is partial coverage."
            ]
            fixes.append(
                "Added checklist-dependent substance follow-up eligibility and a source-defined raw spectrum sum."
            )
        elif n == 1:
            use = {"any": [gt(i) for i in [1, 2, 3]]}
            for i in range(6, 11):
                qmap["Q" + str(i)]["display_if"] = use
            for i in range(11, 21):
                qmap["Q" + str(i)]["display_if"] = gt(4)
            rule("CRAFFT Part B Yes count", range(5, 11), ineligible_item_policy="zero")
            rule("HONC Yes count", range(11, 21), applies_if=gt(4))
            fixes.append(
                "Added substance-use and nicotine routing; gated scores distinguish unanswered dependencies from skipped questions."
            )
            remaining += [
                "Source screening classifications and clinical response protocols require review."
            ]
        elif n == 2:
            qmap["Q5"]["display_if"] = gt(4)
            for i in range(7, 14):
                qmap["Q" + str(i)]["display_if"] = gt(6)
            rule("Substance Use", [4, 5, 6], ineligible_item_policy="zero")
            rule("Risk Factors", [1, 2, 3, 8, 11, 15])
            rule("Protective Factors", [9, 10, 12, 13, 14, 16])
            remaining = [
                "No overall total or percentile norms are defined by this source.",
                "Source clinical review remains pending.",
            ]
            fixes.append(
                "Mapped source item numbers including 7a–7g; encoded explicit skip-as-zero scoring."
            )
        elif n == 3:
            for label, ns in [("PMQ-9", range(1, 10)), ("PHQ-9", range(10, 19))]:
                rr = rule(label + " raw score", ns)
                bands(rr, [("Subthreshold", 0, 9), ("Elevated", 10, 27)])
            a["scoring"]["paired_profile"] = {
                "status": "source_descriptive_draft",
                "rule_ids": [r["id"] for r in new],
                "thresholds": [10, 10],
                "cells": [
                    {"elevated": [False, False], "label": "Both below threshold"},
                    {"elevated": [True, False], "label": "PMQ-9 elevated only"},
                    {"elevated": [False, True], "label": "PHQ-9 elevated only"},
                    {"elevated": [True, True], "label": "Both elevated"},
                ],
                "source": evidence,
            }
        elif n in [4, 10, 18, 20, 22, 28]:
            gs = groups_from_captions()
            assert len(gs) == {4: 5, 10: 2, 18: 4, 20: 3, 22: 7, 28: 2}[n]
            rule(
                "Total raw score",
                [
                    int(qmap[i]["source_label"])
                    for i in sorted(
                        {i for r in gs for i in r["item_ids"]},
                        key=lambda x: int(qmap[x]["source_label"]),
                    )
                ],
            )
        elif n == 5:
            rule("Total raw score", range(1, 74))
            rr = rule(
                "Total percent endorsed",
                range(1, 74),
                "count_threshold",
                threshold=2,
                operator=">=",
                multiplier=100 / 73,
            )
            for label in ["Depression Subscale", "Hypomania/Biphasic Subscale"]:
                m = re.search(re.escape(label) + r"\s*\(items ([\d,\s]+)\)", alltext)
                assert m, label
                ns = nums(m[1])
                rule(
                    label + " percent endorsed",
                    ns,
                    "count_threshold",
                    threshold=2,
                    operator=">=",
                    multiplier=100 / len(ns),
                )
        elif n == 6:
            rule("Total raw score", range(1, 35))
            for label, ns in [
                ("Subjective wellbeing deficits", [4, 14, 17, 31]),
                ("Problems symptoms", [2, 5, 8, 11, 13, 15, 18, 20, 23, 27, 28, 30]),
                (
                    "Life functioning difficulties",
                    [1, 3, 7, 12, 10, 19, 21, 25, 26, 29, 32, 33],
                ),
                ("Risk harm", [9, 6, 16, 22, 24, 34]),
            ]:
                rule(label, ns)
            bands(
                new[0],
                [
                    ("Healthy", 0, 20),
                    ("Low", 21, 33),
                    ("Mild", 34, 50),
                    ("Moderate", 51, 67),
                    ("Moderate-to-Severe", 68, 84),
                    ("Severe", 85, 136),
                ],
            )
        elif n == 7:
            ns = [i for i in range(1, 38) if i not in [3, 4, 12, 22, 26, 33]]
            assert len(ns) == 31
            rr = rule("Total scored core items", ns)
            bands(
                rr,
                [
                    ("Typical Development", 0, 11),
                    ("Moderate Developmental Differences", 12, 14),
                    ("Significant Developmental Differences", 15, 31),
                ],
            )
        elif n == 8:
            gs = groups_from_captions()
            assert len(gs) == 5
            facets = {
                int(i): label.strip()
                for label, i in re.findall(
                    r"^([^:\n]+):[^\n]*?\(Item (\d+)\)", alltext, re.MULTILINE
                )
            }
            assert len(facets) == 30
            for i in range(1, 31):
                rule(facets[i] + " facet", [i])
        elif n == 9:
            gs = groups_from_captions()
            assert len(gs) == 30
            for start, label in zip(
                range(0, 30, 6),
                [
                    "Openness",
                    "Conscientiousness",
                    "Extraversion",
                    "Agreeableness",
                    "Neuroticism",
                ],
            ):
                rule(
                    label + " factor",
                    [
                        int(qmap[i]["source_label"])
                        for r in gs[start : start + 6]
                        for i in r["item_ids"]
                    ],
                )
        elif n == 11:
            assert len(groups_from_captions()) == 2
            remaining += [
                "Source conflict: web text gives subscale range 6–36, while six PDF items each have printed values 1–7 (range 6–42). Raw rules use PDF values; normative interpretation is withheld pending reconciliation."
            ]
        elif n == 12:
            qmap["Q6"]["display_if"] = eq(4, yes_id(4))
            qmap["Q7"]["display_if"] = {"any": [eq(i, yes_id(i)) for i in range(1, 5)]}
            a["scoring"]["protocol"] = {
                "kind": "asq_source_screen",
                "status": "source_protocol_draft",
                "core_item_ids": ["Q1", "Q2", "Q3", "Q4"],
                "acuity_item_id": "Q7",
                "numeric_total_applicable": False,
                "source": evidence,
                "clinical_actions_enabled": False,
            }
            remaining = [
                "No numeric total or percentile is defined for asQ.",
                "Clinical handling of screening states requires an approved clinical workflow; the evaluator returns source-derived states only.",
            ]
            fixes.append(
                "Added missing attempt-recency and any-Yes acuity conditions; encoded nonnumeric screening states."
            )
        elif n == 13:
            remaining = [
                "No authorized, variant-specific SDQ questionnaire is available in the selected source; its PDF is a version-selection guide. Questions, response sets, administration and executable scoring remain blocked."
            ]
        elif n == 14:
            q = qmap["Q1"]
            assert q["text"] == "- NOT WORKING FOR REASONS UNRELATED TO MY DIFFICULTIES"
            q["text"] = "Because of my difficulties, my ability to work is impaired."
            q["source"]["repair"] = {
                "date": "2026-11-14",
                "page": 1,
                "reason": "Restored stem above the response row; special response was incorrectly treated as the stem.",
            }
            rs = copy.deepcopy(sets[q["response_set_id"]])
            rs["id"] = "RS_WSAS_WORK_REPAIRED"
            assert all(o["id"] != "O10" for o in rs["options"])
            rs["options"].append(
                {
                    "id": "O10",
                    "label": "NOT WORKING FOR REASONS UNRELATED TO MY DIFFICULTIES",
                    "printed_value": None,
                    "score": 0,
                    "display_label": "NOT WORKING FOR REASONS UNRELATED TO MY DIFFICULTIES",
                    "display_label_origin": "printed_label",
                }
            )
            sets[rs["id"]] = rs
            a["questionnaire"]["response_sets"].append(rs)
            q["response_set_id"] = rs["id"]
            q["input_spec"]["answer_schema"]["enum"].append("O10")
            rule(
                "Total raw score",
                range(1, 6),
                option_value_overrides={"Q1": {"O10": 0}},
            )
            fixes.append(
                "Restored WSAS Q1 stem and its separate non-working choice O10; preserved all prior option IDs. Source guidance explicitly maps O10 to zero."
            )
        elif n in [15, 17, 21, 25, 30]:
            rule(
                "Total raw score", range(1, {15: 6, 17: 11, 21: 11, 25: 17, 30: 10}[n])
            )
            if n == 25:
                bands(
                    new[0],
                    [
                        ("Low Binge-Eating", 0, 17),
                        ("Mild to Moderate Binge-Eating", 18, 26),
                        ("Severe Binge-Eating", 27, 46),
                    ],
                )
            if n == 30:
                bands(
                    new[0],
                    [
                        ("None", 0, 0),
                        ("Low", 1, 4),
                        ("Moderate", 5, 7),
                        ("Problematic", 8, 27),
                    ],
                )
        elif n == 16:
            assert len(groups_from_captions()) == 5
            plus = [2, 3, 11, 12, 15, 16, 18, 20, 27, 4, 5, 6, 9]
            minus = [1, 14, 28]
            rule(
                "Avoidant Attachment",
                plus + minus,
                "weighted_sum",
                item_coefficients={source_labels[str(i)]: -1 for i in minus},
            )
            plus = [13, 17, 22, 23, 25, 7, 8, 10, 19, 21]
            minus = [24, 26, 29]
            rule(
                "Anxious Attachment",
                plus + minus,
                "weighted_sum",
                item_coefficients={source_labels[str(i)]: -1 for i in minus},
            )
        elif n == 19:
            rule("Total raw score", range(1, 22))
            for label, ns in [
                ("Nonacceptance", [1, 4, 5, 8, 12, 18, 20]),
                ("Modulate", [3, 9, 10, 13, 15, 17, 21]),
                ("Awareness", [2, 6, 11, 16, 19]),
                ("Clarity", [7, 14]),
            ]:
                rule(label, ns)
        elif n == 23:
            rule("Total positive experiences", range(1, 21))
            rule("Common protective factors", range(1, 11))
            rule(
                "Discriminating protective factors", [3, 4, 6, 7, 9, 10, 11, 13, 16, 19]
            )
        elif n == 24:
            for label, ns in [
                ("Total", list(range(1, 21))),
                ("Insistence on Sameness", [7, 9, 12, 13, 14, 15, 16, 17, 18]),
                ("Repetitive Sensory-Motor Behaviours", [2, 3, 4, 5, 6, 8, 10, 19]),
            ]:
                rule(label + " raw", ns)
                rule(label + " mean", ns, "mean")
        elif n == 26:
            assert len(groups_from_captions()) == 5
        elif n == 27:
            for cap in a["scoring"]["unparsed_pdf_expressions"]:
                m = re.match(
                    r"(.+?) symptom count \(items (\d+)[–-](\d+), count items rated 2 or 3",
                    cap["text"],
                )
                if m:
                    ns = list(range(int(m[2]), int(m[3]) + 1))
                    rule(
                        m[1] + " symptom count",
                        ns,
                        "count_threshold",
                        threshold=2,
                        operator=">=",
                    )
                    rule(
                        m[1] + " percent endorsed",
                        ns,
                        "count_threshold",
                        threshold=2,
                        operator=">=",
                        multiplier=100 / len(ns),
                    )
                    rule(m[1] + " mean", ns, "mean")
            assert len(new) == 57
            remaining += [
                "NA responses withhold the affected domain; source-specific NA denominator handling needs verification."
            ]
        elif n in [29, 34, 35, 36]:
            context_key = "attends_school" if n == 29 else "works_or_studies"
            optional = (
                list(range(25, 30))
                if n == 29
                else list(range(26, 33))
                if n == 34
                else list(range(25, 29))
            )
            for i in optional:
                qmap["Q" + str(i)]["display_if"] = {
                    "context_key": context_key,
                    "operator": "equals",
                    "value": True,
                }
            a["administration"]["respondent_context_requirements"] = [
                {
                    "key": context_key,
                    "type": "boolean",
                    "reason": "Explicit source eligibility for school/work questions.",
                }
            ]
            domains = [
                ("Cognition", range(1, 7)),
                ("Mobility", range(7, 12)),
                ("Self-care", range(12, 16)),
                ("Getting along", range(16, 21)),
            ]
            if n == 29:
                domains += [
                    ("Life Activities", range(21, 30)),
                    ("Participation", range(30, 35)),
                ]
            elif n == 34:
                domains += [
                    ("Household", range(21, 25)),
                    ("Work school", range(26, 30)),
                    ("Participation", range(33, 41)),
                ]
            else:
                domains += [
                    ("Life Activities", range(21, 29)),
                    ("Participation", range(29, 37)),
                ]
            total = []
            for label, rg in domains:
                ns = list(rg)
                total += ns
                rule(label + " mean", ns, "mean", ineligible_item_policy="exclude")
                if n == 29:
                    rule(
                        label + " percent maximum",
                        ns,
                        "mean",
                        multiplier=25,
                        ineligible_item_policy="exclude",
                    )
            rule("Overall mean", total, "mean", ineligible_item_policy="exclude")
            if n == 29:
                remaining += [
                    "Overall 0–100 conversion withheld: source calls it domain-weighted without specifying how domain weights are combined. Domain percent-of-maximum and overall item mean are provided."
                ]
            else:
                remaining += [
                    "WHO IRT conversion weights and missing-item/prorating algorithms are not implemented. These rules provide the explicitly described item means, not the complex IRT score."
                ]
            fixes.append(
                "Added explicit work/school eligibility context and excluded auxiliary questions from domain means."
            )
        elif n == 31:
            for label, ns in [
                ("Helpful Reactions", [1, 2, 3, 4, 6, 7, 9, 11, 13, 14]),
                ("Hindering Reactions", [5, 8, 10, 12]),
            ]:
                rule(label + " raw", ns)
                rule(label + " mean", ns, "mean")
        elif n == 32:
            rule(
                "Personal Wellbeing Index",
                range(2, 10),
                "mean",
                multiplier=10,
                optional_item_ids=["Q9"],
            )
            remaining += [
                "The source notes that published norms use seven core domains; comparisons when optional Q9 is included require that distinction."
            ]
        elif n == 33:
            # Recover the wrapped Social Relatedness list from full retained PDF text.
            text = " ".join(" ".join(p["text"].split()) for p in selected["pages"])
            m = re.search(
                r"Social Relatedness Problems score\s*\(Items\s*([\d,\s]+)\)",
                text,
                re.IGNORECASE,
            )
            if not m:
                raise ValueError("RAADS wrapped membership not found")
            rule("Social Relatedness Problems", nums(m[1]))
            gs = groups_from_captions()
            assert len(gs) == 3
            assert len({i for r in new for i in r["item_ids"]}) == 80
            for r in list(new):  # noqa: PERF101 -- rule() appends to new.
                rule(
                    r["label"] + " mean",
                    [qmap[i]["source_label"] for i in r["item_ids"]],
                    "mean",
                )
            rr = rule("Total raw score", range(1, 81))
            bands(
                rr,
                [
                    ("Overall not consistent with autism", 0, 64),
                    ("Some autistic traits", 65, 105),
                    ("Overall consistent with autism", 106, 139),
                    ("Pronounced", 140, 240),
                ],
            )
        elif n == 37:
            rule("Total Self-Compassion mean", range(1, 13), "mean")
            rule("Self Care mean", [2, 3, 5, 6, 7, 10], "mean")
            ns = [1, 4, 8, 9, 11, 12]
            rule(
                "Self Disparagement mean",
                ns,
                "mean",
                item_transforms={"Q" + str(i): {"scale": -1, "offset": 6} for i in ns},
            )
            fixes.append(
                "Represented per-rule score direction; Self Disparagement reverses the total-keyed printed values once."
            )
        elif n == 38:
            allowed = {}
            for i in [1, 2, 8]:
                options = sets[qmap["Q" + str(i)]["response_set_id"]]["options"]
                allowed["Q" + str(i)] = {
                    sex: [
                        o["id"]
                        for o in options
                        if o["label"] in ["NO", "YES (" + sex.upper() + ")"]
                    ]
                    for sex in ["female", "male"]
                }
            rule(
                "Total weighted score",
                range(1, 11),
                context_constraints=[
                    {
                        "context_key": "source_scoring_sex",
                        "allowed_values": ["female", "male"],
                        "allowed_options": allowed,
                    }
                ],
            )
            a["administration"]["respondent_context_requirements"] = [
                {
                    "key": "source_scoring_sex",
                    "enum": ["female", "male"],
                    "reason": "Source sex-specific weighting. Withhold if unsupported or unknown; never infer it.",
                }
            ]
            new[0]["maximum"] = 26
            new[0]["bounds_basis"] = (
                "Maximum over consistent female or male source columns; mixed-column maximum 29 is invalid."
            )
            bands(
                new[0],
                [("Low Risk", 0, 3), ("Moderate Risk", 4, 7), ("High Risk", 8, 26)],
            )
        elif n in [39, 40, 41]:
            gs = groups_from_captions()
            assert len(gs) == 6
            anxiety = [qmap[i]["source_label"] for r in gs[:5] for i in r["item_ids"]]
            rule("Total Anxiety", anxiety)
            rule("Total Internalising", range(1, 48))
        elif n == 42:
            p = [1, 3, 5, 7, 10, 12]
            neg = [2, 4, 6, 8, 9, 11]
            rule("Positive Feelings", p)
            rule("Negative Feelings", neg)
            rule(
                "Affect Balance",
                p + neg,
                "weighted_sum",
                item_coefficients={"Q" + str(i): -1 for i in neg},
            )
        elif n == 43:
            gs = groups_from_captions()
            assert len(gs) == 6
            ns = [qmap[i]["source_label"] for r in gs for i in r["item_ids"]]
            assert len(ns) == 38
            rule("Total anxiety", ns)
        else:
            raise ValueError("Unmapped audit record " + str(n))
        # Specify known source outputs still needing implementation, rather than claiming
        # that the presence of a raw rule makes the assessment scoring complete.
        extra_work = {
            3: "Separate PMQ-9 and PHQ-9 recall periods remain in source instructions; conversational administration requires preserving both.",
            5: "GBI percentage category boundaries are printed as integer ranges. Rounding between those ranges needs source clarification before encoding category assignment.",
            8: "Age/gender percentile lookups, factor/facet descriptors and AB5C pattern logic are not implemented.",
            9: "Age/gender percentile lookups and derived personality descriptors are not implemented.",
            11: "Attachment-pattern logic depends on reconciled subscale ranges and percentile conversion.",
            15: "Source-described change comparison and interpretation are retained as prose; not executable.",
            16: "Attachment pattern classification depends on missing percentile conversion and combination rules.",
            21: "Age-specific thresholds and item-4 review protocol are not implemented.",
            24: "Self-report and informant normative reference distributions must remain distinct.",
            28: "Normative conversion and longitudinal change interpretation are not implemented.",
            29: "Within-domain response variability interpretation is not automated.",
            31: "Within-subscale variability interpretation is not automated.",
            39: "Australian child age-band percentile conversion is not implemented; duplicate catalogue record retained with its own ID.",
            40: "Australian child age-band percentile conversion is not implemented; duplicate catalogue record retained with its own ID.",
            41: "Parent-report normative conversion must use its own respondent reference tables.",
            43: "Age/gender percentile conversion is not implemented; fillers and written responses are excluded from the anxiety total.",
        }
        if n in extra_work:
            remaining.append(extra_work[n])
        for r in new:
            r["source"] = {
                **r["source"],
                "context_section_ids": [
                    c["id"]
                    for c in a["context_sections"]
                    if re.search(r"scor|interpret", c["title"], re.IGNORECASE)
                ],
                "retained_evidence": "Full source text in context_sections and source_documents; draft implementation requires reviewer sign-off.",
            }
        a["scoring"]["rules"] += new
        a["scoring"]["rules_provenance"] = (
            evidence if new else a["scoring"]["rules_provenance"]
        )
        a["scoring"]["calculation_status"] = (
            "draft_rules_available"
            if new
            else "source_protocol_draft"
            if n == 12
            else "source_guidance_only"
        )
        a["scoring"]["status"] = (
            "source_arithmetic_draft"
            if new
            else "source_protocol_draft"
            if n == 12
            else a["scoring"]["status"]
        )
        a["scoring"]["remaining_work"] = remaining
        a["scoring"]["implementation_status"] = {
            "raw_calculation": "partial"
            if n == 0
            else "draft_implemented"
            if new
            else "not_applicable_protocol"
            if n == 12
            else "blocked",
            "interpretation": "partial_source_bands"
            if any(r["severity_bands"] for r in new)
            else "not_compiled",
            "normative_conversion": "not_implemented"
            if n not in [2, 12]
            else "not_applicable",
            "clinical_use": "not_approved",
        }
        a["scoring"]["coverage"] = (
            "Source-bound draft arithmetic/protocol. Norms, partial-answer exceptions, additional algorithms and clinical interpretation remain subject to the explicit remaining_work list."
        )
        a["scoring"]["runtime_module"] = "definition_runtime.py"
        if n in [2, 12]:
            a["scoring"]["percentile_status"] = (
                "not_applicable_source_defines_no_percentiles"
            )
        for q in qmap.values():
            opts = sets[q["response_set_id"]]["options"] if q["response_set_id"] else []
            used = [r for r in a["scoring"]["rules"] if q["id"] in r["item_ids"]]
            q["options"] = []
            for o in opts:
                base = o["printed_value"]
                if used:
                    for r in used:
                        override = (
                            r.get("option_value_overrides", {})
                            .get(q["id"], {})
                            .get(o["id"])
                        )
                        if override is not None:
                            base = override
                    o["score"] = base
                q["options"].append(
                    {
                        "id": o["id"],
                        "text": o["display_label"],
                        "source_label": o["label"],
                        "label_origin": o["display_label_origin"],
                        "printed_value": o["printed_value"],
                        "score": base if used else None,
                        "score_status": "draft_rule_value"
                        if used and base is not None
                        else "not_assigned",
                        "used_by_scoring_rules": [r["id"] for r in used],
                    }
                )
            if used:
                q["score_encoding"] = (
                    "Option score is a base source value. Apply explicit rule transforms, coefficients, thresholds, eligibility and multiplier; do not sum inline values directly."
                )
        a["provenance"]["definition_repair"] = {
            "date": "2026-11-14",
            "input_bundle": INPUT,
            "changes": fixes,
            "new_rule_count": len(new),
            "source": evidence,
        }
        a["review"]["definition_repair"] = {
            "status": "source_implementation_draft",
            "content_repairs": fixes,
            "scoring_rule_count": len(new),
            "remaining_work": remaining,
            "clinical_approval": False,
        }
        report.append(
            {
                "assessment_id": a["assessment_id"],
                "name": a["assessment"]["name"],
                "new_rules": len(new),
                "status": a["scoring"]["calculation_status"],
                "changes": fixes,
                "remaining_work": remaining,
            }
        )
    for a in bundle["assessments"]:
        a["schema_version"] = "2.3.0"
        a["definition_version"] = "1.0.0-draft.6"
        a["scoring"]["enabled"] = False
        a["review"]["ready_for_clinical_use"] = False
    bundle["schema_version"] = "2.3.0"
    bundle["bundle_version"] = "2026-11-14-definition-repair"
    bundle["summary"].update(
        assessments_with_draft_rules=sum(
            bool(a["scoring"]["rules"]) for a in bundle["assessments"]
        ),
        assessments_with_source_guidance_only=sum(
            a["scoring"]["calculation_status"] == "source_guidance_only"
            for a in bundle["assessments"]
        ),
        definition_repair_new_rules=sum(r["new_rules"] for r in report),
        source_protocol_drafts=sum(
            a["scoring"]["calculation_status"] == "source_protocol_draft"
            for a in bundle["assessments"]
        ),
    )
    bundle["import_contract"].update(
        schema_version="2.3.0",
        supported_scoring_methods=["sum", "mean", "count_threshold", "weighted_sum"],
        runtime="definition_runtime.py implements conditional eligibility, optional items, item transforms/coefficients and respondent context. Update consumers before use.",
        scoring_is_enabled=False,
    )
    bundle["summary"]["total_draft_scoring_rules"] = sum(
        len(a["scoring"]["rules"]) for a in bundle["assessments"]
    )
    bundle["summary"]["previously_guidance_only_records_with_new_rules"] = sum(
        bool(r["new_rules"]) for r in report
    )
    bundle["summary"]["fully_clinically_approved_assessments"] = 0
    bundle["usage_notes"].append(
        "14 November repairs add source-bound draft calculations and conditional logic. Remaining_work is authoritative for incomplete scoring coverage. No clinical publication is enabled."
    )
    return bundle, {
        "input_sha256": hashlib.sha256(
            (project / "assessment-exports" / INPUT).read_bytes()
        ).hexdigest(),
        "summary": bundle["summary"],
        "assessments": report,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    b, r = build(args.project)
    save(args.output, b)
    save(args.output.with_name("definition-repair-report-20261114.json"), r)
    print(json.dumps(b["summary"], indent=2))
