"""Add source-checked response types and omitted PDF fields to the review bundle.

No scores are enabled and no finite choices are fabricated for written/numeric inputs.
Run from the repository with its repair dependencies installed.
"""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pymupdf as fitz
from response_overrides import apply, choice_schema, pardi_additional_fields

OLD_NAME = "novopsych-all-186-assessments-repaired-20261113.json"
FINAL_NAME = "novopsych-all-186-assessments-final-20261113.json"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def source_text(pdf_path, ocr_command=None, ocr_data=None, ocr_library=None):
    doc = fitz.open(pdf_path)
    raw = subprocess.check_output(
        ["pdftotext", "-layout", str(pdf_path), "-"], stderr=subprocess.DEVNULL
    ).decode("utf-8")
    texts = raw.split("\f")
    pages = []
    for i, page in enumerate(doc):
        native = texts[i].strip() if i < len(texts) else ""
        images = page.get_image_info()
        full_image = any(
            fitz.Rect(im["bbox"]).get_area() / page.rect.get_area() > 0.65
            for im in images
        )
        needs_ocr = len(native.strip()) < 80 or (full_image and len(native) < 400)
        ocr = None
        error = None
        if needs_ocr and ocr_command:
            try:
                with tempfile.TemporaryDirectory(prefix="assessment-pdf-ocr-") as temp:
                    image = Path(temp) / "page.png"
                    page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5)).save(image)
                    args = [
                        ocr_command,
                        str(image),
                        "stdout",
                        "-l",
                        "eng",
                        "--psm",
                        "3",
                    ]
                    if ocr_data:
                        args.extend(["--tessdata-dir", ocr_data])
                    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
                    if ocr_library:
                        env["LD_LIBRARY_PATH"] = ocr_library
                    ocr = (
                        subprocess.check_output(
                            args, stderr=subprocess.PIPE, env=env, timeout=60
                        )
                        .decode("utf-8")
                        .strip()
                    )
            except Exception as exc:
                error = str(exc)
        pages.append(
            {
                "page": i + 1,
                "text": ocr if ocr else native,
                "native_text": native if ocr else None,
                "method": "ocr" if ocr else "pdf_text",
                "ocr_review_required": bool(ocr),
                "image_count": len(images),
                "image_only_text_unresolved": bool(needs_ocr and not ocr),
                "error": error,
            }
        )
    return {
        "page_count": len(doc),
        "pages": pages,
        "coverage_note": "Page text includes printed instructions, notes and scoring text. OCR requires review; PDF images/diagrams are preserved in the source asset, not interpreted as validated data.",
    }


def set_choice_inputs(a):
    sets = {s["id"]: s for s in a["questionnaire"]["response_sets"]}
    for s in sets.values():
        for option in s["options"]:
            option["display_label"] = option["label"] or (
                str(option["printed_value"])
                if option["printed_value"] is not None
                else None
            )
            option["display_label_origin"] = (
                "printed_label" if option["label"] else "printed_number_only"
            )
    for q in a["questionnaire"]["items"]:
        if q.get("input_spec") or not q["response_set_id"]:
            continue
        options = sets[q["response_set_id"]]["options"]
        schema = choice_schema(options)
        # Existing unspecified selection modes remain visibly unreviewed.
        q["input_spec"] = {
            "kind": "single_choice" if q["selection_mode"] == "single" else "choice",
            "answer_schema": schema,
            "selection_mode": q["selection_mode"],
            "selection_mode_review_required": q["selection_mode"] is None,
            "source_review": "Retained printed response set; no new option labels or scores inferred.",
        }


def add_choci_context(a, pdf):
    if not a["assessment_id"].startswith(
        (
            "obsessional-compulsive-inventory-ocd-child-self-report--",
            "obsessional-compulsive-inventory-revised-parent-choci-r-p--",
        )
    ):
        return
    qs = a["questionnaire"]["items"]
    byid = {q["id"]: q for q in qs}
    for first, last, previous in [("Q11", "Q13", "Q10"), ("Q30", "Q32", "Q29")]:
        q = byid[first]
        prev = byid[previous]
        top = (
            prev["source"]["bbox"][3]
            if prev["source"]["page"] == q["source"]["page"]
            else 35
        )
        rect = fitz.Rect(
            33,
            top,
            pdf[q["source"]["page"] - 1].rect.width - 25,
            q["source"]["bbox"][1],
        )
        text = " ".join(
            pdf[q["source"]["page"] - 1]
            .get_text("text", clip=rect, flags=fitz.TEXT_INHIBIT_SPACES)
            .split()
        )
        if not text:
            raise ValueError("Missing ChOCI group instruction: " + first)
        for number in range(int(first[1:]), int(last[1:]) + 1):
            byid["Q" + str(number)]["context_text"] = text
            byid["Q" + str(number)]["context_source"] = {
                "page": q["source"]["page"],
                "bbox": list(rect),
                "method": "pdf_group_instruction",
            }


def repair_one(a, source_checks, cache, args):
    a = copy.deepcopy(a)
    old_count = len(a["questionnaire"]["items"])
    resolved = apply(a)
    a["schema_version"] = "2.1.0"
    a["definition_version"] = "1.0.0-draft.3"
    added = 0
    selected = next(
        (s for s in a["assets"] if s["role"] == "selected_questionnaire"), None
    )
    sdq = a["assessment_id"].startswith(
        "strengths-and-difficulties-questionnaire-sdq--"
    )
    if selected:
        pdf_path = Path(selected["archive_path"])
        sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        if sha != selected["sha256"]:
            raise ValueError("Changed source asset: " + str(pdf_path))
        pdf = fitz.open(pdf_path)
        added = pardi_additional_fields(a, pdf)
        add_choci_context(a, pdf)
        if sha not in cache:
            cached = args.work / "pdf-text" / f"{sha}.json"
            if cached.is_file():
                cache[sha] = json.loads(cached.read_text())
            else:
                cache[sha] = source_text(
                    pdf_path, args.ocr_command, args.ocr_data, args.ocr_library
                )
                save(cached, cache[sha])
        a["source_documents"] = [
            {
                "id": "selected_pdf",
                "role": "version_selection_guide" if sdq else "questionnaire_source",
                "url": selected["source_url"],
                "sha256": sha,
                "archive_path": str(pdf_path),
                "runtime_context_allowed": False,
                **cache[sha],
            }
        ]
        if selected["source_url"] in source_checks:
            a["provenance"]["response_pdf_live_check"] = source_checks[
                selected["source_url"]
            ]
            if not source_checks[selected["source_url"]].get("matches_archived_pdf"):
                raise ValueError(
                    "Live PDF changed; review before applying old response definitions."
                )
    else:
        a["source_documents"] = []
    set_choice_inputs(a)
    if a["assessment_id"].startswith("crafft-substance-use-assessment-crafft-2-1-n--"):
        a["administration"]["instructions"] = (
            "Part A records the number of days each substance was used in the past 12 months. Later sections follow the source branching guidance retained below."
        )
        a["administration"]["instructions_source"] = {
            "url": a["provenance"]["source_url"],
            "section": "CRAFFT 2.1+N Structure",
            "method": "source_summary",
        }
        a["administration"]["instructions_note"] = (
            "The PDF has no opening instruction block. This brief summary is from the assessment webpage; it is not a verbatim publisher instruction."
        )
        a["assessment"]["reference_period"]["instruction_claims"] = [
            "past 12 months for Part A; other parts have their own wording"
        ]
    issues = a["review"]["issues"]
    if resolved:
        issues = [i for i in issues if i["code"] != "non_choice_fields_need_review"]
        a["review"]["response_format_review"] = {
            "resolved_previously_untyped_fields": resolved,
            "basis": "Selected archived PDF edition checked against current public PDF and inspected for field controls.",
            "clinical_scoring_review": False,
        }
    if a["administration"]["instructions"]:
        issues = [i for i in issues if i["code"] != "instructions_missing"]
    if sdq:
        selected["role"] = "version_selection_guide"
        a["rights"]["digital_questionnaire_status"] = "publisher_authorization_required"
        a["rights"]["digital_questionnaire_evidence_url"] = "https://www.sdqinfo.org/"
        a["rights"]["digital_questionnaire_note"] = (
            "The publisher permits specified paper use but requires prior authorization for electronic versions. No authorized digital questionnaire was supplied."
        )
        a["questionnaire"]["source_availability"] = {
            "status": "publisher_forms_linked_not_digitized",
            "publisher_downloads_url": "https://www.sdqinfo.org/py/sdqinfo/b0.py",
            "novopsych_pdf_role": "version_selection_guide_not_questionnaire",
            "requires": ["authorized digital form", "respondent type and age variant"],
        }
        issues.append(
            {
                "code": "sdq_authorized_digital_form_required",
                "detail": a["rights"]["digital_questionnaire_note"],
            }
        )
    qs = a["questionnaire"]["items"]
    a["questionnaire"]["item_count"] = len(qs)
    a["administration"]["item_order"] = [q["id"] for q in qs]
    unresolved = [
        q["id"]
        for q in qs
        if q["response_type"] == "unverified" or "input_spec" not in q
    ]
    required_widgets = sorted(
        {q["input_spec"]["kind"] for q in qs if "input_spec" in q}
    )
    a["review"]["issues"] = issues
    a["review"]["response_structure_complete"] = bool(qs) and not unresolved
    a["review"]["unresolved_response_item_ids"] = unresolved
    a["review"]["required_input_widgets"] = required_widgets
    a["review"]["ready_for_clinical_use"] = False
    a["review"]["questionnaire_completeness_verified"] = False
    a["scoring"]["enabled"] = False
    a["provenance"]["response_repair"] = {
        "date": "2026-11-13",
        "original_item_count": old_count,
        "added_unnumbered_fields": added,
        "resolved_response_types": resolved,
        "source_review_is_not_clinical_approval": True,
    }
    return a, {
        "assessment_id": a["assessment_id"],
        "name": a["assessment"]["name"],
        "item_count": len(qs),
        "resolved_fields": resolved,
        "added_fields": added,
        "response_structure_complete": bool(qs) and not unresolved,
        "unresolved_item_ids": unresolved,
        "required_widgets": required_widgets,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ocr-command")
    parser.add_argument("--ocr-data")
    parser.add_argument("--ocr-library")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    source = args.project / "assessment-exports" / OLD_NAME
    bundle = json.loads(source.read_text())
    checks_path = Path(__file__).with_name("source-checks.json")
    checks = {r["url"]: r for r in json.loads(checks_path.read_text())}
    cache = {}
    rows = []
    reports = []
    for i, a in enumerate(bundle["assessments"], 1):
        d, r = repair_one(a, checks, cache, args)
        rows.append(d)
        reports.append(r)
        if i % 20 == 0:
            print("Completed", i, "/", len(bundle["assessments"]), flush=True)
    summary = {
        **bundle["summary"],
        "recovered_item_count": sum(len(d["questionnaire"]["items"]) for d in rows),
        "response_structure_complete_count": sum(
            r["response_structure_complete"] for r in reports
        ),
        "resolved_previously_untyped_fields": sum(
            r["resolved_fields"] for r in reports
        ),
        "added_unnumbered_fields": sum(r["added_fields"] for r in reports),
        "unresolved_response_fields": sum(
            len(r["unresolved_item_ids"]) for r in reports
        ),
        "assessments_missing_questionnaire": sum(
            not d["questionnaire"]["items"] for d in rows
        ),
    }
    contract = {
        "schema_version": "2.1.0",
        "scoring_is_enabled": False,
        "supported_response_types": [
            "choice",
            "single_choice",
            "multiple_choice",
            "integer",
            "number",
            "text",
        ],
        "choice_rendering": "Resolve response_set_id and render display_label; a missing verbal anchor may display the printed number.",
        "non_choice_rendering": "Numeric and written answers use input_spec.answer_schema and do not need a response_set_id or fabricated options.",
        "conditional_fields": "Evaluate display_if when supplied. Missing dependency answers mean eligibility is unresolved; do not silently record 0.",
        "additional_review": "Source selection modes and full branching still require instrument review. A complete response structure does not mean clinically approved.",
        "skip_handling": "Record skipped/unanswered separately. NA is allowed only where the source explicitly provides it.",
        "import_warning": "A choice-only importer will continue to reject valid numeric/text fields until it supports these input types.",
    }
    output = args.output or args.project / "assessment-exports" / FINAL_NAME
    final = {
        "schema_version": "2.1.0",
        "bundle_version": "2026-11-13-response-repair",
        "status": "review_draft",
        "summary": summary,
        "import_contract": contract,
        "usage_notes": bundle["usage_notes"]
        + [
            "The final filename identifies this export revision; SDQ remains blocked and no clinical scoring has been enabled.",
            "Source PDFs include complete extracted page text; diagrams and OCR still need source review.",
        ],
        "assessments": rows,
    }
    save(output, final)
    save(
        args.work / "response-review-report.json",
        {"summary": summary, "assessments": reports},
    )
    print(json.dumps(summary, indent=2), flush=True)
    print(output, flush=True)


if __name__ == "__main__":
    main()
