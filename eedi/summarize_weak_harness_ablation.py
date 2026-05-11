from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="汇总多个 EEDI run 目录的 detached eval 与运行层指标，输出 ablation 对比。"
    )
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="单个 run，格式为 label=path；如果不写 label，则默认用目录名。",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="EEDI 弱模型 harness ablation 对比",
        help="markdown 标题。",
    )
    parser.add_argument(
        "--output_md",
        type=str,
        default="",
        help="可选，输出 markdown 文件路径。",
    )
    parser.add_argument(
        "--output_json",
        type=str,
        default="",
        help="可选，输出 json 文件路径。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    runs = [load_run(spec) for spec in args.run]
    payload = {
        "title": args.title,
        "runs": runs,
        "baseline_label": runs[0]["label"] if runs else None,
    }
    markdown = render_markdown(args.title, runs)

    if args.output_md.strip():
        output_md = Path(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(markdown, encoding="utf-8")

    if args.output_json.strip():
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(markdown)


def load_run(spec: str) -> dict[str, Any]:
    label, run_dir = parse_run_spec(spec)
    detached_summary_path = resolve_detached_summary_path(run_dir)
    metrics_path = run_dir / "metrics.json"

    detached_summary = load_json(detached_summary_path)
    metrics = load_json(metrics_path)

    failure_bundle = load_failures(run_dir)

    correctness = as_dict(detached_summary.get("correctness"))
    text_similarity = as_dict(detached_summary.get("text_similarity"))
    same_error = as_dict(detached_summary.get("same_error"))
    pred_distribution = as_dict(correctness.get("pred_distribution"))

    n_records = maybe_int(metrics.get("n_records"))
    n_failures = (
        maybe_int(metrics.get("n_failures"))
        if metrics.get("n_failures") is not None
        else failure_bundle["n_failures"]
    )
    failure_rate = None
    if n_records not in (None, 0) and n_failures is not None:
        failure_rate = n_failures / n_records

    return {
        "label": label,
        "run_dir": str(run_dir),
        "detached_summary_path": str(detached_summary_path),
        "metrics_path": str(metrics_path),
        "failure_source_path": failure_bundle["source_path"],
        "n_rows": maybe_int(detached_summary.get("n_rows")),
        "correctness_match_rate": maybe_float(correctness.get("match_rate")),
        "correctness_match_count": maybe_int(correctness.get("match_count")),
        "correctness_eligible_rows": maybe_int(correctness.get("n_eligible_rows")),
        "pred_na": maybe_int(pred_distribution.get("na")),
        "pred_correct": maybe_int(pred_distribution.get("correct")),
        "pred_incorrect": maybe_int(pred_distribution.get("incorrect")),
        "same_error_rate": maybe_float(same_error.get("same_error_rate")),
        "error_realization_rate": maybe_float(same_error.get("error_realization_rate")),
        "cosine_similarity_mean": maybe_float(text_similarity.get("cosine_similarity_mean")),
        "rougeL_mean": maybe_float(text_similarity.get("rougeL_mean")),
        "n_records": n_records,
        "n_failures": n_failures,
        "failure_rate": failure_rate,
        "retries": maybe_int(metrics.get("retries")),
        "remaining_violations": maybe_int(metrics.get("remaining_violations")),
        "response_space_distribution": as_dict(metrics.get("response_space_distribution")),
        "target_engagement_distribution": as_dict(metrics.get("target_engagement_distribution")),
        "response_commitment_distribution": as_dict(
            metrics.get("response_commitment_distribution")
        ),
        "response_maturity_distribution": as_dict(
            metrics.get("response_maturity_distribution")
        ),
        "violation_distribution": as_dict(metrics.get("violation_distribution")),
        "top_failure_types": failure_bundle["top_failure_types"],
        "top_failure_messages": failure_bundle["top_failure_messages"],
    }


def parse_run_spec(spec: str) -> tuple[str, Path]:
    raw = spec.strip()
    if not raw:
        raise ValueError("empty --run spec")
    if "=" in raw:
        label, path_text = raw.split("=", 1)
        label = label.strip()
        path_text = path_text.strip()
    else:
        path_text = raw
        label = Path(path_text).name
    run_dir = Path(path_text).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"run dir not found: {run_dir}")
    if not run_dir.is_dir():
        raise NotADirectoryError(f"run path is not a directory: {run_dir}")
    if not label:
        raise ValueError(f"invalid label in --run: {spec}")
    return label, run_dir


def resolve_detached_summary_path(run_dir: Path) -> Path:
    preferred = [
        run_dir / "detached_eval_1000" / "detached_eval_summary.json",
        run_dir / "detached_eval" / "detached_eval_summary.json",
        run_dir / "detached_eval_full" / "detached_eval_summary.json",
        run_dir / "detached_eval_smoke_5" / "detached_eval_summary.json",
    ]
    for path in preferred:
        if path.exists():
            return path

    candidates = sorted(run_dir.rglob("detached_eval_summary.json"))
    if not candidates:
        raise FileNotFoundError(f"detached_eval_summary.json not found under: {run_dir}")
    if len(candidates) > 1:
        joined = ", ".join(str(path) for path in candidates)
        raise ValueError(
            "multiple detached_eval_summary.json found under "
            f"{run_dir}; please narrow the run dir. candidates: {joined}"
        )
    return candidates[0]


def load_failures(run_dir: Path) -> dict[str, Any]:
    task_failures_path = run_dir / "task_failures.jsonl"
    if task_failures_path.exists():
        return summarize_failure_jsonl(task_failures_path)

    summary_candidates = [
        run_dir / "task_failures_summary.json",
        run_dir / "task_failures_summary_firstpass_100c.json",
    ]
    for summary_path in summary_candidates:
        if summary_path.exists():
            payload = load_json(summary_path)
            n_failures = maybe_int(payload.get("n_failures"))
            if n_failures is None:
                n_failures = maybe_int(payload.get("n_failed_tasks"))
            return {
                "source_path": str(summary_path),
                "n_failures": n_failures,
                "top_failure_types": dict_items_to_ranked_list(as_dict(payload.get("error_type_distribution"))),
                "top_failure_messages": [],
            }

    return {
        "source_path": "",
        "n_failures": maybe_int(None),
        "top_failure_types": [],
        "top_failure_messages": [],
    }


def summarize_failure_jsonl(path: Path) -> dict[str, Any]:
    type_counter: Counter[str] = Counter()
    message_counter: Counter[str] = Counter()
    n_failures = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            row = json.loads(raw)
            n_failures += 1
            error_type = str(row.get("error_type") or "UNKNOWN")
            error_message = str(row.get("error_message") or "").strip()
            type_counter[error_type] += 1
            if error_message:
                message_counter[normalize_message(error_message)] += 1

    return {
        "source_path": str(path),
        "n_failures": n_failures,
        "top_failure_types": counter_to_ranked_list(type_counter, limit=5),
        "top_failure_messages": counter_to_ranked_list(message_counter, limit=5),
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing file: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"json root must be object: {path}")
    return raw


def render_markdown(title: str, runs: list[dict[str, Any]]) -> str:
    if not runs:
        raise ValueError("no runs to render")

    baseline = runs[0]
    lines: list[str] = [f"# {title}", ""]
    lines.append("## 1. 核心指标对比")
    lines.append(
        "| run | n_rows | correctness | same_error | error_realization | cosine | rougeL | pred_na | n_records | n_failures | failure_rate |"
    )
    lines.append(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    for run in runs:
        lines.append(
            "| "
            + " | ".join(
                [
                    run["label"],
                    fmt_int(run["n_rows"]),
                    fmt_pct(run["correctness_match_rate"]),
                    fmt_pct(run["same_error_rate"]),
                    fmt_pct(run["error_realization_rate"]),
                    fmt_float(run["cosine_similarity_mean"]),
                    fmt_float(run["rougeL_mean"]),
                    fmt_int(run["pred_na"]),
                    fmt_int(run["n_records"]),
                    fmt_int(run["n_failures"]),
                    fmt_pct(run["failure_rate"]),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append(f"基线默认取第一行：`{baseline['label']}`。")
    lines.append("")
    lines.append("## 2. 相对基线增减")
    lines.append("| run | Δcorrectness | Δsame_error | Δerror_realization | Δpred_na | Δfailure_rate |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for run in runs[1:]:
        lines.append(
            "| "
            + " | ".join(
                [
                    run["label"],
                    fmt_signed_pct(delta(run["correctness_match_rate"], baseline["correctness_match_rate"])),
                    fmt_signed_pct(delta(run["same_error_rate"], baseline["same_error_rate"])),
                    fmt_signed_pct(
                        delta(
                            run["error_realization_rate"],
                            baseline["error_realization_rate"],
                        )
                    ),
                    fmt_signed_int(delta(run["pred_na"], baseline["pred_na"])),
                    fmt_signed_pct(delta(run["failure_rate"], baseline["failure_rate"])),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## 3. 运行层分布")
    lines.append("| run | response_space | target_engagement | response_commitment | response_maturity | violations |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for run in runs:
        lines.append(
            "| "
            + " | ".join(
                [
                    run["label"],
                    format_distribution(run["response_space_distribution"]),
                    format_distribution(run["target_engagement_distribution"]),
                    format_distribution(run["response_commitment_distribution"]),
                    format_distribution(run["response_maturity_distribution"]),
                    format_distribution(run["violation_distribution"]),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## 4. 失败概览")
    for run in runs:
        lines.append(f"### {run['label']}")
        lines.append(f"- run目录：`{run['run_dir']}`")
        lines.append(f"- detached eval：`{run['detached_summary_path']}`")
        lines.append(f"- 运行层指标：`{run['metrics_path']}`")
        if run["failure_source_path"]:
            lines.append(f"- 失败来源：`{run['failure_source_path']}`")
        else:
            lines.append("- 失败来源：无单条失败文件")
        lines.append(f"- top failure types：{format_ranked_items(run['top_failure_types'])}")
        lines.append(f"- top failure messages：{format_ranked_items(run['top_failure_messages'])}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def normalize_message(message: str) -> str:
    message = " ".join(message.split())
    if len(message) > 160:
        return message[:157] + "..."
    return message


def counter_to_ranked_list(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in counter.most_common(limit)
    ]


def dict_items_to_ranked_list(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for key, value in mapping.items():
        count = maybe_int(value)
        ranked.append({"name": str(key), "count": count if count is not None else 0})
    ranked.sort(key=lambda item: item["count"], reverse=True)
    return ranked[:5]


def format_ranked_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "无"
    return "; ".join(f"{item['name']} x{item['count']}" for item in items)


def format_distribution(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "无"
    parts = [f"{key}:{value}" for key, value in sorted(mapping.items(), key=lambda item: str(item[0]))]
    return "<br>".join(parts)


def maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def delta(value: float | int | None, baseline: float | int | None) -> float | int | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.4f}"


def fmt_signed_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.4f}"


def fmt_float(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.4f}"


def fmt_int(value: int | None) -> str:
    if value is None:
        return "NA"
    return str(value)


def fmt_signed_int(value: int | float | None) -> str:
    if value is None:
        return "NA"
    return f"{int(value):+d}"


if __name__ == "__main__":
    main()
