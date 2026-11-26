"""Validate the generated artifact and persist results tied to its SHA-256."""

import hashlib
import json
import unittest

from json_io import save
from paths import BUNDLE, OUT, SCHEMA
from test_repair import RepairTests


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RepairTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "status": "passed" if result.wasSuccessful() else "failed",
        "test_count": result.testsRun,
        "failure_count": len(result.failures),
        "error_count": len(result.errors),
        "bundle_sha256": hashlib.sha256(BUNDLE.read_bytes()).hexdigest(),
        "limitations": "Automated structural/regression checks and selected source transcriptions; not a full independent clinical review.",
        "failures": [
            {"test": str(t), "details": s} for t, s in result.failures + result.errors
        ],
    }
    save(OUT / "validation-results.json", report)
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    manifest["validation_status"] = report["status"]
    manifest["validation_test_count"] = result.testsRun
    save(OUT / "manifest.json", manifest)
    save(OUT / "definition.schema.json", json.loads(SCHEMA.read_text(encoding="utf-8")))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
