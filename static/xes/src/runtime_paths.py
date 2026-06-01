from __future__ import annotations

from pathlib import Path

XES_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = XES_ROOT.parent.parent

XES_CONFIGS_DIR = XES_ROOT / "configs"
XES_OUTPUTS_DIR = XES_ROOT / "outputs"
XES_REPORTS_DIR = XES_ROOT / "reports"


def project_relative(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def xes_relative(*parts: str) -> Path:
    return XES_ROOT.joinpath(*parts)


def resolve_xes_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("../"):
        return (PROJECT_ROOT / normalized[3:]).resolve()
    if normalized.startswith("static/xes/"):
        return (PROJECT_ROOT / path).resolve()
    if normalized.split("/", 1)[0] in {"configs", "outputs", "reports"}:
        return (XES_ROOT / path).resolve()
    project_candidate = (PROJECT_ROOT / path).resolve()
    if project_candidate.exists():
        return project_candidate
    return (XES_ROOT / path).resolve()
