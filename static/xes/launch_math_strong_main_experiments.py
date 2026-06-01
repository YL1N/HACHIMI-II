from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


XES_ROOT = Path(__file__).resolve().parent

CONFIG_PATH = "configs/run_local_9501_qwen.json"
FORMS = (
    (
        "Form_A",
        "outputs/principled_papers_frozen_questions/run_20260427_195718/Form_A_selected_questions.json",
    ),
    (
        "Form_B",
        "outputs/principled_papers_frozen_questions/run_20260427_195718/Form_B_selected_questions.json",
    ),
    (
        "Form_C",
        "outputs/principled_papers_frozen_questions/run_20260427_195718/Form_C_selected_questions.json",
    ),
)
GRADE_LABELS = {
    3: "三年级",
    4: "四年级",
    5: "五年级",
    6: "六年级",
}


@dataclass(frozen=True)
class RunSpec:
    grade: int
    grade_label: str
    form_name: str
    persona_path: str
    frozen_question_set_path: str
    output_root: str


def _build_run_specs(grades: list[int]) -> list[RunSpec]:
    specs: list[RunSpec] = []
    for grade in grades:
        if grade not in GRADE_LABELS:
            raise ValueError(f"unsupported grade: {grade}")
        grade_label = GRADE_LABELS[grade]
        persona_path = f"../data/personas_math_strong_grade{grade}_exact_20x4_seed42.jsonl"
        for form_name, frozen_path in FORMS:
            specs.append(
                RunSpec(
                    grade=grade,
                    grade_label=grade_label,
                    form_name=form_name,
                    persona_path=persona_path,
                    frozen_question_set_path=frozen_path,
                    output_root=f"outputs/math_strong_main_experiments/grade{grade}_math_strong/{form_name}_qwen9501_20q_80p",
                )
            )
    return specs


def _command_for_spec(spec: RunSpec) -> list[str]:
    return [
        sys.executable,
        "run_experiments.py",
        "--config",
        CONFIG_PATH,
        "--persona_path",
        spec.persona_path,
        "--target_grade",
        spec.grade_label,
        "--max_personas",
        "80",
        "--frozen_question_set_path",
        spec.frozen_question_set_path,
        "--output_root",
        spec.output_root,
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch math-strong persona main experiments for grade 3/4/5/6 on the three frozen grade-3 papers."
    )
    parser.add_argument(
        "--grades",
        type=int,
        nargs="+",
        default=[3, 4, 5, 6],
        help="Grades to run. Supported: 3 4 5 6.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Only write manifest and print commands without launching subprocesses.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    specs = _build_run_specs(args.grades)

    batch_root = XES_ROOT / "outputs" / "math_strong_main_experiments"
    batch_root.mkdir(parents=True, exist_ok=True)
    launch_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = batch_root / f"launcher_manifest_{launch_stamp}.json"

    manifest_rows: list[dict[str, object]] = []
    for spec in specs:
        output_root_path = (XES_ROOT / spec.output_root).resolve()
        output_root_path.mkdir(parents=True, exist_ok=True)
        manifest_rows.append(
            {
                **asdict(spec),
                "command": _command_for_spec(spec),
                "stdout_log": str(output_root_path / "launcher_stdout.log"),
                "stderr_log": str(output_root_path / "launcher_stderr.log"),
            }
        )
    manifest_path.write_text(json.dumps(manifest_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest_path": str(manifest_path)}, ensure_ascii=False))

    if args.dry_run:
        for row in manifest_rows:
            print(json.dumps(row, ensure_ascii=False))
        return

    grouped_specs: dict[int, list[RunSpec]] = {}
    for spec in specs:
        grouped_specs.setdefault(spec.grade, []).append(spec)

    for grade in args.grades:
        group = grouped_specs[grade]
        processes: list[tuple[RunSpec, subprocess.Popen[str], object, object]] = []
        print(json.dumps({"event": "grade_start", "grade": grade, "n_runs": len(group)}, ensure_ascii=False))
        for spec in group:
            output_root_path = (XES_ROOT / spec.output_root).resolve()
            stdout_path = output_root_path / "launcher_stdout.log"
            stderr_path = output_root_path / "launcher_stderr.log"
            stdout_file = stdout_path.open("w", encoding="utf-8", newline="\n")
            stderr_file = stderr_path.open("w", encoding="utf-8", newline="\n")
            process = subprocess.Popen(
                _command_for_spec(spec),
                cwd=str(XES_ROOT),
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
            )
            processes.append((spec, process, stdout_file, stderr_file))
            print(
                json.dumps(
                    {
                        "event": "run_started",
                        "grade": spec.grade,
                        "form": spec.form_name,
                        "pid": process.pid,
                        "output_root": str(output_root_path),
                    },
                    ensure_ascii=False,
                )
            )

        failures: list[dict[str, object]] = []
        for spec, process, stdout_file, stderr_file in processes:
            return_code = process.wait()
            stdout_file.close()
            stderr_file.close()
            print(
                json.dumps(
                    {
                        "event": "run_finished",
                        "grade": spec.grade,
                        "form": spec.form_name,
                        "pid": process.pid,
                        "return_code": return_code,
                    },
                    ensure_ascii=False,
                )
            )
            if return_code != 0:
                failures.append(
                    {
                        "grade": spec.grade,
                        "form": spec.form_name,
                        "return_code": return_code,
                        "output_root": spec.output_root,
                    }
                )

        if failures:
            raise RuntimeError(json.dumps({"grade": grade, "failures": failures}, ensure_ascii=False))
        print(json.dumps({"event": "grade_done", "grade": grade}, ensure_ascii=False))

    print(json.dumps({"event": "all_done"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
