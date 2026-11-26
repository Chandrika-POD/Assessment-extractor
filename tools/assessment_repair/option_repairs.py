"""Recover option labels from PDF cells, explicit instructions and primary evidence."""

import copy
import re

IRIS_SOURCE = "https://www.qscriptlearn.health.qld.gov.au/file/153/download"


def option_repairs(a, cell_changes):
    sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
    items = {q["id"]: q for q in a["questionnaire"]["items"]}
    changes = []
    for r in cell_changes:
        if r["assessment_id"] != a["assessment_id"]:
            continue
        if items[r["item_id"]]["source"]["sha256"] != r["sha256"]:
            raise ValueError("Source mismatch for cell label")
        option = next(
            o
            for o in sets[r["response_set_id"]]["options"]
            if o["id"] == r["option_id"]
        )
        if option["label"] not in [r["old_label"], r["label"]]:
            raise ValueError("Cell repair input differs")
        option["label"] = r["label"]
        option["display_label"] = r["label"] or str(option["printed_value"])
        changes.append(
            {
                "kind": "pdf_cell_reading_order",
                "item_id": r["item_id"],
                "option_id": r["option_id"],
                "previous_label": r["old_label"],
                "label": r["label"],
                "source": {"sha256": r["sha256"], "page": r["page"], "bbox": r["bbox"]},
            }
        )
    if a["assessment_id"].startswith("why-have-sex"):
        instruction = a["administration"]["instructions"]
        matches = re.findall(r"([1-5]) = ([^;]+?)(?:;|\.$)", instruction)
        mapping = {int(n): text for n, text in matches}
        if len(mapping) != 5:
            raise ValueError("YSEX source scale no longer matches")
        for q in items.values():
            for o in sets[q["response_set_id"]]["options"]:
                o["label"] = mapping[o["printed_value"]]
                o["display_label"] = o["label"]
                o["display_label_origin"] = "printed_label"
            q["source"]["option_label_origin"] = (
                "Explicit shared response scale in PDF instructions."
            )
            changes.append(
                {
                    "kind": "instruction_response_scale",
                    "item_id": q["id"],
                    "restored_labels": 5,
                    "source": q["source"],
                }
            )
    if "pardi-ar-q" in a["assessment_id"] or a["assessment_id"].startswith(
        "pica-arfid"
    ):
        for q in items.values():
            if not q["source_label"].isdigit() or int(q["source_label"]) < 19:
                continue
            anchors = {
                int(n): text.strip()
                for n, text in re.findall(r"(\d+)\s*\(=\s*([^)]*)\)", q["text"])
            }
            if set(anchors) != {0, 6}:
                raise ValueError("PARDI endpoint source changed: " + q["id"])
            old = sets[q["response_set_id"]]
            new = copy.deepcopy(old)
            new["id"] = old["id"] + "_anchors_" + q["id"]
            for o in new["options"]:
                if o["printed_value"] in anchors:
                    o["label"] = anchors[o["printed_value"]]
                    o["display_label"] = o["label"]
                    o["display_label_origin"] = "printed_label"
            a["questionnaire"]["response_sets"].append(new)
            sets[new["id"]] = new
            q["response_set_id"] = new["id"]
            q["source"]["option_label_origin"] = (
                "Endpoint definitions printed in this question."
            )
            changes.append(
                {
                    "kind": "question_endpoint_labels",
                    "item_id": q["id"],
                    "restored_labels": 2,
                    "source": q["source"],
                }
            )
    if a["assessment_id"].startswith("indigenous-risk"):
        replacements = {
            "Q3": {
                1: "NEVER/HARDLY EVER",
                3: "ONCE A FORTNIGHT",
                5: "MORE THAN ONCE A WEEK",
                6: "MOST DAYS/EVERY DAY",
            },
            "Q5": {4: "I COULDN’T STOP OR CUT DOWN"},
        }
        for iid, mapping in replacements.items():
            q = items[iid]
            for o in sets[q["response_set_id"]]["options"]:
                if o["printed_value"] in mapping:
                    old = o["label"]
                    o["label"] = mapping[o["printed_value"]]
                    o["display_label"] = o["label"]
                    changes.append(
                        {
                            "kind": "clipped_source_label_restored",
                            "item_id": iid,
                            "option_id": o["id"],
                            "previous_label": old,
                            "label": o["label"],
                            "source": {"url": IRIS_SOURCE, "page": 1},
                        }
                    )
            q["source"]["supplemental_option_source"] = {
                "url": IRIS_SOURCE,
                "page": 1,
                "reason": "NovoPsych PDF truncates these response labels.",
            }
    if a["assessment_id"].startswith("life-events-checklist"):
        if "one or more" not in a["administration"]["instructions"]:
            raise ValueError("LEC source does not establish multiple selections")
        for q in items.values():
            q["selection_mode"] = "multiple"
            q["response_type"] = "multiple_choice"
            q["input_spec"] = {
                "kind": "multiple_choice",
                "selection_mode": "multiple",
                "selection_mode_review_required": False,
                "answer_schema": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            o["id"] for o in sets[q["response_set_id"]]["options"]
                        ],
                    },
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "source_review": "PDF instructions explicitly allow one or more exposure boxes per event.",
            }
            changes.append({"kind": "multiple_selection_restored", "item_id": q["id"]})
    for q in items.values():
        if q["response_set_id"] and all(
            o["label"] is not None for o in sets[q["response_set_id"]]["options"]
        ):
            q["review_flags"] = [
                v
                for v in q["review_flags"]
                if v != "some_printed_rating_values_have_no_verbal_anchor"
            ]
    return changes
