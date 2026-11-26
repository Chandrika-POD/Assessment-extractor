"""Recover verified question stems and first scale options from archived PDFs.

The checked rules are tied to exact PDF hashes and coordinates. No network calls,
scoring inference or replacement of existing option IDs occurs.
"""

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf as fitz

INPUT_NAME = "novopsych-all-186-assessments-final-20261113.json"
OUTPUT_NAME = "novopsych-all-186-assessments-questions-recovered-20261113.json"
HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def source_text(pdf, page, bbox):
    return " ".join(
        pdf[page - 1]
        .get_text("text", clip=fitz.Rect(bbox), flags=fitz.TEXT_INHIBIT_SPACES)
        .split()
    )


def checked_pdf(a, expected_sha):
    src = next(s for s in a["source_documents"] if s["sha256"] == expected_sha)
    path = Path(src["archive_path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise ValueError("Source PDF changed: " + str(path))
    return fitz.open(path)


def recover(bundle, rules):
    result = copy.deepcopy(bundle)
    rows = {a["assessment_id"]: a for a in result["assessments"]}
    changes = []
    for rule in rules["questions"]:
        a = rows[rule["assessment_id"]]
        q = next(q for q in a["questionnaire"]["items"] if q["id"] == rule["item_id"])
        if (
            q["text"] != rule["old_text"]
            or q["source"]["sha256"] != rule["source_sha256"]
        ):
            raise ValueError("Question/source differs from reviewed input: " + q["id"])
        with checked_pdf(a, rule["source_sha256"]) as pdf:
            recovered = source_text(pdf, rule["stem_page"], rule["stem_bbox"])
            if recovered != rule["text"]:
                raise ValueError("Reviewed question text no longer matches PDF")
            page = pdf[q["source"]["page"] - 1]
            box = fitz.Rect(q["source"]["bbox"])
            separators = [
                d["rect"]
                for d in page.get_drawings()
                if 0 < d["rect"].width < 2
                and d["rect"].height > 8
                and abs(d["rect"].y0 - box.y0) < 1
                and abs(d["rect"].y1 - box.y1) < 1
            ]
            first_box = [52, box.y0, min(r.x0 for r in separators), box.y1]
            printed = source_text(pdf, q["source"]["page"], first_box)
            if re.sub(r"\s", "", printed) != re.sub(r"\s", "", rule["old_text"]):
                raise ValueError(
                    "First answer cell does not match reviewed label: " + printed
                )
        match = re.fullmatch(r"(\d+) ([A-Z ]+)", rule["old_text"])
        if not match:
            raise ValueError("Unsupported first answer cell")
        original_set = next(
            s
            for s in a["questionnaire"]["response_sets"]
            if s["id"] == q["response_set_id"]
        )
        restored = copy.deepcopy(original_set)
        restored["id"] = original_set["id"] + "_restored_first"
        new_id = "O" + str(max(int(o["id"][1:]) for o in restored["options"]) + 1)
        option = {
            "id": new_id,
            "label": match[2],
            "printed_value": int(match[1]),
            "score": None,
            "display_label": match[2],
            "display_label_origin": "printed_label",
        }
        if any(
            o["printed_value"] == option["printed_value"] for o in restored["options"]
        ):
            raise ValueError("Unexpected duplicate restored response value")
        restored["options"].insert(0, option)
        existing = next(
            (
                s
                for s in a["questionnaire"]["response_sets"]
                if s["id"] == restored["id"]
            ),
            None,
        )
        if existing is not None and existing != restored:
            raise ValueError("Response set collision")
        if existing is None:
            a["questionnaire"]["response_sets"].append(restored)
        old_set_id = q["response_set_id"]
        q["text"] = recovered
        q["response_set_id"] = restored["id"]
        q["response_type"] = "single_choice"
        q["selection_mode"] = "single"
        q["input_spec"] = {
            "kind": "single_choice",
            "answer_schema": {
                "type": "string",
                "enum": [o["id"] for o in restored["options"]],
            },
            "selection_mode": "single",
            "selection_mode_review_required": False,
            "source_review": "Source horizontal scale and full question/shared prompt checked against archived PDF.",
        }
        q["source"]["method"] = "pdf_horizontal_scale_stem_recovered"
        q["source"]["stem_page"] = rule["stem_page"]
        q["source"]["stem_bbox"] = rule["stem_bbox"]
        q["source"]["restored_first_option_bbox"] = first_box
        q["review_status"] = "question_and_scale_source_checked"
        change = {
            "assessment_id": a["assessment_id"],
            "item_id": q["id"],
            "previous_text": rule["old_text"],
            "recovered_text": recovered,
            "previous_response_set_id": old_set_id,
            "response_set_id": restored["id"],
            "restored_option_id": new_id,
            "restored_printed_value": option["printed_value"],
            "source_sha256": rule["source_sha256"],
            "source_page": rule["stem_page"],
            "source_bbox": rule["stem_bbox"],
        }
        changes.append(change)
        a["provenance"].setdefault("question_recovery", []).append(change)
    context_count = 0
    for rule in rules["contexts"]:
        a = rows[rule["assessment_id"]]
        with checked_pdf(a, rule["sha256"]) as pdf:
            text = source_text(pdf, rule["page"], rule["bbox"])
            if text != rule["text"]:
                raise ValueError("Shared prompt differs from reviewed PDF")
        for q in a["questionnaire"]["items"]:
            if q["id"] not in rule["item_ids"]:
                continue
            if q.get("context_text"):
                raise ValueError("Do not overwrite an existing context")
            q["context_text"] = re.sub(r"([ʼ’])\s+(?=s\b)", r"\1", text)
            q["context_origin"] = "source_pdf_shared_prompt"
            q["context_source"] = {
                "page": rule["page"],
                "bbox": rule["bbox"],
                "sha256": rule["sha256"],
                "method": "pdf_shared_prompt_checked",
            }
            context_count += 1
        a["provenance"].setdefault("shared_prompt_recovery", []).append(rule)
    changed_ids = {r["assessment_id"] for r in rules["questions"] + rules["contexts"]}
    for a in result["assessments"]:
        if a["assessment_id"] in changed_ids:
            a["definition_version"] = "1.0.0-draft.4"
            a["review"]["question_recovery_date"] = "2026-11-13"
            a["review"]["required_input_widgets"] = sorted(
                {q["input_spec"]["kind"] for q in a["questionnaire"]["items"]}
            )
    counts = Counter(c["assessment_id"] for c in changes)
    result["bundle_version"] = "2026-11-13-pdf-question-recovery"
    result["summary"]["corrected_question_stems"] = len(changes)
    result["summary"]["restored_first_options_by_item"] = len(changes)
    result["summary"]["items_with_recovered_shared_prompts"] = context_count
    result["usage_notes"].append(
        "PDF question recovery corrected 47 horizontal-scale items and restored each first option. Existing question IDs and existing option ID meanings are preserved; use item response_set_id to select the corrected scale."
    )
    report = {
        "input_bundle": INPUT_NAME,
        "output_bundle": OUTPUT_NAME,
        "assessment_count": len(rows),
        "corrected_question_stems": len(changes),
        "restored_first_options_by_item": len(changes),
        "shared_prompt_item_count": context_count,
        "corrections_by_assessment": dict(counts),
        "changes": changes,
        "shared_prompts": rules["contexts"],
        "limitations": [
            "This audit is not a guarantee of exhaustive questionnaire coverage.",
            "SDQ has no authorized digital questionnaire in the archived selection guide.",
            "Scoring, broader branching, OCR and supplemental documents retain their review requirements.",
        ],
    }
    return result, report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, default=HERE.parents[1])
    p.add_argument("--output", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    bundle, report = recover(
        read(args.project / "assessment-exports" / INPUT_NAME),
        read(HERE / "reviewed-question-recoveries.json"),
    )
    output = args.output or args.project / "assessment-exports" / OUTPUT_NAME
    save(output, bundle)
    save(
        args.report or output.with_name("question-recovery-report-20261113.json"),
        report,
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ["changes", "shared_prompts"]},
            indent=2,
        )
    )
    print(output)


if __name__ == "__main__":
    main()
