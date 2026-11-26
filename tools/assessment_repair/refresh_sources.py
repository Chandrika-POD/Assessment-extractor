"""Refresh all source pages and their questionnaire/scoring PDFs with resumable evidence."""

import argparse
import hashlib
import html
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project))
    import retrieval
    from source_parser import Tree, parse_html, scope_for

    # Explicit per-resource budget for scoring manuals that exceeded the old 3 MB cap.
    retrieval.MAX_BYTES = 30 * 1024 * 1024
    robots = {}

    def check_robots(url):
        p = retrieval.validate_url(url)
        host = p.hostname
        if host not in robots:
            status, headers, body = retrieval.request("https://" + host + "/robots.txt")
            if status == 404:
                robots[host] = None
            elif status != 200 or "text/html" in next(
                (v for k, v in headers.items() if k.lower() == "content-type"), ""
            ):
                raise retrieval.ExtractionError(
                    "Robots rules unavailable; stopped for this host", "restricted"
                )
            else:
                r = RobotFileParser()
                r.parse(body.decode("utf-8", errors="replace").splitlines())
                robots[host] = r
        r = robots[host]
        if r is not None:
            if not r.can_fetch(retrieval.AGENT, url):
                raise retrieval.ExtractionError(
                    "robots.txt disallows URL", "restricted"
                )
            delay = r.crawl_delay(retrieval.AGENT) or 0
            rate = r.request_rate(retrieval.AGENT)
            if rate:
                delay = max(delay, rate.seconds / rate.requests)
            if delay > 30:
                raise retrieval.ExtractionError(
                    "Crawl delay exceeds run budget", "restricted"
                )
            if delay:
                time.sleep(delay)

    retrieval.robots_allowed = check_robots
    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    manifest_path = work / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {
            "started_at": datetime.now(UTC).isoformat(),
            "pages": {},
            "pdfs": {},
            "status": "running",
        }
    )
    manifest["status"] = "running"
    save(manifest_path, manifest)
    bundle = json.loads(
        (
            args.project
            / "assessment-exports/novopsych-all-186-assessments-questions-recovered-20261113.json"
        ).read_text()
    )

    def fetch(url, group, extension):
        saved = manifest[group].get(url)
        if saved and saved["status"] == "retrieved":
            return saved
        entry = {"requested_url": url, "retrieved_at": datetime.now(UTC).isoformat()}
        try:
            final, mime, body = retrieval.public_fetch(url)
            if extension == "pdf" and not body.startswith(b"%PDF-"):
                raise ValueError("Not a PDF response")
            if extension == "html" and "html" not in mime:
                raise ValueError("Not an HTML response")
            sha = hashlib.sha256(body).hexdigest()
            file = work / "assets" / (sha + "." + extension)
            file.parent.mkdir(exist_ok=True)
            file.write_bytes(body)
            entry.update(
                status="retrieved",
                resolved_url=final,
                mime_type=mime,
                sha256=sha,
                bytes=len(body),
                path=str(file),
            )
        except Exception as exc:  # noqa: BLE001 - Record per-source failures; continue the batch.
            entry.update(
                status="failed",
                error=str(exc),
                error_status=getattr(exc, "status", "unavailable"),
            )
        manifest[group][url] = entry
        save(manifest_path, manifest)
        return entry

    def serialize(node):
        if isinstance(node, str):
            return html.escape(node)
        if node.tag in {
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "noscript",
            "template",
        }:
            return ""
        attrs = {
            k: v
            for k, v in node.attrs.items()
            if k not in {"style", "hidden", "aria-hidden"}
        }
        attr = "".join(
            " " + k + '="' + html.escape(str(v or ""), quote=True) + '"'
            for k, v in attrs.items()
        )
        return (
            "<"
            + node.tag
            + attr
            + ">"
            + "".join(serialize(c) for c in node.children)
            + "</"
            + node.tag
            + ">"
        )

    queue = {}
    for a in bundle["assessments"]:
        for d in a["source_documents"]:
            queue.setdefault(
                d["url"], {"assessment_ids": [], "roles": [], "old_sha256": d["sha256"]}
            )
            queue[d["url"]]["assessment_ids"].append(a["assessment_id"])
            queue[d["url"]]["roles"].append(d["role"])
    for i, a in enumerate(bundle["assessments"], 1):
        url = a["provenance"]["source_url"]
        entry = fetch(url, "pages", "html")
        if entry["status"] == "retrieved":
            content = Path(entry["path"]).read_text(errors="replace")
            tree = Tree()
            tree.feed(content)
            scope, _ = scope_for(tree.root, entry["resolved_url"])
            panels = [n for n in scope.walk() if n.attrs.get("role") == "tabpanel"]
            parsed = parse_html(serialize(scope), entry["resolved_url"])
            parsed["capture_method"] = (
                "fresh_response_html_including_embedded_hidden_tab_panels"
            )
            parsed["panel_count"] = len(panels)
            parsed["assessment_id"] = a["assessment_id"]
            save(work / "parsed-pages" / (a["assessment_id"] + ".json"), parsed)
            entry["parsed_path"] = str(
                work / "parsed-pages" / (a["assessment_id"] + ".json")
            )
            entry["panel_count"] = len(panels)
            links = []
            for n in scope.walk({"a"}):
                target = urljoin(entry["resolved_url"], n.attrs.get("href", ""))
                label = n.text()
                if urlsplit(target).path.lower().endswith(".pdf"):
                    links.append({"url": target, "title": label})
                    if re.search(r"sample|example|sample.report", label, re.IGNORECASE):
                        continue
                    if re.search(
                        r"download|question|scor|manual|psychometric|technical|review",
                        label + " " + urlsplit(target).path,
                        re.IGNORECASE,
                    ):
                        queue.setdefault(target, {"assessment_ids": [], "roles": []})
                        if a["assessment_id"] not in queue[target]["assessment_ids"]:
                            queue[target]["assessment_ids"].append(a["assessment_id"])
                        queue[target]["roles"].append(label or "linked_pdf")
            entry["pdf_links"] = links
        save(manifest_path, manifest)
        print(f"PAGE {i}/186 {entry['status']} {a['assessment_id']}", flush=True)
    save(work / "pdf-queue.json", queue)
    for i, (url, meta) in enumerate(queue.items(), 1):
        entry = fetch(url, "pdfs", "pdf")
        entry.update(meta)
        if entry["status"] == "retrieved" and meta.get("old_sha256"):
            entry["matches_archived_pdf"] = entry["sha256"] == meta["old_sha256"]
        save(manifest_path, manifest)
        print(f"PDF {i}/{len(queue)} {entry['status']} {url}", flush=True)
    manifest["status"] = "finished"
    manifest["finished_at"] = datetime.now(UTC).isoformat()
    save(manifest_path, manifest)
    print(
        "REFRESH COMPLETE",
        {
            group: {
                s: sum(e["status"] == s for e in manifest[group].values())
                for s in ["retrieved", "failed"]
            }
            for group in ["pages", "pdfs"]
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
