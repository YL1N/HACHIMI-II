from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation_eedi import export_official_eval_csv
from src.runtime_paths import EEDI_OUTPUTS_DIR, PROJECT_ROOT


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export run outputs into sim-student-eval compatible CSV files."
    )
    parser.add_argument(
        "--run_dir",
        type=str,
        default="",
        help="Specific EEDI run directory containing predictions.jsonl.",
    )
    parser.add_argument(
        "--all_runs",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Export all run_* directories under dynamic/eedi/outputs.",
    )
    parser.add_argument(
        "--annotated_eedi_dir",
        type=str,
        default=str(PROJECT_ROOT / "external/sim-student-eval/data/annotated/eedi"),
        help="Annotated EEDI directory from sim-student-eval.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    run_dirs = _resolve_run_dirs(args.run_dir, args.all_runs)
    annotated_eedi_dir = Path(args.annotated_eedi_dir)
    if not annotated_eedi_dir.exists():
        raise FileNotFoundError(f"annotated EEDI dir not found: {annotated_eedi_dir}")

    exported = 0
    skipped = 0
    for run_dir in run_dirs:
        predictions_path = run_dir / "predictions.jsonl"
        if not predictions_path.exists():
            skipped += 1
            print(f"SKIP {run_dir} missing predictions.jsonl")
            continue
        records = _load_jsonl(predictions_path)
        out_path = export_official_eval_csv(
            output_dir=run_dir,
            records=records,
            annotated_eedi_dir=annotated_eedi_dir,
        )
        if out_path is None:
            skipped += 1
            print(f"SKIP {run_dir} no matched annotated rows")
            continue
        exported += 1
        print(f"OK {out_path}")

    print(f"exported={exported} skipped={skipped}")


def _resolve_run_dirs(run_dir: str, all_runs: bool) -> list[Path]:
    run_dir_text = run_dir.strip()
    if all_runs:
        return sorted(
            [path for path in EEDI_OUTPUTS_DIR.glob("run_*") if path.is_dir()],
            key=lambda path: path.name,
        )
    if run_dir_text:
        path = Path(run_dir_text)
        if not path.exists():
            raise FileNotFoundError(f"run dir not found: {path}")
        if not path.is_dir():
            raise ValueError(f"run dir is not a directory: {path}")
        return [path]
    raise ValueError("provide either --run_dir or --all_runs")


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(
                    f"jsonl row in {path} at line {line_no} must be object/dict"
                )
            rows.append(row)
    return rows


if __name__ == "__main__":
    main()
