"""Draft local report contracts for every assessment, derived from retained definitions.

This module does not enable scoring, supply norms or infer clinical diagnoses.
"""

REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "status", "clinical_scoring_enabled", "metrics", "charts",
                 "comparisons", "percentiles", "interpretation", "source_evidence"],
    "properties": {
        "version": {"const": "1.0.0-draft.1"},
        "status": {"const": "draft_requires_clinical_review"},
        "clinical_scoring_enabled": {"const": False},
        "metrics": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["rule_id", "label", "minimum", "maximum", "favourable_direction"],
            "properties": {
                "rule_id": {"type": "string"}, "label": {"type": "string"},
                "minimum": {"type": "number"}, "maximum": {"type": "number"},
                "favourable_direction": {"enum": ["decrease", "increase"]},
            },
        }},
        "charts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "title", "kind", "series", "minimum", "maximum", "axis_unit"],
            "properties": {
                "id": {"type": "string"}, "title": {"type": "string"},
                "kind": {"enum": ["item_trend", "domain_trend"]},
                "series": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["id", "label", "value_field"],
                    "properties": {"id": {"type": "string"}, "label": {"type": "string"},
                                   "value_field": {"enum": ["printed_value", "rule_result"]}},
                }},
                "minimum": {"type": "number"}, "maximum": {"type": "number"},
                "axis_unit": {"type": "string"}, "note": {"type": "string"},
                "hide_series_when_all_observed_values_zero": {"type": "boolean"},
                "ineligible_value": {"enum": [0]},
            },
        }},
        "comparisons": {"type": "object"},
        "percentiles": {"type": "object"},
        "interpretation": {"type": "object"},
        "source_evidence": {"type": "object"},
    },
}


def _special_configuration(assessment):
    aid = assessment["assessment_id"]
    phq = aid.startswith("patient-health-questionnaire-depression-phq-9--")
    bam = aid.startswith("brief-addiction-monitor-bam--")
    if not (phq or bam):
        return None
    rules = assessment["scoring"]["rules"]
    config = {
        "version": "1.0.0-draft.1",
        "status": "draft_requires_clinical_review",
        "clinical_scoring_enabled": False,
        "metrics": [], "charts": [],
        "comparisons": {
            "reference_visits": ["previous", "baseline"],
            "delta_formula": "current_minus_reference",
            "deduplicate_same_reference_visit": True,
            "require_same_assessment_definition_language_and_scoring_version": True,
            "missing_result": "withhold_comparison",
            "single_visit": "show_current_scores_only",
            "date_source": "saved_session_completion_timestamp",
        },
        "percentiles": {
            "enabled": False,
            "reason": "verified_lookup_not_available" if phq else "not_applicable_to_instrument",
        },
        "interpretation": {
            "method": "deterministic_templates",
            "score_template": "{label}: {score} out of {maximum}.",
            "change_template": "{label} changed by {signed_delta} points since {reference_date}.",
            "missing_result_template": "Result unavailable: required responses or eligibility information are missing.",
            "clinical_significance": "not_implemented_requires_review",
            "diagnosis": "not_inferred",
            "severity_source": "rule.severity_bands" if phq else "not_applicable",
            "overall_total": "total_raw" if phq else None,
        },
        "source_evidence": {
            "questionnaire_sha256": next(d["sha256"] for d in assessment["source_documents"]
                                          if d["role"] == "questionnaire_source"),
            "guidance_titles": [g["title"] for g in assessment["scoring"]["source_guidance"]],
        },
    }
    for rule in rules:
        direction = "increase" if bam and rule["label"] == "Protective Factors" else "decrease"
        label = rule.get("label", "PHQ-9 total score")
        config["metrics"].append({
            "rule_id": rule["id"], "label": label,
            "minimum": rule["minimum"], "maximum": rule["maximum"],
            "favourable_direction": direction,
        })
        config["charts"].append({
            "id": rule["id"], "title": label, "kind": "domain_trend",
            "series": [{"id": rule["id"], "label": label, "value_field": "rule_result"}],
            "minimum": rule["minimum"], "maximum": rule["maximum"], "axis_unit": "score",
        })
    if phq:
        # The source contains prose about reliable change but no separately
        # verified implementation here. Do not turn it into a clinical claim.
        return config
    groups = [
        ("substance_use", "Alcohol and other drug use", "days", [
            ("Q4", "Alcohol use"), ("Q5", "Heavy alcohol use"), ("Q6", "Drug use / prescription medication misuse")]),
        ("specific_substances", "Specific drug use", "days", [
            ("Q7", "Marijuana"), ("Q8", "Sedatives / tranquilizers"), ("Q9", "Cocaine / crack"),
            ("Q10", "Other stimulants"), ("Q11", "Opiates"), ("Q12", "Inhalants"), ("Q13", "Other drugs")]),
        ("health", "Health and wellbeing", "score", [
            ("Q1", "Poor physical health"), ("Q2", "Disturbed sleep"), ("Q3", "Emotional distress"),
            ("Q21", "Conflict with family or friends")]),
        ("craving", "Craving and risk exposure", "score", [
            ("Q14", "Cravings and urges"), ("Q17", "Risky situations")]),
        ("recovery", "Recovery engagement and confidence", "score", [
            ("Q15", "Confidence in not using"), ("Q16", "Self-help attendance"), ("Q18", "Spiritual support")]),
        ("support", "Life stability and social support", "score", [
            ("Q19", "Work, study or volunteering"), ("Q20", "Adequate income"), ("Q22", "Supportive contact")]),
        ("satisfaction", "Satisfaction with recovery progress", "score", [("Q23", "Recovery satisfaction")]),
    ]
    item_charts = []
    for cid, title, unit, members in groups:
        chart = {"id": cid, "title": title, "kind": "item_trend", "minimum": 0, "maximum": 30,
                 "axis_unit": unit, "series": [
                     {"id": iid, "label": label, "value_field": "printed_value"} for iid, label in members]}
        if cid in ("substance_use", "specific_substances"):
            chart["ineligible_value"] = 0
            chart["note"] = "Days in the past 30 days. Only explicitly ineligible items use zero; unknown or unanswered items remain missing."
        else:
            chart["note"] = "Item values on the 0–30 scoring scale; this axis does not uniformly represent days."
        if cid == "specific_substances":
            chart["hide_series_when_all_observed_values_zero"] = True
            chart["note"] += " Specific-drug responses do not contribute to domain totals. Missing values are never treated as observed zeros."
        if cid == "satisfaction":
            chart["note"] += " Recovery satisfaction does not contribute to any domain total."
        item_charts.append(chart)
    config["charts"] = item_charts + config["charts"]
    config["interpretation"]["domain_change_note"] = "Review which individual items changed alongside the domain totals."
    return config


# These extensions are part of a versioned distribution contract. Existing
# PHQ-9/BAM layouts are retained; all other layouts use their own rule membership,
# scale bounds and source labels rather than borrowing another instrument's scale.
REPORT_SCHEMA["properties"]["version"] = {"const": "2.0.0-draft.1"}
REPORT_SCHEMA["properties"]["metrics"]["items"]["properties"].update({
    "favourable_direction": {"enum": ["decrease", "increase", None]},
    "direction_status": {"enum": ["source_guidance_draft", "not_compiled"]},
    "calculation_method": {"enum": ["sum", "mean", "count_threshold", "weighted_sum"]},
    "calculation_ref": {"type": "string"},
    "item_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    "severity_bands_ref": {"type": ["string", "null"]},
    "axis_unit": {"enum": ["score", "mean score", "item count"]},
})
REPORT_SCHEMA["properties"]["metrics"]["items"]["required"] += [
    "direction_status", "calculation_method", "calculation_ref",
    "item_ids", "severity_bands_ref", "axis_unit",
]
REPORT_SCHEMA["required"] += [
    "mode", "coverage", "sections", "response_groups", "item_history",
    "required_context", "protocol", "paired_profile",
]
REPORT_SCHEMA["properties"].update({
    "mode": {"enum": ["numeric_scores", "descriptive_responses", "screening_protocol", "unavailable"]},
    "coverage": {
        "type": "object", "additionalProperties": False,
        "required": ["questionnaire_available", "numeric_rule_count", "rules_included",
                     "raw_calculation_status", "interpretation_status", "full_source_coverage_verified",
                     "clinical_review_complete", "remaining_work", "review_issue_codes",
                     "reference_guidance_only", "missing_direction_rule_ids"],
        "properties": {
            "questionnaire_available": {"type": "boolean"},
            "numeric_rule_count": {"type": "integer", "minimum": 0},
            "rules_included": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            "raw_calculation_status": {"type": "string"},
            "interpretation_status": {"type": "string"},
            "full_source_coverage_verified": {"const": False},
            "clinical_review_complete": {"const": False},
            "remaining_work": {"type": "array", "items": {"type": "string"}},
            "review_issue_codes": {"type": "array", "items": {"type": "string"}},
            "reference_guidance_only": {"type": "boolean"},
            "missing_direction_rule_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        },
    },
    "sections": {"type": "array", "items": {"type": "object"}},
    "response_groups": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "label", "rule_id", "item_ids"],
        "properties": {
            "id": {"type": "string"}, "label": {"type": "string"},
            "rule_id": {"type": ["string", "null"]},
            "item_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        },
    }},
    "item_history": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["item_id", "question_ref", "source_label", "response_type", "presentation",
                     "value_field", "unit", "minimum", "maximum", "missing_value", "ineligible_value"],
        "properties": {
            "item_id": {"type": "string"}, "question_ref": {"type": "string"},
            "source_label": {"type": ["string", "null"]}, "response_type": {"type": "string"},
            "presentation": {"enum": ["numeric_history", "choice_history", "multiple_choice_history", "text_history"]},
            "value_field": {"const": "saved_answer"},
            "unit": {"type": ["string", "null"]},
            "minimum": {"type": ["number", "null"]}, "maximum": {"type": ["number", "null"]},
            "missing_value": {"const": "gap"}, "ineligible_value": {"const": "not_asked"},
        },
    }},
    "required_context": {"type": "array", "items": {"type": "object"}},
    "protocol": {"type": ["object", "null"]},
    "paired_profile": {"type": ["object", "null"]},
})


def _label(rule):
    # Missing labels occur in early hand-encoded rules with semantic IDs.
    return rule.get("label") or rule["id"].replace("_", " ").capitalize()


def _required_context(assessment):
    fields = {}

    def condition(expr):
        if not expr:
            return
        if "context_key" in expr:
            key = expr["context_key"]
            fields[key] = {
                "key": key,
                "type": "boolean" if isinstance(expr.get("value"), bool) else "source_defined",
                "required_when": "a dependent question or scoring rule is evaluated",
                "missing_policy": "eligibility_unknown",
            }
        for op in ("all", "any"):
            for child in expr.get(op, []):
                condition(child)

    for q in assessment["questionnaire"]["items"]:
        condition(q.get("display_if"))
    for rule in assessment["scoring"]["rules"]:
        condition(rule.get("applies_if"))
        for constraint in rule.get("context_constraints", []):
            key = constraint["context_key"]
            allowed = constraint["allowed_values"]
            if key in fields and fields[key].get("allowed_values") not in (None, allowed):
                raise ValueError("Conflicting respondent context constraints: " + key)
            fields[key] = {
                "key": key, "type": "enum", "allowed_values": allowed,
                "required_when": "a dependent question or scoring rule is evaluated",
                "missing_policy": "withhold_dependent_result",
            }
    return [fields[k] for k in sorted(fields)]


def _generic_configuration(a):
    rules = a["scoring"]["rules"]
    return {
        "version": "2.0.0-draft.1", "status": "draft_requires_clinical_review",
        "clinical_scoring_enabled": False, "metrics": [], "charts": [],
        "comparisons": {
            "reference_visits": ["previous", "baseline"], "delta_formula": "current_minus_reference",
            "deduplicate_same_reference_visit": True,
            "require_same_assessment_definition_language_and_scoring_version": True,
            "missing_result": "withhold_comparison",
            "single_visit": "show_current_scores_only" if rules else "show_current_responses_only",
            "date_source": "saved_session_completion_timestamp",
        },
        "percentiles": {
            "enabled": False,
            "reason": ("not_applicable_to_instrument" if a["scoring"].get("percentile_status", "").startswith("not_applicable")
                       else "verified_lookup_not_available"),
        },
        "interpretation": {
            "method": "deterministic_templates",
            "score_template": "{label}: {score} (scale {minimum} to {maximum}).",
            "change_template": "{label} changed by {signed_delta} points since {reference_date}.",
            "missing_result_template": "Result unavailable: required responses or eligibility information are missing.",
            "clinical_significance": "not_implemented_requires_review", "diagnosis": "not_inferred",
            "severity_source": "rule.severity_bands" if any(r.get("severity_bands") for r in rules) else "not_compiled",
            "overall_total": "total_raw" if any(r["id"] == "total_raw" for r in rules) else None,
        },
        "source_evidence": {
            "questionnaire_sha256": next((d.get("sha256") for d in a["source_documents"]
                                           if d["role"] == "questionnaire_source"), None),
            "guidance_titles": [g["title"] for g in a["scoring"]["source_guidance"]],
        },
    }


def report_configuration(a):
    """Return a complete presentation contract for each catalogue record.

    Every existing numeric rule gets a metric and chart. No raw values are
    converted to norms, and no favourable direction is guessed from a title.
    Records without numeric scoring receive an explicitly different report mode.
    """
    config = _special_configuration(a) or _generic_configuration(a)
    config["version"] = "2.0.0-draft.1"
    scoring = a["scoring"]
    rules = scoring["rules"]
    questions = a["questionnaire"]["items"]
    mode = ("unavailable" if not questions else "numeric_scores" if rules else
            "screening_protocol" if scoring.get("protocol") else "descriptive_responses")
    config["mode"] = mode
    previous_metrics = {m["rule_id"]: m for m in config["metrics"]}
    config["metrics"] = []
    names = [_label(r) for r in rules]
    for index, rule in enumerate(rules):
        rid = rule["id"]
        name = _label(rule)
        # Identical labels must still identify distinct source rules.
        if names.count(name) > 1:
            name += " (" + str(index + 1) + ")"
        prior = previous_metrics.get(rid, {})
        direction = prior.get("favourable_direction")
        unit = {"mean": "mean score", "count_threshold": "item count"}.get(rule["method"], "score")
        metric = {
            "rule_id": rid, "label": prior.get("label", name),
            "minimum": rule["minimum"], "maximum": rule["maximum"],
            "favourable_direction": direction,
            "direction_status": "source_guidance_draft" if direction else "not_compiled",
            "calculation_method": rule["method"], "calculation_ref": f"/scoring/rules/{index}",
            "item_ids": list(rule["item_ids"]),
            "severity_bands_ref": f"/scoring/rules/{index}/severity_bands" if rule.get("severity_bands") else None,
            "axis_unit": unit,
        }
        config["metrics"].append(metric)
        if not any(c["kind"] == "domain_trend" and c["series"][0]["id"] == rid for c in config["charts"]):
            config["charts"].append({
                "id": rid, "title": metric["label"], "kind": "domain_trend",
                "series": [{"id": rid, "label": metric["label"], "value_field": "rule_result"}],
                "minimum": rule["minimum"], "maximum": rule["maximum"], "axis_unit": unit,
            })
    config["comparisons"].update({
        "require_compatible_respondent_context": True,
        "unknown_direction": "report_numeric_change_without_improvement_or_deterioration_label",
        "score_colour_policy": "neutral_unless_direction_has_been_reviewed",
        "non_numeric_results": "show_state_or_response_history_without_numeric_delta",
    })
    config["interpretation"].update({
        "combine_metrics_into_new_total": False,
        "source_guidance_ref": "/scoring/source_guidance",
        "source_guidance_use": "reference_text_for_review_not_executable_rules",
        "descriptor_template": "{label}: {descriptor} (draft source descriptor).",
        "descriptive_template": "Responses are shown individually; no numeric total is defined.",
        "unavailable_template": "This assessment's questionnaire is unavailable in the supplied definitions.",
    })
    config["required_context"] = _required_context(a)
    config["coverage"] = {
        "questionnaire_available": bool(questions), "numeric_rule_count": len(rules),
        "rules_included": [r["id"] for r in rules],
        "raw_calculation_status": scoring.get("implementation_status", {}).get("raw_calculation",
                                  "draft_rules_available" if rules else mode),
        "interpretation_status": scoring.get("implementation_status", {}).get("interpretation", "requires_review"),
        "full_source_coverage_verified": False, "clinical_review_complete": False,
        "remaining_work": list(scoring.get("remaining_work", [])),
        "review_issue_codes": [i["code"] for i in a["review"]["issues"]],
        "reference_guidance_only": not questions,
        "missing_direction_rule_ids": [m["rule_id"] for m in config["metrics"] if m["favourable_direction"] is None],
    }
    config["sections"] = [
        {"id": "patient_details", "enabled": True, "source": "saved_patient_and_session"},
        {"id": "assessment_summary", "enabled": True, "source": "assessment_and_reporting_coverage"},
        {"id": "results", "enabled": bool(rules), "source": "reporting.metrics"},
        {"id": "score_charts", "enabled": bool(rules), "source": "reporting.charts",
         "single_visit": "range_bar", "repeated_visits": "line_chart"},
        {"id": "comparisons", "enabled": bool(questions), "source": "compatible_saved_sessions"},
        {"id": "protocol_result", "enabled": mode == "screening_protocol", "source": "scoring.protocol"},
        {"id": "paired_profile", "enabled": bool(scoring.get("paired_profile")), "source": "scoring.paired_profile"},
        {"id": "response_history", "enabled": bool(questions), "source": "reporting.item_history"},
        {"id": "responses", "enabled": bool(questions), "source": "reporting.response_groups"},
        {"id": "source_guidance", "enabled": bool(scoring["source_guidance"]), "source": "scoring.source_guidance",
         "role": "reference_material_requires_review"},
        {"id": "limitations", "enabled": True, "source": "reporting.coverage"},
    ]
    used = set()
    config["response_groups"] = []
    for metric in config["metrics"]:
        config["response_groups"].append({
            "id": metric["rule_id"], "label": metric["label"],
            "rule_id": metric["rule_id"], "item_ids": metric["item_ids"],
        })
        used.update(metric["item_ids"])
    remaining = [q["id"] for q in questions if q["id"] not in used]
    if remaining:
        config["response_groups"].append({
            "id": "recorded_responses", "label": "Additional recorded responses" if rules else "Recorded responses",
            "rule_id": None, "item_ids": remaining,
        })
    config["item_history"] = []
    for index, q in enumerate(questions):
        numeric = q["response_type"] in ("integer", "number")
        multiple = q["response_type"] == "multiple_choice" or q.get("selection_mode") == "multiple"
        kind = ("numeric_history" if numeric else "text_history" if q["response_type"] == "text"
                else "multiple_choice_history" if multiple else "choice_history")
        schema = q["input_spec"]["answer_schema"]
        unit = q["input_spec"].get("unit")
        config["item_history"].append({
            "item_id": q["id"], "question_ref": f"/questionnaire/items/{index}",
            "source_label": q.get("source_label"), "response_type": q["response_type"],
            "presentation": kind, "value_field": "saved_answer",
            "unit": unit if isinstance(unit, str) else None,
            "minimum": schema.get("minimum") if numeric else None,
            "maximum": schema.get("maximum") if numeric else None,
            "missing_value": "gap", "ineligible_value": "not_asked",
        })
    config["protocol"] = ({
        "definition_ref": "/scoring/protocol", "kind": scoring["protocol"]["kind"],
        "presentation": "categorical_state_history", "numeric_total_applicable": False,
        "clinical_actions_enabled": False,
        "state_labels": {
            "incomplete": "Incomplete screening responses",
            "negative_core_screen": "Negative core screen",
            "positive_core_screen_acuity_unanswered": "Positive core screen; acuity response missing",
            "positive_core_screen_current_ideation": "Positive core screen; current ideation reported",
            "positive_core_screen_no_current_ideation": "Positive core screen; no current ideation reported",
        },
    } if scoring.get("protocol") else None)
    config["paired_profile"] = ({
        "definition_ref": "/scoring/paired_profile",
        "rule_ids": list(scoring["paired_profile"]["rule_ids"]),
        "presentation": "paired_scores_and_source_profile",
        "status": scoring["paired_profile"]["status"],
        "missing_result": "withhold_profile",
    } if scoring.get("paired_profile") else None)
    return config
