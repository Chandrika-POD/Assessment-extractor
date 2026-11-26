"""Serve only the repaired bundle, schema and review report on localhost."""

import argparse
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from paths import EXPORTS

CURRENT = EXPORTS / "current"
FILES = {
    "/all-assessments.json": CURRENT / "all-assessments.json",
    "/definition-clean-export.schema.json": CURRENT / "definition-clean-export.schema.json",
    "/validation-report.json": CURRENT / "validation-report.json",
    "/assessment-readiness.csv": CURRENT / "assessment-readiness.csv",
    "/all-assessments.json.sha256": CURRENT / "all-assessments.json.sha256",
    "/README.md": CURRENT / "README.md",
    "/scoring-verification-summary.json": CURRENT / "scoring-verification-summary.json",
    "/technical-scoring-audit.json": CURRENT / "technical-scoring-audit.json",
    "/source-benchmark-results.json": CURRENT / "source-benchmark-results.json",
    "/sdq-source-recovery.json": CURRENT / "sdq-source-recovery.json",
}


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        path = urlsplit(self.path).path
        if path == "/":
            html = (
                b'<!doctype html><meta charset="utf-8"><title>Assessment JSON download</title><h1>Current assessment export</h1><p>Structural validation passed; clinical review is still pending. Use all-assessments.json for integration development.</p><ul>'
                + b"".join(
                    ('<li><a href="' + url + '">' + file.name + "</a></li>").encode()
                    for url, file in FILES.items() if file.is_file()
                )
                + b"</ul><p>Reading these files does not run extraction.</p>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            if body:
                self.wfile.write(html)
            return
        file = FILES.get(path)
        if file is None or not file.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
            if file.suffix == ".json"
            else "text/csv; charset=utf-8" if file.suffix == ".csv"
            else "text/plain; charset=utf-8",
        )
        self.send_header(
            "Content-Disposition", 'attachment; filename="' + file.name + '"'
        )
        self.send_header("Content-Length", str(file.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            with file.open("rb") as f:
                shutil.copyfileobj(f, self.wfile)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=4185)
    args = p.parse_args()
    print("Download page: http://127.0.0.1:" + str(args.port) + "/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
