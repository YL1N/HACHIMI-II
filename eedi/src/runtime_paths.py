from __future__ import annotations

from pathlib import Path

EEDI_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = EEDI_ROOT.parent

EEDI_CONFIGS_DIR = EEDI_ROOT / "configs"
EEDI_OUTPUTS_DIR = EEDI_ROOT / "outputs"
EEDI_REPORTS_DIR = EEDI_ROOT / "reports"
