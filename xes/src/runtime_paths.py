from __future__ import annotations

from pathlib import Path

XES_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = XES_ROOT.parent

XES_CONFIGS_DIR = XES_ROOT / "configs"
XES_OUTPUTS_DIR = XES_ROOT / "outputs"
XES_REPORTS_DIR = XES_ROOT / "reports"


def project_relative(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def xes_relative(*parts: str) -> Path:
    return XES_ROOT.joinpath(*parts)
