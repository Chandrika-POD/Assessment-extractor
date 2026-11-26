"""Repository-relative locations shared by the offline repair commands."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = PROJECT_ROOT / "assessment-registry"
EXPORTS = PROJECT_ROOT / "assessment-exports"
OLD = EXPORTS / "cleaned-assessments-20261112"
EVIDENCE = REGISTRY / "repair-20261113" / "evidence"
OUT = EXPORTS / "repaired-assessments-20261113"
BUNDLE = EXPORTS / "novopsych-all-186-assessments-repaired-20261113.json"
SCHEMA = Path(__file__).with_name("definition.schema.json")
