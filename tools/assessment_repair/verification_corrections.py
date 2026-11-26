"""Narrow, reproducible corrections; retained original evidence is never edited."""

YES_ID = "your-experience-of-service-yes--29de2c8cbc9b"
YES_OLD_MINIMUMS = {"pdf_2": .75, "pdf_3": .5, "pdf_4": 1 / 3,
                    "pdf_5": 5 / 6, "pdf_6": 1 / 3, "pdf_7": 13 / 22}


def apply_corrections(a):
    if a["assessment_id"] != YES_ID:
        return
    changes = []
    for r in a["scoring"]["rules"]:
        if r["id"] in YES_OLD_MINIMUMS:
            old = YES_OLD_MINIMUMS[r["id"]]
            if r["minimum"] != old:
                raise ValueError("YES source changed; re-review correction: " + r["id"])
            r["minimum"] = 1.0
            changes.append({"rule_id": r["id"], "field": "minimum", "before": old, "after": 1.0})
    a["definition_version"] = "1.0.0-draft.7"
    a["scoring"]["remaining_work"] = list(a["scoring"].get("remaining_work", [])) + [
        "YES partial-response and NA denominator rules are not implemented. Current conservative evaluation withholds affected means; it must not treat NA as zero.",
        "Current YES rules express means on 1–5. The official standardized experience/outcome percentages and their reporting contract are not implemented.",
    ]
    a["provenance"]["scoring_verification_corrections"] = {
        "checked_on": "2026-11-18", "source_definition_version": "1.0.0-draft.6",
        "changes": changes,
        "reason": "NA zero codes are unavailable responses, not attainable numeric minima for the current mean rules. Valid answered responses range from 1 to 5.",
        "source_reference": "https://www.amhocn.org/__data/assets/pdf_file/0008/700397/yes_guidance_for_orgs_ver_1.2_170703.pdf",
        "source_sections": ["7.2.1", "7.2.3", "7.3"],
        "clinical_approval": False,
    }
