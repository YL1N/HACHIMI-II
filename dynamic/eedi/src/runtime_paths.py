from __future__ import annotations

from pathlib import Path

EEDI_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = EEDI_ROOT.parent.parent

EEDI_CONFIGS_DIR = EEDI_ROOT / "configs"
EEDI_OUTPUTS_DIR = EEDI_ROOT / "outputs"
EEDI_REPORTS_DIR = EEDI_ROOT / "reports"


def resolve_eedi_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("../"):
        return (PROJECT_ROOT / normalized[3:]).resolve()
    if normalized.startswith("dynamic/eedi/"):
        return (PROJECT_ROOT / path).resolve()
    if normalized.split("/", 1)[0] in {"configs", "outputs", "reports"}:
        return (EEDI_ROOT / path).resolve()
    project_candidate = (PROJECT_ROOT / path).resolve()
    if project_candidate.exists():
        return project_candidate
    return (EEDI_ROOT / path).resolve()
