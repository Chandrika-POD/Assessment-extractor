"""Source-checked response controls for fields that are not ordinary rating rows.

The hash allowlist binds these rules to the PDF editions inspected on 2026-11-13.
This defines how to record answers, not how to calculate clinical scores.
"""

import copy
import json
from pathlib import Path

import pymupdf as fitz

HASHES = json.loads(Path(__file__).with_name("reviewed-pdf-hashes.json").read_text())


def input_spec(kind, *, unit=None, maximum=None, na=False):
    if kind == "text":
        schema = {"type": "string", "minLength": 1}
    else:
        schema = {"type": kind, "minimum": 0}
        if maximum is not None:
            schema["maximum"] = maximum
        if na:
            schema = {"oneOf": [schema, {"const": "NA"}]}
    return {
        "kind": kind,
        "answer_schema": schema,
        "unit": unit,
        "allow_not_applicable": na,
        "not_applicable_value": "NA" if na else None,
        "missing_answer_representation": "Omit the answer and record skipped/unanswered separately; do not substitute 0 or NA.",
        "constraints_basis": "Integer counts and nonnegative quantities; upper bounds only from an explicit day window or printed range."
        if kind != "text"
        else "The PDF provides a written-response field. No fixed answer options or invented character limit.",
        "source_review": "PDF text and field layout; targeted visual checks for ambiguous controls.",
    }


def type_field(q, kind, *, unit=None, maximum=None, na=False):
    q["response_type"] = kind
    q["selection_mode"] = None
    q["response_set_id"] = None
    q["input_spec"] = input_spec(kind, unit=unit, maximum=maximum, na=na)
    q["review_status"] = "response_format_source_checked"
    q["review_flags"] = [
        f
        for f in q["review_flags"]
        if f != "response_type_and_input_constraints_need_review"
    ]
    q["source"]["response_format_reviewed_on"] = "2026-11-13"


def choice_schema(options, multiple=False):
    enum = [o["id"] for o in options]
    if multiple:
        return {
            "type": "array",
            "items": {"type": "string", "enum": enum},
            "uniqueItems": True,
            "minItems": 1,
        }
    return {"type": "string", "enum": enum}


def condition_on_yes(a, item_id, previous_id):
    items = {q["id"]: q for q in a["questionnaire"]["items"]}
    sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
    previous = items[previous_id]
    options = sets[previous["response_set_id"]]["options"]
    yes = next(o for o in options if (o["label"] or "").strip().upper() == "YES")
    items[item_id]["display_if"] = {
        "item_id": previous_id,
        "operator": "equals",
        "value": yes["id"],
        "basis": "Printed conditional question wording.",
    }


def apply(a):
    key = a["assessment_id"]
    items = a["questionnaire"]["items"]
    affected = [q for q in items if q["response_type"] == "unverified"]
    if not affected:
        return 0
    selected = next(
        asset for asset in a["assets"] if asset["role"] == "selected_questionnaire"
    )
    if HASHES.get(key) != selected["sha256"]:
        raise ValueError(
            "Response overrides require review for this PDF edition: " + key
        )
    for q in affected:
        n = q["source_label"]
        if key.startswith("multilevel-assessment-of-psychopathology-mapsy--"):
            assert n == "74"
            labels = [
                "Alcohol",
                "Sedatives or hypnotics (e.g., benzodiazepines or “benzos” such as alprazolam/Xanax and diazepam/Valium, or Z-drugs or “sleeping pills”)",
                "Cannabis (i.e., weed, marijuana)",
                "Stimulants (e.g., methamphetamine, cocaine)",
                "Hallucinogens or psychedelics (e.g., LSD, psilocybin or “magic mushrooms”, ketamine, PCP)",
                "Opioids (e.g., heroin)",
                "Inhalants (e.g., glue, paint thinners, spray paints, nitrous oxide or “nos”)",
                "None of the above",
            ]
            opts = [
                {
                    "id": "O" + str(i),
                    "label": label,
                    "printed_value": None,
                    "score": None,
                }
                for i, label in enumerate(labels, 1)
            ]
            rid = "RS_MAPSY_SUBSTANCES"
            a["questionnaire"]["response_sets"].append(
                {
                    "id": rid,
                    "options": opts,
                    "mapping_status": "source_checked_categorical_options_unscored",
                }
            )
            q.update(
                text="In the past year, which of the following substances have you used?",
                response_type="multiple_choice",
                selection_mode="multiple",
                response_set_id=rid,
                review_status="response_format_source_checked",
                review_flags=[],
            )
            schema = choice_schema(opts, True)
            schema["oneOf"] = [
                {"maxItems": 1, "contains": {"const": "O8"}},
                {"not": {"contains": {"const": "O8"}}},
            ]
            q["input_spec"] = {
                "kind": "multiple_choice",
                "answer_schema": schema,
                "exclusive_option_ids": ["O8"],
                "source_review": "Eight printed checkboxes; None of the above is exclusive.",
            }
        elif key.startswith("brief-addiction-monitor-bam--"):
            type_field(q, "integer", unit="days", maximum=30)
            if n.startswith("7"):
                q["context_text"] = (
                    "In the past 30 days, how many days did you use the following substances?"
                )
                q["context_origin"] = (
                    "Administration paraphrase of the form time window and the item 7 drug-use fields; original item text is unchanged."
                )
            if n == "2":
                q["input_spec"]["unit"] = "nights"
                q["review_flags"].append(
                    "Source question asks nights; the form prints days beside the box. Both are retained."
                )
        elif key.startswith("crafft-substance-use-assessment-crafft-2-1-n--"):
            type_field(q, "integer", unit="days")
            q["context_text"] = "Number of days in the past 12 months."
            q["context_source"] = {
                "url": a["provenance"]["source_url"],
                "section": "CRAFFT 2.1+N Structure / Part A",
            }
            q["input_spec"]["range_note"] = (
                "No numeric upper limit is printed in the PDF; the webpage supplies the 12-month reference period."
            )
        elif key.startswith("eating-disorder-15ed-15--"):
            type_field(
                q,
                "integer",
                unit="times" if int(n) <= 12 else "days",
                maximum=None if int(n) <= 12 else 7,
                na=int(n) in (11, 12, 13),
            )
        elif key.startswith("kessler-psychological-distress-scale-plus-k10--"):
            type_field(
                q,
                "integer",
                unit="times" if n == "13" else "days",
                maximum=None if n == "13" else 30,
            )
        elif "whodas" in key:
            type_field(q, "integer", unit="days", maximum=30)
            q["context_text"] = "In the past 30 days."
        elif key.startswith(
            (
                "pardi-ar-q-arfid-questionnaire--",
                "pica-arfid-and-rumination-disorder-interview-arfid-questionnaire-informant-report-par--",
            )
        ):
            if n == "7":
                type_field(q, "number")
                q["review_flags"].append(
                    "The weight-loss field does not state a unit; do not assume kilograms or pounds."
                )
            else:
                assert n in ("13", "15", "17")
                type_field(q, "text")
                q["review_flags"].append(
                    "The PDF prints days beside this field but asks for product name and daily amount. Retain the written answer; do not interpret it as a day count."
                )
        elif key.startswith(
            (
                "gender-preoccupation-stability-questionnaire-2--",
                "composite-caregiving-questionnaire-ccq--",
                "client-satisfaction-survey-css--",
                "obsessional-compulsive-inventory-ocd-child-self-report--",
                "obsessional-compulsive-inventory-revised-parent-choci-r-p--",
                "ask-suicide-screening-questionnaire-asq--",
                "session-reactions-scale-3-brief-srs-3-b--",
                "your-experience-of-service-yes--",
                "vanderbilt-adhd-diagnostic-teacher-rating-scale-vadtrs--",
                "preschool-anxiety-scale-pas--",
                "spence-childrens-anxiety-scale-child-scas-child--",
                "spence-childrens-anxiety-scale-parent-scas-parent--",
            )
        ):
            type_field(q, "text")
            if key.startswith("composite-caregiving") and n == "2":
                q["input_spec"]["format_note"] = (
                    "Age is a written field in the PDF; retain a response such as years and months without inventing an age unit or upper bound."
                )
        else:
            raise ValueError(
                "No source-checked response mapping for " + key + " / " + n
            )
    if key.startswith("ask-suicide-screening-questionnaire-asq--"):
        condition_on_yes(a, "Q5", "Q4")
        condition_on_yes(a, "Q8", "Q7")
    if key.startswith("preschool-anxiety-scale-pas--"):
        condition_on_yes(a, "Q30", "Q29")
    if key.startswith("spence-childrens-anxiety-scale-child-scas-child--"):
        condition_on_yes(a, "Q46", "Q45")
    if key.startswith(
        (
            "pardi-ar-q-arfid-questionnaire--",
            "pica-arfid-and-rumination-disorder-interview-arfid-questionnaire-informant-report-par--",
        )
    ):
        for number in (7, 13, 15, 17):
            condition_on_yes(a, "Q" + str(number), "Q" + str(number - 1))
    return len(affected)


def pardi_additional_fields(a, pdf):
    """The four unnumbered measurement lines follow the printed unit selectors."""
    if not a["assessment_id"].startswith(
        (
            "pardi-ar-q-arfid-questionnaire--",
            "pica-arfid-and-rumination-disorder-interview-arfid-questionnaire-informant-report-par--",
        )
    ):
        return 0
    page = pdf[0]
    lines = [
        ("".join(s["text"] for s in line["spans"]), line["bbox"])
        for block in page.get_text("dict", flags=fitz.TEXT_INHIBIT_SPACES)["blocks"]
        for line in block.get("lines", [])
    ]
    sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
    additions = []
    for parent in a["questionnaire"]["items"]:
        if parent["id"] not in ("Q1", "Q2"):
            continue
        parent["response_type"] = "single_choice"
        parent["selection_mode"] = "single"
        controls = sets[parent["response_set_id"]]["options"]
        labels = (
            [
                ("height_cm", "Current height in centimetres", "centimetres"),
                ("height_feet", "Current height in feet", "feet"),
                ("height_inches", "Current height in inches", "inches"),
            ]
            if parent["id"] == "Q1"
            else [("weight", "Current weight", None)]
        )
        for suffix, label, unit in labels:
            if "informant-report-par--" in a["assessment_id"]:
                label = label.replace("Current", "Child's")
            field = copy.deepcopy(parent)
            field["id"] = parent["id"] + "_" + suffix
            field["source_label"] = parent["source_label"] + "." + suffix
            field["text"] = label
            matches = [bbox for text, bbox in lines if text.strip() == label]
            if not matches:
                raise ValueError(
                    "Unnumbered field label not found in selected PDF: " + label
                )
            # 'Current weight' also appears in the selector; the final occurrence is the input label.
            field["source"]["bbox"] = list(matches[-1])
            field["source"]["method"] = "unnumbered_pdf_field_visually_checked"
            field["source"]["page"] = 1
            field["source"]["parent_item_id"] = parent["id"]
            type_field(field, "number", unit=unit)
            if parent["id"] == "Q1":
                target = "CENTIMETRES" if suffix == "height_cm" else "FEET AND INCHES"
                option = next(
                    o
                    for o in controls
                    if (o["label"] or "").upper().replace(" ", "")
                    == target.replace(" ", "")
                )
                field["display_if"] = {
                    "item_id": "Q1",
                    "operator": "equals",
                    "value": option["id"],
                    "basis": "Measurement field follows the printed preferred-unit selector.",
                }
            else:
                field["input_spec"]["unit_from_item"] = {
                    "item_id": "Q2",
                    "option_units": {o["id"]: o["label"] for o in controls},
                }
            additions.append((parent["id"], field))
    ordered = []
    for q in a["questionnaire"]["items"]:
        ordered.append(q)
        ordered.extend(field for parent, field in additions if parent == q["id"])
    for i, q in enumerate(ordered, 1):
        q["order"] = i
    a["questionnaire"]["items"] = ordered
    return len(additions)
