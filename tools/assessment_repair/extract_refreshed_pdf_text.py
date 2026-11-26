"""Parse completed downloads while the bounded source refresh continues."""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--ocr-command", default=shutil.which("tesseract"))
    p.add_argument("--ocr-data")
    p.add_argument("--ocr-library")
    args = p.parse_args()
    sys.path.insert(0, str(args.project / "tools/assessment_repair"))
    from complete_response_bundle import source_text

    source_cache = args.project / "artifacts/response-repair-20261113/pdf-text"
    target = args.work / "pdf-text"
    target.mkdir(exist_ok=True)
    while True:
        manifest = json.loads((args.work / "manifest.json").read_text())
        changed = 0
        for url, doc in manifest["pdfs"].items():
            if doc["status"] != "retrieved" or "sample" in url.lower():
                continue
            sha = doc["sha256"]
            output = target / (sha + ".json")
            if output.exists():
                continue
            prior = source_cache / (sha + ".json")
            try:
                if prior.exists():
                    data = json.loads(prior.read_text())
                else:
                    data = source_text(
                        Path(doc["path"]),
                        args.ocr_command,
                        args.ocr_data,
                        args.ocr_library,
                    )
                tmp = output.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                tmp.replace(output)
                changed += 1
                print("PDF TEXT", len(data["pages"]), "pages", sha, flush=True)
            except Exception as exc:  # noqa: BLE001 - Record per-source failures; continue the batch.
                output.with_suffix(".error.json").write_text(
                    json.dumps({"url": url, "error": str(exc)})
                )
                print("PDF TEXT ERROR", url, str(exc), flush=True)
        if manifest["status"] == "finished":
            break
        if not changed:
            time.sleep(5)
    print("PDF TEXT COMPLETE", len(list(target.glob("*.json"))), flush=True)


if __name__ == "__main__":
    main()
