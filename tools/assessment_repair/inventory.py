import json

from json_io import save
from paths import EVIDENCE, OLD
from pdf_layout import extract_pdf

ROOT = OLD
WORK = EVIDENCE


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    summary = []
    for row in manifest["items"]:
        a = json.loads((ROOT / row["json_file"]).read_text(encoding="utf-8"))
        docs = a["assets"]["documents"]
        eligible = [
            x
            for x in docs
            if not any(
                t in x.get("title", "").lower()
                for t in ["sample results", "sample report", "manual"]
            )
            and (x.get("archive") or x.get("storage_key"))
        ]
        wanted = [x for x in eligible if "download" in x.get("title", "").lower()]
        # Avoid a related instrument's download linked in the same page.
        matching = [
            x
            for x in wanted
            if row["title"].split("(")[-1].rstrip(")").lower()
            in x.get("title", "").lower()
        ]
        doc = (
            next(iter(matching), None)
            or next((x for x in eligible if x.get("used_for_main_questionnaire")), None)
            or next(iter(wanted), None)
            or next(iter(eligible), None)
        )
        preferred = {
            "client-satisfaction-survey-css--": "css_-Client-Satisfaction-Survey.pdf",
            "problem-gambling-severity-index-pgsi--": "pgsi-problem-gambling-severity-index-online-assessment.pdf",
            "eating-attitudes-test-26-eat-26--": "eat-26_assessment_form.pdf",
        }
        for key, ending in preferred.items():
            if key in row["source_key"]:
                doc = next(
                    (x for x in eligible if x.get("url", "").endswith(ending)), doc
                )
        if not doc:
            summary.append(
                {
                    "key": row["source_key"],
                    "old": row["extracted_questions"],
                    "new": 0,
                    "error": "no_questionnaire_pdf",
                }
            )
            continue
        archive = doc.get("archive", doc)
        path = (ROOT / "assessments" / archive["storage_key"]).resolve()
        try:
            parsed = extract_pdf(path)
            if not parsed["items"]:
                alternatives = [
                    x
                    for x in eligible
                    if x is not doc and x.get("used_for_main_questionnaire")
                ]
                for alternative in alternatives:
                    aa = alternative.get("archive", alternative)
                    ap = (ROOT / "assessments" / aa["storage_key"]).resolve()
                    candidate = extract_pdf(ap)
                    if candidate["items"]:
                        parsed, doc, archive, path = candidate, alternative, aa, ap
                        break
        except Exception as e:
            summary.append(
                {
                    "key": row["source_key"],
                    "old": row["extracted_questions"],
                    "new": 0,
                    "error": str(e),
                }
            )
            continue
        parsed["pdf_path"] = str(path)
        parsed["pdf_url"] = doc.get("url", doc.get("source_url"))
        parsed["sha256"] = archive["sha256"]
        save(WORK / (row["source_key"] + ".parsed.json"), parsed)
        summary.append(
            {
                "key": row["source_key"],
                "old": row["extracted_questions"],
                "new": len(parsed["items"]),
                "numbers": [x["source_number"] for x in parsed["items"]],
            }
        )
        if len(summary) % 30 == 0:
            print("Parsed", len(summary), flush=True)
    save(WORK / "layout-summary.json", summary)
    print(
        "assessments",
        len(summary),
        "with_rows",
        sum(x["new"] > 0 for x in summary),
        "items",
        sum(x["new"] for x in summary),
        flush=True,
    )
    for x in summary:
        if x["old"] != x["new"]:
            print(x, flush=True)


if __name__ == "__main__":
    main()
