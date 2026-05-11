from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from src.root_cause_workflow import (
    DEFAULT_FROZEN_QUESTION_SET_PATH,
    ROOT_CAUSE_C1_REPORT_PATH,
    ROOT_CAUSE_D1_REPORT_PATH,
    ROOT_CAUSE_D2_REPORT_PATH,
    ROOT_CAUSE_E1_REPORT_PATH,
    ROOT_CAUSE_F1_REPORT_PATH,
    ROOT_CAUSE_G1_REPORT_PATH,
    ROOT_CAUSE_OUTPUT_ROOT,
    collect_run_progress,
    run_d1_simple_forced_state,
    run_d2_full_forced_state,
    run_e1_counterfactual_sensitivity,
    run_f1_stability,
    update_root_cause_plan,
    write_c1_report,
    write_d1_report,
    write_d2_report,
    write_e1_report,
    write_f1_report,
    write_g1_report,
)
from src.runtime_paths import XES_ROOT
ROOT = XES_ROOT
SUPERVISOR_LOG_PATH = ROOT_CAUSE_OUTPUT_ROOT / "supervisor.log"
CHILD_LOG_ROOT = ROOT_CAUSE_OUTPUT_ROOT / "supervisor_children"
SMOKE_REPORT_ROOT = ROOT_CAUSE_OUTPUT_ROOT / "smoke_reports"
C1_RUN_DIRS = {
    "direct": ROOT / "outputs/root_cause/C1_direct/run_20260420_225055",
    "state_single": ROOT / "outputs/root_cause/C1_state_single/run_20260420_225125",
    "state_step": ROOT / "outputs/root_cause/C1_state_step/run_20260420_225213",
}


def _log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    SUPERVISOR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUPERVISOR_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _path_for_plan(path: Path) -> str:
    return str(path).replace("\\", "/")


def _latest_completed_run(stage_root: Path) -> Path | None:
    if not stage_root.exists():
        return None
    completed = [
        child
        for child in stage_root.iterdir()
        if child.is_dir() and (child / "metrics.json").exists()
    ]
    if not completed:
        return None
    return sorted(completed, key=lambda path: path.name)[-1]


def _latest_run(stage_root: Path) -> Path | None:
    if not stage_root.exists():
        return None
    runs = [child for child in stage_root.iterdir() if child.is_dir()]
    if not runs:
        return None
    return sorted(runs, key=lambda path: path.name)[-1]


def _stage_output_root(stage_id: str, smoke: bool = False) -> Path | None:
    if stage_id == "D1":
        return ROOT / (
            "outputs/root_cause/D1_simple_forced_state_smoke"
            if smoke
            else "outputs/root_cause/D1_simple_forced_state"
        )
    if stage_id == "D2":
        return ROOT / (
            "outputs/root_cause/D2_full_forced_state_smoke"
            if smoke
            else "outputs/root_cause/D2_full_forced_state"
        )
    if stage_id == "E1":
        return ROOT / (
            "outputs/root_cause/E1_counterfactual_sensitivity_smoke"
            if smoke
            else "outputs/root_cause/E1_counterfactual_sensitivity"
        )
    if stage_id == "F1":
        return ROOT / (
            "outputs/root_cause/F1_stability_smoke"
            if smoke
            else "outputs/root_cause/F1_stability"
        )
    return None


def _is_stage_inflight(
    stage_id: str,
    max_stale_seconds: int,
    smoke: bool = False,
) -> bool:
    stage_root = _stage_output_root(stage_id, smoke=smoke)
    if stage_root is None:
        return False
    run_dir = _latest_run(stage_root)
    if run_dir is None or (run_dir / "metrics.json").exists():
        return False
    progress = collect_run_progress(run_dir)
    latest_update_ts = progress["latest_update_ts"]
    if latest_update_ts is None:
        return False
    return (time.time() - float(latest_update_ts)) <= max_stale_seconds


def _is_stage_complete(stage_id: str) -> bool:
    if stage_id == "C1":
        return all((run_dir / "metrics.json").exists() for run_dir in C1_RUN_DIRS.values()) and ROOT_CAUSE_C1_REPORT_PATH.exists()
    if stage_id == "D1":
        return _latest_completed_run(ROOT / "outputs/root_cause/D1_simple_forced_state") is not None and ROOT_CAUSE_D1_REPORT_PATH.exists()
    if stage_id == "D2":
        return _latest_completed_run(ROOT / "outputs/root_cause/D2_full_forced_state") is not None and ROOT_CAUSE_D2_REPORT_PATH.exists()
    if stage_id == "E1":
        return _latest_completed_run(ROOT / "outputs/root_cause/E1_counterfactual_sensitivity") is not None and ROOT_CAUSE_E1_REPORT_PATH.exists()
    if stage_id == "F1":
        return _latest_completed_run(ROOT / "outputs/root_cause/F1_stability") is not None and ROOT_CAUSE_F1_REPORT_PATH.exists()
    if stage_id == "G1":
        return ROOT_CAUSE_G1_REPORT_PATH.exists()
    raise ValueError(f"unknown stage_id: {stage_id}")


def _launch_child(label: str, args: list[str]) -> subprocess.Popen[str]:
    CHILD_LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stdout_path = CHILD_LOG_ROOT / f"{label}_stdout.log"
    stderr_path = CHILD_LOG_ROOT / f"{label}_stderr.log"
    stdout_file = stdout_path.open("a", encoding="utf-8")
    stderr_file = stderr_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        args,
        cwd=str(ROOT),
        stdout=stdout_file,
        stderr=stderr_file,
        text=True,
    )
    _log(f"launched child label={label} pid={process.pid} args={args}")
    return process


def _resume_c1_if_stale(
    label: str,
    run_dir: Path,
    method_variant: str,
    children: dict[str, subprocess.Popen[str]],
    max_stale_seconds: int,
) -> None:
    if (run_dir / "metrics.json").exists():
        return
    progress = collect_run_progress(run_dir)
    latest_update_ts = progress["latest_update_ts"]
    if latest_update_ts is None:
        stale = True
    else:
        stale = (time.time() - float(latest_update_ts)) > max_stale_seconds
    child_label = f"C1_resume_{method_variant}"
    if not stale:
        return
    if child_label in children and children[child_label].poll() is None:
        return
    args = [
        sys.executable,
        "run_experiments.py",
        "--config",
        "configs/run_local.json",
        "--resume_run_dir",
        _path_for_plan(run_dir.relative_to(ROOT)),
        "--frozen_question_set_path",
        _path_for_plan(DEFAULT_FROZEN_QUESTION_SET_PATH),
        "--persona_variant",
        "full_persona",
        "--method_variant",
        method_variant,
        "--max_concurrency",
        "16",
    ]
    children[child_label] = _launch_child(child_label, args)


def _finalize_c1() -> None:
    summary = write_c1_report(
        direct_run_dir=C1_RUN_DIRS["direct"],
        state_single_run_dir=C1_RUN_DIRS["state_single"],
        state_step_run_dir=C1_RUN_DIRS["state_step"],
    )
    direct_metrics = _read_json(C1_RUN_DIRS["direct"] / "metrics.json")
    single_metrics = _read_json(C1_RUN_DIRS["state_single"] / "metrics.json")
    step_metrics = _read_json(C1_RUN_DIRS["state_step"] / "metrics.json")
    actual_conclusions = [
        summary,
        f"direct item Pearson = {direct_metrics['item_accuracy_pearson_vs_real_students']:.4f}",
        f"state_single item Pearson = {single_metrics['item_accuracy_pearson_vs_real_students']:.4f}",
        f"state_step item Pearson = {step_metrics['item_accuracy_pearson_vs_real_students']:.4f}",
        f"direct strict_monotonic = {direct_metrics['strict_monotonic_item_count']}",
        f"state_single strict_monotonic = {single_metrics['strict_monotonic_item_count']}",
        f"state_step strict_monotonic = {step_metrics['strict_monotonic_item_count']}",
    ]
    update_root_cause_plan(
        stage_id="C1",
        output_dir=(
            f"direct={_path_for_plan(C1_RUN_DIRS['direct'].relative_to(ROOT))}; "
            f"state_single={_path_for_plan(C1_RUN_DIRS['state_single'].relative_to(ROOT))}; "
            f"state_step={_path_for_plan(C1_RUN_DIRS['state_step'].relative_to(ROOT))}"
        ),
        summary=summary,
        current_position="A1 已冻结；B1/B2/B3/C1 已完成；正式根因归因实验继续推进",
        next_step="D1 强制状态服从：simple_forced_state",
        actual_config_lines=[
            f"direct run：{_path_for_plan(C1_RUN_DIRS['direct'].relative_to(ROOT))}",
            f"state_single run：{_path_for_plan(C1_RUN_DIRS['state_single'].relative_to(ROOT))}",
            f"state_step run：{_path_for_plan(C1_RUN_DIRS['state_step'].relative_to(ROOT))}",
            "固定 persona = full_persona",
            "固定题集 = outputs/run_20260420_014128/selected_questions.json",
        ],
        actual_conclusion_lines=actual_conclusions,
    )
    _log("C1 finalized: report written and plan updated")


def _run_stage_worker(stage: str, smoke: bool = False) -> None:
    if stage == "C1":
        _finalize_c1()
        return
    if stage == "D1":
        run_dir = run_d1_simple_forced_state(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("D1_simple_forced_state_smoke" if smoke else "D1_simple_forced_state"),
            samples_per_state=2 if smoke else 20,
            max_questions=4 if smoke else None,
            max_concurrency=4 if smoke else 16,
        )
        report_path = (
            SMOKE_REPORT_ROOT / "d1_simple_forced_state_smoke.md"
            if smoke
            else ROOT_CAUSE_D1_REPORT_PATH
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        summary = write_d1_report(run_dir, report_path=report_path)
        if smoke:
            _log(f"D1 smoke completed: {run_dir}")
            return
        metrics = _read_json(run_dir / "metrics.json")
        update_root_cause_plan(
            stage_id="D1",
            output_dir=_path_for_plan(run_dir.relative_to(ROOT)),
            summary=summary,
            current_position="A1 已冻结；B1/B2/B3/C1/D1 已完成；正式根因归因实验继续推进",
            next_step="D2 强制状态服从：full_forced_state",
            actual_config_lines=[
                f"run：{_path_for_plan(run_dir.relative_to(ROOT))}",
                "固定题集 = outputs/run_20260420_014128/selected_questions.json",
                "forced states = mastered/partial/guessable/unreachable",
                "samples_per_state = 20",
            ],
            actual_conclusion_lines=[
                summary,
                f"mastered accuracy = {metrics['mastered_accuracy']:.4f}",
                f"partial accuracy = {metrics['partial_accuracy']:.4f}",
                f"guessable accuracy = {metrics['guessable_accuracy']:.4f}",
                f"unreachable accuracy = {metrics['unreachable_accuracy']:.4f}",
                f"strict_state_descending_item_count = {metrics['strict_state_descending_item_count']}",
            ],
        )
        _log(f"D1 completed: {run_dir}")
        return
    if stage == "D2":
        d1_stage_root = ROOT / (
            "outputs/root_cause/D1_simple_forced_state_smoke"
            if smoke
            else "outputs/root_cause/D1_simple_forced_state"
        )
        d1_run_dir = _latest_completed_run(d1_stage_root)
        if d1_run_dir is None:
            raise RuntimeError("D2 requires completed D1 run")
        run_dir = run_d2_full_forced_state(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("D2_full_forced_state_smoke" if smoke else "D2_full_forced_state"),
            samples_per_state=2 if smoke else 20,
            max_questions=4 if smoke else None,
            max_concurrency=4 if smoke else 16,
        )
        report_path = (
            SMOKE_REPORT_ROOT / "d2_full_forced_state_smoke.md"
            if smoke
            else ROOT_CAUSE_D2_REPORT_PATH
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        summary = write_d2_report(d1_run_dir=d1_run_dir, d2_run_dir=run_dir, report_path=report_path)
        if smoke:
            _log(f"D2 smoke completed: {run_dir}")
            return
        metrics = _read_json(run_dir / "metrics.json")
        update_root_cause_plan(
            stage_id="D2",
            output_dir=_path_for_plan(run_dir.relative_to(ROOT)),
            summary=summary,
            current_position="A1 已冻结；B1/B2/B3/C1/D1/D2 已完成；正式根因归因实验继续推进",
            next_step="E1 反事实敏感性测试",
            actual_config_lines=[
                f"run：{_path_for_plan(run_dir.relative_to(ROOT))}",
                f"D1 reference：{_path_for_plan(d1_run_dir.relative_to(ROOT))}",
                "固定题集 = outputs/run_20260420_014128/selected_questions.json",
                "forced states = mastered/partial/guessable/unreachable",
                "samples_per_state = 20",
            ],
            actual_conclusion_lines=[
                summary,
                f"mastered accuracy = {metrics['mastered_accuracy']:.4f}",
                f"partial accuracy = {metrics['partial_accuracy']:.4f}",
                f"guessable accuracy = {metrics['guessable_accuracy']:.4f}",
                f"unreachable accuracy = {metrics['unreachable_accuracy']:.4f}",
                f"remaining_violations = {metrics['remaining_violations']}",
                f"retry_count = {metrics['retry_count']}",
            ],
        )
        _log(f"D2 completed: {run_dir}")
        return
    if stage == "E1":
        run_dir = run_e1_counterfactual_sensitivity(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("E1_counterfactual_sensitivity_smoke" if smoke else "E1_counterfactual_sensitivity"),
            max_questions=4 if smoke else 20,
            repeats_per_side=1 if smoke else 5,
            max_concurrency=4 if smoke else 12,
        )
        report_path = (
            SMOKE_REPORT_ROOT / "e1_counterfactual_sensitivity_smoke.md"
            if smoke
            else ROOT_CAUSE_E1_REPORT_PATH
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        summary = write_e1_report(run_dir, report_path=report_path)
        if smoke:
            _log(f"E1 smoke completed: {run_dir}")
            return
        metrics = _read_json(run_dir / "metrics.json")
        update_root_cause_plan(
            stage_id="E1",
            output_dir=_path_for_plan(run_dir.relative_to(ROOT)),
            summary=summary,
            current_position="A1 已冻结；B1/B2/B3/C1/D1/D2/E1 已完成；正式根因归因实验继续推进",
            next_step="F1 稳定性测试",
            actual_config_lines=[
                f"run：{_path_for_plan(run_dir.relative_to(ROOT))}",
                "factors = math_subject_strength / efficacy / srl_fragility / engagement_style",
                "max_questions = 20",
                "repeats_per_side = 5",
            ],
            actual_conclusion_lines=[
                summary,
                f"mean_state_change_rate = {metrics['mean_state_change_rate']:.4f}",
                f"mean_answer_change_rate = {metrics['mean_answer_change_rate']:.4f}",
                f"mean_correctness_change_rate = {metrics['mean_correctness_change_rate']:.4f}",
            ],
        )
        _log(f"E1 completed: {run_dir}")
        return
    if stage == "F1":
        run_dir = run_f1_stability(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("F1_stability_smoke" if smoke else "F1_stability"),
            max_questions=4 if smoke else 20,
            max_personas=4 if smoke else 8,
            repeats=2 if smoke else 3,
            max_concurrency=4 if smoke else 12,
        )
        report_path = (
            SMOKE_REPORT_ROOT / "f1_stability_smoke.md"
            if smoke
            else ROOT_CAUSE_F1_REPORT_PATH
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        summary = write_f1_report(run_dir, report_path=report_path)
        if smoke:
            _log(f"F1 smoke completed: {run_dir}")
            return
        metrics = _read_json(run_dir / "metrics.json")
        update_root_cause_plan(
            stage_id="F1",
            output_dir=_path_for_plan(run_dir.relative_to(ROOT)),
            summary=summary,
            current_position="A1 已冻结；B1/B2/B3/C1/D1/D2/E1/F1 已完成；正式根因归因实验继续推进",
            next_step="G1 最终归因报告",
            actual_config_lines=[
                f"run：{_path_for_plan(run_dir.relative_to(ROOT))}",
                "personas = 8 stratified sampled real personas",
                "max_questions = 20",
                "repeats = 3",
                "method = state_step",
            ],
            actual_conclusion_lines=[
                summary,
                f"response_state_change_rate = {metrics['response_state_change_rate']:.4f}",
                f"predicted_answer_change_rate = {metrics['predicted_answer_change_rate']:.4f}",
                f"is_correct_change_rate = {metrics['is_correct_change_rate']:.4f}",
                f"fully_stable_rate = {metrics['fully_stable_rate']:.4f}",
            ],
        )
        _log(f"F1 completed: {run_dir}")
        return
    if stage == "G1":
        d1_run_dir = _latest_completed_run(ROOT / "outputs/root_cause/D1_simple_forced_state")
        d2_run_dir = _latest_completed_run(ROOT / "outputs/root_cause/D2_full_forced_state")
        e1_run_dir = _latest_completed_run(ROOT / "outputs/root_cause/E1_counterfactual_sensitivity")
        f1_run_dir = _latest_completed_run(ROOT / "outputs/root_cause/F1_stability")
        if None in {d1_run_dir, d2_run_dir, e1_run_dir, f1_run_dir}:
            raise RuntimeError("G1 requires completed D1/D2/E1/F1 runs")
        summary = write_g1_report(
            c1_run_dirs=C1_RUN_DIRS,
            d1_run_dir=d1_run_dir,
            d2_run_dir=d2_run_dir,
            e1_run_dir=e1_run_dir,
            f1_run_dir=f1_run_dir,
        )
        update_root_cause_plan(
            stage_id="G1",
            output_dir=_path_for_plan(ROOT_CAUSE_G1_REPORT_PATH.relative_to(ROOT)),
            summary=summary,
            current_position="A1 已冻结；B1/B2/B3/C1/D1/D2/E1/F1/G1 已完成；正式根因归因实验全部完成",
            next_step="全部正式根因归因实验已完成",
            actual_config_lines=[
                f"C1 report：{_path_for_plan(ROOT_CAUSE_C1_REPORT_PATH.relative_to(ROOT))}",
                f"D1 report：{_path_for_plan(ROOT_CAUSE_D1_REPORT_PATH.relative_to(ROOT))}",
                f"D2 report：{_path_for_plan(ROOT_CAUSE_D2_REPORT_PATH.relative_to(ROOT))}",
                f"E1 report：{_path_for_plan(ROOT_CAUSE_E1_REPORT_PATH.relative_to(ROOT))}",
                f"F1 report：{_path_for_plan(ROOT_CAUSE_F1_REPORT_PATH.relative_to(ROOT))}",
            ],
            actual_conclusion_lines=[
                summary,
                "B1/B2/B3 共同表明：persona 细节噪声大且没有被稳定读取",
                "C1/D2 共同表明：完整方法协议可能在吃掉本来就不强的状态差异",
                "D1/F1 共同表明：模型边界与稳定性问题仍然存在，但不是唯一主因",
            ],
        )
        _log("G1 completed: final report and plan updated")
        return
    raise ValueError(f"unsupported stage: {stage}")


def _cleanup_children(children: dict[str, subprocess.Popen[str]]) -> int:
    finished_labels = []
    for label, process in children.items():
        code = process.poll()
        if code is None:
            continue
        _log(f"child finished label={label} pid={process.pid} exit_code={code}")
        finished_labels.append(label)
    for label in finished_labels:
        del children[label]
    return len(finished_labels)


def _monitor_loop(
    poll_seconds: int,
    max_stale_seconds: int,
    stop_after: str = "",
) -> None:
    children: dict[str, subprocess.Popen[str]] = {}
    stage_sequence = ["C1", "D1", "D2", "E1", "F1", "G1"]
    if stop_after:
        stop_index = stage_sequence.index(stop_after)
        managed_sequence = stage_sequence[: stop_index + 1]
    else:
        managed_sequence = stage_sequence
    _log(
        "supervisor started "
        f"poll_seconds={poll_seconds} "
        f"max_stale_seconds={max_stale_seconds} "
        f"stop_after={stop_after or 'ALL'}"
    )
    while True:
        finished_children = _cleanup_children(children)
        launched_child = False
        external_inflight = False

        if stop_after and _is_stage_complete(stop_after):
            _log(f"stop-after target {stop_after} is complete; supervisor exiting")
            return

        if not _is_stage_complete("C1"):
            c1_done = all((run_dir / "metrics.json").exists() for run_dir in C1_RUN_DIRS.values())
            if c1_done:
                if "stage_C1" not in children:
                    children["stage_C1"] = _launch_child("stage_C1", [sys.executable, "root_cause_supervisor.py", "--run-stage", "C1"])
                    launched_child = True
            else:
                _resume_c1_if_stale(
                    label="state_single",
                    run_dir=C1_RUN_DIRS["state_single"],
                    method_variant="state_single",
                    children=children,
                    max_stale_seconds=max_stale_seconds,
                )
                _resume_c1_if_stale(
                    label="state_step",
                    run_dir=C1_RUN_DIRS["state_step"],
                    method_variant="state_step",
                    children=children,
                    max_stale_seconds=max_stale_seconds,
                )
        else:
            for stage in managed_sequence[1:]:
                if _is_stage_complete(stage):
                    continue
                child_label = f"stage_{stage}"
                if _is_stage_inflight(stage, max_stale_seconds=max_stale_seconds):
                    external_inflight = True
                    break
                if child_label not in children:
                    children[child_label] = _launch_child(
                        child_label,
                        [sys.executable, "root_cause_supervisor.py", "--run-stage", stage],
                    )
                    launched_child = True
                break
            else:
                if stop_after:
                    _log(f"managed stages through {stop_after} are complete; supervisor exiting")
                else:
                    _log("all root-cause stages are complete; supervisor exiting")
                return

        has_live_children = any(process.poll() is None for process in children.values())
        sleep_seconds = poll_seconds
        if finished_children or launched_child or has_live_children or external_inflight:
            sleep_seconds = min(poll_seconds, 30)
        time.sleep(sleep_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Root-cause experiment supervisor")
    parser.add_argument("--run-stage", choices=["C1", "D1", "D2", "E1", "F1", "G1"], default="")
    parser.add_argument("--stop-after", choices=["C1", "D1", "D2", "E1", "F1", "G1"], default="")
    parser.add_argument("--poll-seconds", type=int, default=1800)
    parser.add_argument("--max-stale-seconds", type=int, default=3600)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    if args.run_stage:
        _run_stage_worker(args.run_stage, smoke=args.smoke)
        return
    _monitor_loop(
        poll_seconds=max(1, args.poll_seconds),
        max_stale_seconds=max(1, args.max_stale_seconds),
        stop_after=args.stop_after,
    )


if __name__ == "__main__":
    main()
