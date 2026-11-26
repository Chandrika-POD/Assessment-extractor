"""Conservative, source-bound arithmetic extraction; no clinical approval implied."""

import math
import re


def parse_items(text):
    text = text.lower().replace("–", "-").replace("—", "-").replace(" to ", "-")
    text = re.sub(r"\band\b|&", ",", text)
    if not re.fullmatch(r"[\d,\s-]+", text):
        raise ValueError("Unsupported item expression")
    result = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            ends = part.split("-")
            if len(ends) != 2:
                raise ValueError("Invalid item range")
            low, high = map(int, ends)
            if not 0 < low <= high <= 300:
                raise ValueError("Invalid item range")
            result.extend(range(low, high + 1))
        else:
            result.append(int(part))
    if (
        not result
        or any(not 0 < n <= 300 for n in result)
        or len(result) != len(set(result))
    ):
        raise ValueError("Empty or repeated items")
    return result


def parse_caption(text):
    """Only explicit item sums/means; never assume a bare subscale is a sum."""
    # A complete parenthesis is required: wrapped/incomplete captions need review.
    matches = list(re.finditer(r"\(([^()]*)\)", text))
    for m in matches:
        expr = m[1].strip()
        low = expr.lower()
        nums = None
        method = None
        factor = 1.0
        if re.search(r"\b(schema|subscale|domain)\s+scores?\b", low):
            continue
        all_items = re.fullmatch(
            r"(sum|average|mean) of all (\d+) items(?:,\s*range\s+-?\d+\s*(?:to|[–-])\s*\d+)?",
            low,
        )
        explicit = re.fullmatch(
            r"(sum|average|mean) of (?:items|questions) ([\d,\s&–—-]+(?:and|to)?[\d,\s&–—-]*)",
            low,
        )
        trailing = re.fullmatch(r"(?:(odd|even) )?items ([\d,\s&–—-]+),\s*(.+)", low)
        if all_items:
            method = "sum" if all_items[1] == "sum" else "mean"
            nums = list(range(1, int(all_items[2]) + 1))
        elif explicit:
            method = "sum" if explicit[1] == "sum" else "mean"
            nums = parse_items(explicit[2])
        elif trailing:
            nums = parse_items(trailing[2])
            tail = trailing[3]
            if trailing[1]:
                nums = [n for n in nums if n % 2 == (1 if trailing[1] == "odd" else 0)]
            if re.fullmatch(
                r"(average|mean) of (?:the |these )?(?:\d+ )?(?:circled values|items|scores)(?:,\s*[\d–-]+)?(?:\s*×\s*10)?",
                tail,
            ):
                method = "mean"
                factor = 10.0 if "×" in tail else 1.0
            elif tail == "sum of circled values":
                method = "sum"
            else:
                divided = re.fullmatch(
                    r"sum of (?:items|(?:the \d+ )?item scores|circled values)(?:,)? (?:divided by |÷\s*)(\d+)",
                    tail,
                )
                if divided:
                    method = "sum"
                    factor = 1 / int(divided[1])
                else:
                    continue
        else:
            continue
        if not nums:
            continue
        return {
            "label": text[: m.start()].strip(),
            "method": method,
            "numbers": nums,
            "multiplier": factor,
        }
    return None


def compile_formulas(a, captions):
    items = {q["source_label"]: q for q in a["questionnaire"]["items"]}
    if len(items) != len(a["questionnaire"]["items"]):
        raise ValueError("Duplicate source item numbers")
    sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
    compiled = []
    pending = []
    seen = set()
    # This form's subscale directions differ from the printed overall-score direction.
    direction_sensitive = a["assessment_id"].startswith(
        "self-compassion-scale-short-form"
    )
    for caption in captions:
        try:
            spec = parse_caption(caption["text"])
        except ValueError:
            spec = None
        if not spec:
            pending.append(
                {
                    **caption,
                    "reason": "Caption was not automatically parsed; retain it for review and check rules for manually implemented equivalents.",
                }
            )
            continue
        key = (tuple(spec["numbers"]), spec["method"], spec["multiplier"])
        if key in seen:
            continue
        selected = [items.get(str(n)) for n in spec["numbers"]]
        reason = None
        if direction_sensitive:
            reason = "Subscale and total use different score directions; per-rule transformation review required."
        elif any(q is None for q in selected):
            reason = "Source item numbers do not resolve uniquely to extracted fields."
        elif any(q.get("display_if") for q in selected):
            reason = "Conditional item inclusion requires an explicit scoring policy."
        else:
            for q in selected:
                if q["response_type"] in ["integer", "number"]:
                    continue
                if (
                    q["response_type"] in ["text", "multiple_choice"]
                    or not q["response_set_id"]
                ):
                    reason = "Arithmetic refers to a non-scalar response."
                    break
                if any(
                    o["printed_value"] is None
                    for o in sets[q["response_set_id"]]["options"]
                ):
                    reason = "A source response has no numeric value."
                    break
        if reason:
            pending.append({**caption, "reason": reason})
            continue
        low = high = 0
        for q in selected:
            if q["response_set_id"]:
                values = [
                    o["printed_value"] for o in sets[q["response_set_id"]]["options"]
                ]
                low += min(values)
                if high is not None:
                    high += max(values)
            else:
                schema = q["input_spec"]["answer_schema"]
                low += schema.get("minimum", 0)
                if "maximum" not in schema:
                    high = None
                elif high is not None:
                    high += schema["maximum"]
        denom = len(selected) if spec["method"] == "mean" else 1
        rid = "pdf_" + str(len(compiled) + 1)
        compiled.append(
            {
                "id": rid,
                "label": spec["label"],
                "method": spec["method"],
                "item_ids": [q["id"] for q in selected],
                "multiplier": spec["multiplier"],
                "value_field": "printed_value",
                "minimum": low / denom * spec["multiplier"],
                "maximum": high / denom * spec["multiplier"]
                if high is not None
                else None,
                "severity_bands": [],
                "status": "source_arithmetic_draft",
                "enabled": False,
                "source": caption,
                "reverse_scoring_handling": "Use the printed source values once. Do not reverse again based only on item wording.",
                "missing_item_policy": "withhold_if_any_required_answer_is_missing",
                "coverage": "Arithmetic only; diagnostic algorithms, norms and source-specific missing-answer exceptions are not implied.",
            }
        )
        seen.add(key)
    return compiled, pending


def evaluate(definition, rule, answers):
    """Evaluate explicit draft arithmetic for testing, never clinical publication."""
    items = {q["id"]: q for q in definition["questionnaire"]["items"]}
    sets = {s["id"]: s for s in definition["questionnaire"]["response_sets"]}
    values = []
    for iid in rule["item_ids"]:
        if iid not in answers:
            return None
        q = items[iid]
        answer = answers[iid]
        if q["response_set_id"]:
            opt = next(
                (o for o in sets[q["response_set_id"]]["options"] if o["id"] == answer),
                None,
            )
            if opt is None:
                raise ValueError("Invalid answer option")
            if re.fullmatch(
                r"(?:NOT APPLICABLE|N/?A)", opt.get("label") or "", re.IGNORECASE
            ):
                return None
            value = opt[rule["value_field"]]
        else:
            from jsonschema import Draft202012Validator

            Draft202012Validator(q["input_spec"]["answer_schema"]).validate(answer)
            value = answer
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("A numeric scoring value is required")
        if rule["method"] == "count_threshold":
            threshold = rule.get("item_thresholds", {}).get(iid, rule["threshold"])
            if rule["operator"] == ">=":
                value = int(value >= threshold)
            elif rule["operator"] == "<=":
                value = int(value <= threshold)
            else:
                raise ValueError("Unsupported threshold operator")
        values.append(value)
    result = sum(values)
    if rule["method"] == "mean":
        result /= len(values)
    elif rule["method"] not in ["sum", "count_threshold"]:
        raise ValueError("Unsupported formula")
    return result * rule["multiplier"]
