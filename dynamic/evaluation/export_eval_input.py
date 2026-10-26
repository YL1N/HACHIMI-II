"""Export any method's predictions into the unified judge evaluation format.

Works for both HACHIMI-II and baseline outputs. Takes a run directory
containing predictions.jsonl and joins with annotated EEDI data to produce
official_eval_input.csv, which run_detached_eval.py consumes.

Usage:
    python export_eval_input.py --run_dir <path_to_run_output> --annotated_eedi_dir <path>
    python export_eval_input.py --all_dirs <parent_dir> --annotated_eedi_dir <path>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_export_function():
    module_path = PROJECT_ROOT / "dynamic" / "eedi" / "src" / "evaluation_eedi.py"
    if not module_path.exists():
        raise FileNotFoundError(f"evaluation_eedi not found: {module_path}")
    spec = importlib.util.spec_from_file_location(
        "evaluation_eedi_for_export",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import evaluation_eedi from: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.export_official_eval_csv


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export predictions into judge-compatible CSV (works for any method)."
    )
    parser.add_argument(
        "--run_dir", type=str, default="",
        help="Run directory containing predictions.jsonl.",
    )
    parser.add_argument(
        "--all_dirs", type=str, default="",
        help="Parent directory; exports all subdirectories containing predictions.jsonl.",
    )
    parser.add_argument(
        "--annotated_eedi_dir", type=str,
        default=str(PROJECT_ROOT / "external" / "sim-student-eval" / "data" / "annotated" / "eedi"),
        help="Annotated EEDI directory from sim-student-eval.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    export_fn = _load_export_function()
    annotated_eedi_dir = Path(args.annotated_eedi_dir)
    if not annotated_eedi_dir.exists():
        raise FileNotFoundError(f"annotated EEDI dir not found: {annotated_eedi_dir}")

    run_dirs = _resolve_run_dirs(args.run_dir, args.all_dirs)
    exported = 0
    skipped = 0
    for run_dir in run_dirs:
        predictions_path = run_dir / "predictions.jsonl"
        if not predictions_path.exists():
            skipped += 1
            print(f"SKIP {run_dir} — missing predictions.jsonl")
            continue
        records = _load_jsonl(predictions_path)
        out_path = export_fn(
            output_dir=run_dir,
            records=records,
            annotated_eedi_dir=annotated_eedi_dir,
        )
        if out_path is None:
            skipped += 1
            print(f"SKIP {run_dir} — no matched annotated rows")
            continue
        exported += 1
        print(f"OK   {out_path}")

    print(f"\nexported={exported} skipped={skipped}")


def _resolve_run_dirs(run_dir: str, all_dirs: str) -> list[Path]:
    if all_dirs.strip():
        parent = Path(all_dirs.strip())
        if not parent.is_dir():
            raise FileNotFoundError(f"parent dir not found: {parent}")
        return sorted(
            [p for p in parent.iterdir() if p.is_dir() and (p / "predictions.jsonl").exists()],
            key=lambda p: p.name,
        )
    if run_dir.strip():
        path = Path(run_dir.strip())
        if not path.is_dir():
            raise FileNotFoundError(f"run dir not found: {path}")
        return [path]
    raise ValueError("provide either --run_dir or --all_dirs")


if __name__ == "__main__":
    main()
