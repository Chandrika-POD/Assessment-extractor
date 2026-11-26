"""Deterministic draft definition evaluator. Missing eligibility never becomes zero."""

import math
import re

from jsonschema import Draft202012Validator


def items(definition):
    return {q["id"]: q for q in definition["questionnaire"]["items"]}


def answer_value(definition, iid, answers, field="printed_value"):
    if iid not in answers:
        return None
    q = items(definition)[iid]
    answer = answers[iid]
    Draft202012Validator(q["input_spec"]["answer_schema"]).validate(answer)
    if q["response_set_id"]:
        opts = next(
            s["options"]
            for s in definition["questionnaire"]["response_sets"]
            if s["id"] == q["response_set_id"]
        )
        if isinstance(answer, list):
            return answer
        opt = next(o for o in opts if o["id"] == answer)
        if re.fullmatch(r"N/?A|NOT APPLICABLE", opt.get("label") or "", re.IGNORECASE):
            return None
        return opt[field]
    return answer


def condition(definition, expr, answers, context=None):
    """Three-valued boolean: None means a required dependency is unanswered."""
    context = context or {}
    if "any" in expr:
        results = [condition(definition, e, answers, context) for e in expr["any"]]
        return True if True in results else None if None in results else False
    if "all" in expr:
        results = [condition(definition, e, answers, context) for e in expr["all"]]
        return False if False in results else None if None in results else True
    if "context_key" in expr:
        value = context.get(expr["context_key"])
        if (
            isinstance(expr["value"], bool)
            and value is not None
            and type(value) is not bool
        ):
            raise ValueError(
                "Boolean respondent context required: " + expr["context_key"]
            )
    else:
        iid = expr["item_id"]
        if iid not in answers:
            return None
        answer_value(
            definition, iid, answers
        )  # Validate dependencies even for categorical equality.
        value = (
            answers[iid]
            if expr.get("value_field") == "answer_id" or expr["operator"] == "equals"
            else answer_value(definition, iid, answers)
        )
    if value is None:
        return None
    op = expr["operator"]
    expected = expr["value"]
    if op == "equals":
        return value == expected
    if op == "gt":
        return value > expected
    if op == "contains_any":
        return bool(set(value) & set(expected))
    raise ValueError("Unsupported condition operator: " + op)


def evaluate(definition, rule, answers, context=None):
    context = context or {}
    qs = items(definition)
    if rule.get("applies_if"):
        eligible = condition(definition, rule["applies_if"], answers, context)
        if eligible is not True:
            return None
    for constraint in rule.get("context_constraints", []):
        key = constraint["context_key"]
        if context.get(key) not in constraint["allowed_values"]:
            return None
        for iid, allowed_by_value in constraint["allowed_options"].items():
            if iid in answers and answers[iid] not in allowed_by_value[context[key]]:
                raise ValueError("Answer conflicts with respondent context: " + iid)
    values = []
    for iid in rule["item_ids"]:
        eligible = True
        if qs[iid].get("display_if"):
            eligible = condition(definition, qs[iid]["display_if"], answers, context)
        if eligible is None:
            return None
        if eligible is False:
            policy = rule.get("ineligible_item_policy", "withhold")
            if policy == "zero":
                values.append(0)
                continue
            if policy == "exclude":
                continue
            return None
        if iid not in answers:
            if iid in rule.get("optional_item_ids", []):
                continue
            return None
        answer = answers[iid]
        overrides = rule.get("option_value_overrides", {}).get(iid, {})
        if isinstance(answer, str) and answer in overrides:
            Draft202012Validator(qs[iid]["input_spec"]["answer_schema"]).validate(
                answer
            )
            value = overrides[answer]
        else:
            value = answer_value(
                definition, iid, answers, rule.get("value_field", "printed_value")
            )
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Non-finite/non-numeric scoring value")
        transform = rule.get("item_transforms", {}).get(iid, {})
        value = value * transform.get("scale", 1) + transform.get("offset", 0)
        if rule["method"] == "count_threshold":
            threshold = rule.get("item_thresholds", {}).get(iid, rule["threshold"])
            op = rule["operator"]
            if op == ">=":
                value = int(value >= threshold)
            elif op == "<=":
                value = int(value <= threshold)
            else:
                raise ValueError("Unsupported threshold operator")
        value *= rule.get("item_coefficients", {}).get(iid, 1)
        values.append(value)
    if not values:
        return None
    result = sum(values)
    if rule["method"] == "mean":
        result /= len(values)
    elif rule["method"] not in ["sum", "weighted_sum", "count_threshold"]:
        raise ValueError("Unsupported scoring method")
    return result * rule.get("multiplier", 1)


def interpret(rule, score):
    if score is None:
        return None
    for band in rule.get("severity_bands", []):
        if band["minimum_inclusive"] <= score <= band["maximum_inclusive"]:
            return band["label"]
    return None


def evaluate_protocol(definition, answers):
    """Return source-derived draft states only; no autonomous clinical action."""
    protocol = definition["scoring"].get("protocol")
    if not protocol:
        raise ValueError("No protocol defined")
    if protocol["kind"] != "asq_source_screen":
        raise ValueError("Unsupported protocol")
    core = [answer_value(definition, i, answers) for i in protocol["core_item_ids"]]
    if any(v is None for v in core):
        return {"status": "incomplete"}
    if not any(v == 1 for v in core):
        return {"status": "negative_core_screen"}
    acuity = answer_value(definition, protocol["acuity_item_id"], answers)
    if acuity is None:
        return {"status": "positive_core_screen_acuity_unanswered"}
    return {
        "status": "positive_core_screen_current_ideation"
        if acuity == 1
        else "positive_core_screen_no_current_ideation"
    }


def evaluate_profile(definition, answers, context=None):
    """Evaluate only the explicitly encoded paired raw-score profile."""
    profile = definition["scoring"].get("paired_profile")
    if not profile:
        raise ValueError("No paired profile defined")
    by_id = {r["id"]: r for r in definition["scoring"]["rules"]}
    scores = [
        evaluate(definition, by_id[i], answers, context) for i in profile["rule_ids"]
    ]
    if any(v is None for v in scores):
        return None
    elevated = [v >= threshold for v, threshold in zip(scores, profile["thresholds"])]
    return next(
        cell["label"] for cell in profile["cells"] if cell["elevated"] == elevated
    )
