from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must be object: {path}")
    return payload


def _fmt(value: object) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _metric(metrics: dict[str, object], path: list[str]) -> object:
    current: object = metrics
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load_run(name: str, run_dir: str) -> dict[str, object]:
    path = Path(run_dir)
    metrics = _read_json(path / "metrics.json")
    common = metrics.get("common_test_metrics")
    if not isinstance(common, dict):
        raise ValueError(f"run missing common_test_metrics: {path}")
    return {
        "name": name,
        "run_dir": str(path),
        "metrics": metrics,
        "common": common,
    }


def _main_table(runs: list[dict[str, object]]) -> str:
    headers = [
        "run",
        "acc",
        "item_P",
        "item_S",
        "student_P",
        "student_S",
        "overall_consistency",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for run in runs:
        common = run["common"]
        metrics = run["metrics"]
        assert isinstance(common, dict)
        assert isinstance(metrics, dict)
        row = [
            run["name"],
            common.get("overall_accuracy"),
            common.get("item_accuracy_pearson"),
            common.get("item_accuracy_spearman"),
            common.get("student_accuracy_pearson"),
            common.get("student_accuracy_spearman"),
            common.get("consistency_mean"),
        ]
        lines.append("| " + " | ".join(_fmt(item) for item in row) + " |")
    return "\n".join(lines)


def _level_consistency_table(runs: list[dict[str, object]]) -> str:
    headers = ["run", "poor", "low", "medium", "high"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for run in runs:
        common = run["common"]
        assert isinstance(common, dict)
        per_level = common.get("per_level", {})
        if not isinstance(per_level, dict):
            per_level = {}
        row = [
            run["name"],
            _metric(per_level, ["poor", "consistency"]),
            _metric(per_level, ["low", "consistency"]),
            _metric(per_level, ["medium", "consistency"]),
            _metric(per_level, ["high", "consistency"]),
        ]
        lines.append("| " + " | ".join(_fmt(item) for item in row) + " |")
    return "\n".join(lines)


def _predicted_score_table(runs: list[dict[str, object]]) -> str:
    headers = ["run", "pred_accuracy", "pred_score_96"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for run in runs:
        common = run["common"]
        assert isinstance(common, dict)
        pred_accuracy = common.get("overall_accuracy")
        pred_score = float(pred_accuracy) * 96 if pred_accuracy is not None else None
        lines.append(
            "| " + " | ".join(_fmt(item) for item in [run["name"], pred_accuracy, pred_score]) + " |"
        )
    return "\n".join(lines)


def _predicted_level_score_table(runs: list[dict[str, object]]) -> str:
    headers = [
        "run",
        "poor_acc",
        "poor_score",
        "low_acc",
        "low_score",
        "medium_acc",
        "medium_score",
        "high_acc",
        "high_score",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for run in runs:
        common = run["common"]
        assert isinstance(common, dict)
        per_level = common.get("per_level", {})
        if not isinstance(per_level, dict):
            per_level = {}
        row: list[object] = [run["name"]]
        for level in ("poor", "low", "medium", "high"):
            acc = _metric(per_level, [level, "predicted_accuracy"])
            score = float(acc) * 96 if acc is not None else None
            row.extend([acc, score])
        lines.append("| " + " | ".join(_fmt(item) for item in row) + " |")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize XES common-test harness runs.")
    parser.add_argument("--strong_hachimi_run_dir", required=True)
    parser.add_argument("--strong_history_only_run_dir", required=True)
    parser.add_argument("--weak_1_7b_run_dir", required=True)
    parser.add_argument("--weak_3b_run_dir", required=True)
    parser.add_argument("--weak_7b_run_dir", required=True)
    parser.add_argument("--output_report", required=True)
    parser.add_argument("--case_dump_path", default="")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    runs = [
        _load_run("strong+hachimi", args.strong_hachimi_run_dir),
        _load_run("strong history only", args.strong_history_only_run_dir),
        _load_run("weak 1.7b", args.weak_1_7b_run_dir),
        _load_run("weak 3b", args.weak_3b_run_dir),
        _load_run("weak 7b", args.weak_7b_run_dir),
    ]
    first_metrics = runs[0]["metrics"]
    assert isinstance(first_metrics, dict)
    run_config = first_metrics.get("run_config", {})
    if not isinstance(run_config, dict):
        run_config = {}
    real_overall_accuracy = _metric(first_metrics, ["common_test_metrics", "real_overall_accuracy"])
    if real_overall_accuracy is not None:
        real_overall_accuracy = float(real_overall_accuracy)
    real_per_level = {
        level: _metric(first_metrics, ["common_test_metrics", "per_level", level, "real_accuracy"])
        for level in ("poor", "low", "medium", "high")
    }

    lines: list[str] = [
        "# XES common-test harness report",
        "",
        "## 实验设置",
        "",
        "- 样本：60名学生，poor/low/medium/high 各15名。",
        "- 测试：96道共同测试题，所有指标只在这96题上计算。",
        "- 历史：每名学生30道非测试题历史，按个人时间序列三段均匀取样。",
        "- 固定样本配置：`" + str(run_config.get("fixed_cohort_path", "NA")) + "`",
        "",
        "## 核心指标",
        "",
        _main_table(runs),
        "",
        "## 四档 Consistency",
        "",
        _level_consistency_table(runs),
        "",
        "## 指标说明",
        "",
        "- `acc`：模型实际做对题数 / 总题数，也就是整体预测正确率。",
        "- `item_P / item_S`：题目正确率与真实题目正确率的 Pearson / Spearman。",
        "- `student_P / student_S`：学生个人正确率与真实学生个人正确率的 Pearson / Spearman。",
        "- `overall_consistency`：先对每个学生算逐题对错一致率，再对全部学生取平均。",
        "",
        "## 五组模型预测分数",
        "",
        _predicted_score_table(runs),
        "",
        "## 五组模型四档预测分数",
        "",
        _predicted_level_score_table(runs),
        "",
        "## 真实学生分数参考",
        "",
        "- 共同测试总题数：96。",
        "- 真实学生总体平均正确率：`" + _fmt(real_overall_accuracy) + "`",
        "- 真实学生总体平均分：`" + _fmt(real_overall_accuracy * 96 if real_overall_accuracy is not None else None) + " / 96`",
        "",
        "| 档次 | 真实正确率 | 真实平均分(96题制) |",
        "|---|---|---|",
        "| poor | "
        + _fmt(real_per_level["poor"])
        + " | "
        + _fmt(float(real_per_level["poor"]) * 96 if real_per_level["poor"] is not None else None)
        + " |",
        "| low | "
        + _fmt(real_per_level["low"])
        + " | "
        + _fmt(float(real_per_level["low"]) * 96 if real_per_level["low"] is not None else None)
        + " |",
        "| medium | "
        + _fmt(real_per_level["medium"])
        + " | "
        + _fmt(float(real_per_level["medium"]) * 96 if real_per_level["medium"] is not None else None)
        + " |",
        "| high | "
        + _fmt(real_per_level["high"])
        + " | "
        + _fmt(float(real_per_level["high"]) * 96 if real_per_level["high"] is not None else None)
        + " |",
        "",
        "## 输出位置",
        "",
        *[f"- {run['name']}: `{run['run_dir']}`" for run in runs],
    ]
    if args.case_dump_path:
        lines.append(f"- case dump: `{args.case_dump_path}`")
    lines.append("")

    output_path = Path(args.output_report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
