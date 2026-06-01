from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "dynamic/eedi/configs/run_local.json"
DEFAULT_EVAL_ROOT = PROJECT_ROOT / "external/sim-student-eval"
DEFAULT_EVALUATIONS = "sim-text,sim-corr-errs"
DEFAULT_HF_CACHE_ROOT = PROJECT_ROOT / ".cache/huggingface"
OFFICIAL_METRIC_ORDER = [
    "acts-sim",
    "correctness-sim",
    "error-sim",
    "ks-sim",
    "cos-sim",
    "rouge",
    "tutor-ppl",
]
OFFICIAL_METRIC_LABELS = {
    "acts-sim": "Acts",
    "correctness-sim": "Correctness",
    "error-sim": "Errors",
    "ks-sim": "Knowledge Acquisition",
    "cos-sim": "Cosine Similarity",
    "rouge": "ROUGE-L",
    "tutor-ppl": "Tutor Response",
}


def _resolve_eedi_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("../"):
        return (PROJECT_ROOT / normalized[3:]).resolve()
    if normalized.startswith("dynamic/eedi/"):
        return (PROJECT_ROOT / path).resolve()
    if normalized.split("/", 1)[0] in {"configs", "outputs", "reports"}:
        return (PROJECT_ROOT / "dynamic/eedi" / path).resolve()
    project_candidate = (PROJECT_ROOT / path).resolve()
    if project_candidate.exists():
        return project_candidate
    return (PROJECT_ROOT / "dynamic/eedi" / path).resolve()


EVAL_GROUP_TO_REQUIREMENTS = {
    "sim-text": {
        "modules": ("evaluate", "sentence_transformers", "rouge_score", "absl"),
        "remote_modules": ("evaluate", "rouge_score", "absl", "openai"),
        "model_dirs": (),
    },
    "sim-acts": {
        "modules": (),
        "model_dirs": ("acts-8b",),
    },
    "sim-ks": {
        "modules": (),
        "model_dirs": ("llmkt-8b-ocean",),
        "needs_dialogue_kt": True,
    },
    "sim-corr-errs": {
        "modules": (),
        "model_dirs": (),
    },
    "tutor-ppl": {
        "modules": (),
        "model_dirs": ("eedi-tutor-sft-8b",),
    },
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run sim-student-eval with the existing qwen OpenAI-compatible endpoint."
    )
    parser.add_argument(
        "--input_file",
        type=str,
        help="Path to official_eval_input.csv exported from eedi outputs.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help="Config JSON containing llm_base_url / llm_model / llm_api_key or llm_api_key_env.",
    )
    parser.add_argument(
        "--eval_root",
        type=str,
        default=str(DEFAULT_EVAL_ROOT),
        help="Root of the sim-student-eval repo.",
    )
    parser.add_argument(
        "--evaluations",
        type=str,
        default=DEFAULT_EVALUATIONS,
        help=(
            "Comma-separated official eval names. "
            "Default is the no-training subset: sim-text,sim-corr-errs."
        ),
    )
    parser.add_argument(
        "--truncate",
        type=int,
        default=0,
        help="Optional truncate for official eval.",
    )
    parser.add_argument(
        "--llm_total_concurrency_budget",
        type=int,
        default=0,
        help=(
            "Total concurrency budget for the shared 9501/v1 endpoint. "
            "Judge requests use this value unless llm_judge_batch_size override is set."
        ),
    )
    parser.add_argument(
        "--llm_judge_batch_api",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use official batch api path for the LLM judge. Default false for generic OpenAI-compatible endpoints.",
    )
    parser.add_argument(
        "--llm_judge_reasoning_effort",
        type=str,
        default="low",
        help="Reasoning effort for official sim-corr-errs judge.",
    )
    parser.add_argument(
        "--llm_judge_temperature",
        type=float,
        default=0.0,
        help="Temperature for official sim-corr-errs judge.",
    )
    parser.add_argument(
        "--llm_judge_batch_size",
        type=int,
        default=0,
        help="Batch size / max parallel request count for official sim-corr-errs judge.",
    )
    parser.add_argument(
        "--embedding_api_base_url",
        type=str,
        default="",
        help=(
            "Optional OpenAI-compatible embeddings endpoint base URL. "
            "If set, sim-text will call remote embeddings instead of loading "
            "Qwen/Qwen3-Embedding-8B locally."
        ),
    )
    parser.add_argument(
        "--embedding_model",
        type=str,
        default="",
        help="Embedding model name exposed by the remote endpoint.",
    )
    parser.add_argument(
        "--embedding_api_key",
        type=str,
        default="",
        help="Optional API key for the remote embeddings endpoint.",
    )
    parser.add_argument(
        "--embedding_batch_size",
        type=int,
        default=16,
        help="Batch size for remote embedding requests.",
    )
    parser.add_argument(
        "--embedding_timeout_s",
        type=float,
        default=60.0,
        help="Client timeout in seconds for each remote embedding request.",
    )
    parser.add_argument(
        "--embedding_max_retries",
        type=int,
        default=3,
        help="Maximum retry count for transient remote embedding failures.",
    )
    parser.add_argument(
        "--embedding_retry_sleep_s",
        type=float,
        default=2.0,
        help="Sleep in seconds between remote embedding retries.",
    )
    parser.add_argument(
        "--preflight_only",
        action="store_true",
        help="Only validate dependencies for the requested official eval subset and exit.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    config = _load_json(_resolve_eedi_path(args.config))
    llm_api_key = _resolve_config_value(config, "llm_api_key")
    requested_total_budget = int(args.llm_total_concurrency_budget or 0)
    judge_override = int(args.llm_judge_batch_size or 0)
    if requested_total_budget < 0:
        raise ValueError("--llm_total_concurrency_budget must be >= 0")
    if judge_override < 0:
        raise ValueError("--llm_judge_batch_size must be >= 0")
    if not args.embedding_api_base_url.strip():
        args.embedding_api_base_url = str(
            config.get("embedding_api_base_url", "") or os.getenv("EMBEDDING_API_BASE_URL", "")
        )
    if not args.embedding_model.strip():
        args.embedding_model = str(
            config.get("embedding_model", "") or os.getenv("EMBEDDING_MODEL", "") or "Qwen/Qwen3-Embedding-8B"
        )
    if not args.embedding_api_key.strip():
        args.embedding_api_key = str(
            config.get("embedding_api_key", "") or os.getenv("EMBEDDING_API_KEY", "")
        )
    if args.embedding_batch_size <= 0:
        args.embedding_batch_size = int(config.get("embedding_batch_size", 16) or 16)
    if args.embedding_timeout_s <= 0:
        args.embedding_timeout_s = float(config.get("embedding_timeout_s", 60.0) or 60.0)
    if args.embedding_max_retries < 0:
        args.embedding_max_retries = int(config.get("embedding_max_retries", 3) or 0)
    if args.embedding_retry_sleep_s < 0:
        args.embedding_retry_sleep_s = float(config.get("embedding_retry_sleep_s", 2.0) or 0.0)
    if requested_total_budget <= 0:
        requested_total_budget = int(
            config.get("llm_total_concurrency_budget", 0)
            or config.get("llm_judge_batch_size", 0)
            or config.get("max_concurrency", 0)
            or 1
        )
    if judge_override > requested_total_budget:
        raise ValueError(
            "--llm_judge_batch_size cannot exceed --llm_total_concurrency_budget"
        )
    args.llm_total_concurrency_budget = requested_total_budget
    args.effective_llm_judge_batch_size = (
        judge_override if judge_override > 0 else requested_total_budget
    )
    eval_root = Path(args.eval_root)
    input_file = _resolve_eedi_path(args.input_file) if args.input_file else None
    evaluations = _parse_evaluations(args.evaluations)
    if not eval_root.exists():
        raise FileNotFoundError(f"eval_root not found: {eval_root}")
    _preflight_official_eval(
        eval_root=eval_root,
        evaluations=evaluations,
        embedding_api_base_url=args.embedding_api_base_url,
    )
    if args.preflight_only:
        print(
            "Official eval preflight passed for evaluations: "
            + ",".join(evaluations)
        )
        return
    if input_file is None:
        raise ValueError("--input_file is required unless --preflight_only is set")
    if not input_file.exists():
        raise FileNotFoundError(f"input_file not found: {input_file}")

    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = str(config["llm_base_url"])
    env["OPENAI_API_KEY"] = llm_api_key
    _configure_local_hf_caches(env)
    dialogue_kt_root = PROJECT_ROOT / "external/dialogue-kt"
    if dialogue_kt_root.exists():
        prior_pythonpath = str(env.get("PYTHONPATH", "")).strip()
        env["PYTHONPATH"] = (
            str(dialogue_kt_root)
            if not prior_pythonpath
            else str(dialogue_kt_root) + os.pathsep + prior_pythonpath
        )

    run_dir = input_file.parent
    eval_groups = _plan_eval_groups(
        evaluations=evaluations,
        use_remote_embeddings=bool(args.embedding_api_base_url.strip()),
    )
    _run_eval_groups(
        eval_root=eval_root,
        run_dir=run_dir,
        input_file=input_file,
        eval_groups=eval_groups,
        env=env,
        llm_judge_model=str(config["llm_model"]),
        llm_judge_reasoning_effort=args.llm_judge_reasoning_effort,
        llm_judge_temperature=args.llm_judge_temperature,
        llm_judge_batch_size=args.effective_llm_judge_batch_size,
        llm_judge_batch_api=args.llm_judge_batch_api,
        embedding_api_base_url=args.embedding_api_base_url.strip(),
        embedding_model=args.embedding_model.strip(),
        embedding_api_key=args.embedding_api_key.strip(),
        embedding_batch_size=args.embedding_batch_size,
        embedding_timeout_s=args.embedding_timeout_s,
        embedding_max_retries=args.embedding_max_retries,
        embedding_retry_sleep_s=args.embedding_retry_sleep_s,
        truncate=args.truncate,
    )
    _collect_and_copy_results(
        eval_root=eval_root,
        input_file=input_file,
        evaluations=evaluations,
        eval_groups=eval_groups,
    )


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("config must be a JSON object")
    required = ["llm_base_url", "llm_model"]
    missing = [key for key in required if not str(raw.get(key, "")).strip()]
    if not str(raw.get("llm_api_key", "") or "").strip() and not str(
        raw.get("llm_api_key_env", "") or ""
    ).strip():
        missing.append("llm_api_key or llm_api_key_env")
    if missing:
        raise ValueError(f"config missing required keys: {missing}")
    return raw


def _resolve_config_value(config: dict[str, object], key: str) -> str:
    env_name = str(config.get(f"{key}_env", "") or "").strip()
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if not env_value:
            raise ValueError(f"missing required environment variable for {key}: {env_name}")
        return env_value
    value = str(config.get(key, "") or "").strip()
    if not value:
        raise ValueError(f"missing required config value: {key}")
    return value


def _parse_evaluations(raw: str) -> list[str]:
    evaluations = [item.strip() for item in str(raw).split(",") if item.strip()]
    if not evaluations:
        raise ValueError("evaluations cannot be empty")
    unknown = sorted(set(evaluations) - set(EVAL_GROUP_TO_REQUIREMENTS))
    if unknown:
        raise ValueError(f"unknown official evaluations: {unknown}")
    return evaluations


def _preflight_official_eval(
    eval_root: Path,
    evaluations: list[str],
    embedding_api_base_url: str = "",
) -> None:
    saved_models_root = _get_saved_models_root(eval_root)
    missing_modules: set[str] = set()
    missing_model_dirs: set[str] = set()
    needs_dialogue_kt = False
    use_remote_embeddings = bool(str(embedding_api_base_url).strip())
    for evaluation in evaluations:
        requirements = EVAL_GROUP_TO_REQUIREMENTS[evaluation]
        required_modules = (
            requirements.get("remote_modules", ())
            if evaluation == "sim-text" and use_remote_embeddings
            else requirements.get("modules", ())
        )
        for module_name in required_modules:
            if not _module_available(module_name):
                missing_modules.add(module_name)
        for model_dir in requirements.get("model_dirs", ()):
            if not (saved_models_root / model_dir).exists():
                missing_model_dirs.add(model_dir)
        if requirements.get("needs_dialogue_kt"):
            needs_dialogue_kt = True
    problems: list[str] = []
    if missing_modules:
        problems.append(f"missing python modules: {sorted(missing_modules)}")
    if missing_model_dirs:
        problems.append(
            "missing official eval checkpoints under "
            f"{saved_models_root}: {sorted(missing_model_dirs)}"
        )
    if needs_dialogue_kt and not _dialogue_kt_available(eval_root):
        problems.append(
            "missing dialogue_kt package or repo symlink required by sim-ks"
        )
    if problems:
        raise RuntimeError(
            "official eval preflight failed:\n- " + "\n- ".join(problems)
        )


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _dialogue_kt_available(eval_root: Path) -> bool:
    return (
        _module_available("dialogue_kt")
        or (eval_root / "dialogue_kt").exists()
        or (PROJECT_ROOT / "external/dialogue-kt/dialogue_kt").exists()
    )


def _configure_local_hf_caches(env: dict[str, str]) -> None:
    hf_home = DEFAULT_HF_CACHE_ROOT
    hub_cache = hf_home / "hub"
    evaluate_cache = hf_home / "evaluate"
    sentence_transformers_cache = hf_home / "sentence_transformers"
    for path in (
        hf_home,
        hub_cache,
        evaluate_cache,
        sentence_transformers_cache,
    ):
        path.mkdir(parents=True, exist_ok=True)
    env["HF_HOME"] = str(hf_home)
    env["HUGGINGFACE_HUB_CACHE"] = str(hub_cache)
    env["HF_EVALUATE_CACHE"] = str(evaluate_cache)
    env["SENTENCE_TRANSFORMERS_HOME"] = str(sentence_transformers_cache)
    env["TRANSFORMERS_CACHE"] = str(hub_cache)


def _get_saved_models_root(eval_root: Path) -> Path:
    override = os.getenv("SIM_STUDENT_SAVED_MODELS_ROOT", "").strip()
    if override:
        return Path(override)
    return eval_root / "saved_models"


def _plan_eval_groups(
    evaluations: list[str],
    use_remote_embeddings: bool,
) -> list[list[str]]:
    if (
        use_remote_embeddings
        and "sim-text" in evaluations
        and "sim-corr-errs" in evaluations
    ):
        groups: list[list[str]] = [["sim-text"], ["sim-corr-errs"]]
        remaining = [
            evaluation
            for evaluation in evaluations
            if evaluation not in {"sim-text", "sim-corr-errs"}
        ]
        if remaining:
            groups.append(remaining)
        return groups
    return [evaluations]


def _build_eval_command(
    input_file: Path,
    evaluations: list[str],
    llm_judge_model: str,
    llm_judge_reasoning_effort: str,
    llm_judge_temperature: float,
    llm_judge_batch_size: int,
    llm_judge_batch_api: bool,
    embedding_api_base_url: str,
    embedding_model: str,
    embedding_api_key: str,
    embedding_batch_size: int,
    embedding_timeout_s: float,
    embedding_max_retries: int,
    embedding_retry_sleep_s: float,
    truncate: int,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "sim_student.eval",
        "--input_file",
        str(input_file.resolve()),
        "--evaluations",
        ",".join(evaluations),
        "--llm_judge_model",
        llm_judge_model,
        "--llm_judge_reasoning_effort",
        llm_judge_reasoning_effort,
        "--llm_judge_temperature",
        str(llm_judge_temperature),
        "--llm_judge_batch_size",
        str(llm_judge_batch_size),
    ]
    if embedding_api_base_url:
        cmd.extend(["--embedding_api_base_url", embedding_api_base_url])
    if embedding_model:
        cmd.extend(["--embedding_model", embedding_model])
    if embedding_api_key:
        cmd.extend(["--embedding_api_key", embedding_api_key])
    if embedding_batch_size > 0:
        cmd.extend(["--embedding_batch_size", str(embedding_batch_size)])
    if embedding_timeout_s > 0:
        cmd.extend(["--embedding_timeout_s", str(embedding_timeout_s)])
    if embedding_max_retries >= 0:
        cmd.extend(["--embedding_max_retries", str(embedding_max_retries)])
    if embedding_retry_sleep_s >= 0:
        cmd.extend(["--embedding_retry_sleep_s", str(embedding_retry_sleep_s)])
    if truncate:
        cmd.extend(["--truncate", str(truncate)])
    cmd.append(
        "--llm_judge_batch_api" if llm_judge_batch_api else "--no-llm_judge_batch_api"
    )
    return cmd


def _run_eval_groups(
    eval_root: Path,
    run_dir: Path,
    input_file: Path,
    eval_groups: list[list[str]],
    env: dict[str, str],
    llm_judge_model: str,
    llm_judge_reasoning_effort: str,
    llm_judge_temperature: float,
    llm_judge_batch_size: int,
    llm_judge_batch_api: bool,
    embedding_api_base_url: str,
    embedding_model: str,
    embedding_api_key: str,
    embedding_batch_size: int,
    embedding_timeout_s: float,
    embedding_max_retries: int,
    embedding_retry_sleep_s: float,
    truncate: int,
) -> None:
    if len(eval_groups) == 1:
        cmd = _build_eval_command(
            input_file=input_file,
            evaluations=eval_groups[0],
            llm_judge_model=llm_judge_model,
            llm_judge_reasoning_effort=llm_judge_reasoning_effort,
            llm_judge_temperature=llm_judge_temperature,
            llm_judge_batch_size=llm_judge_batch_size,
            llm_judge_batch_api=llm_judge_batch_api,
            embedding_api_base_url=embedding_api_base_url,
            embedding_model=embedding_model,
            embedding_api_key=embedding_api_key,
            embedding_batch_size=embedding_batch_size,
            embedding_timeout_s=embedding_timeout_s,
            embedding_max_retries=embedding_max_retries,
            embedding_retry_sleep_s=embedding_retry_sleep_s,
            truncate=truncate,
        )
        print("Running:", " ".join(cmd))
        subprocess.run(cmd, cwd=eval_root, env=env, check=True)
        return

    print(
        "Running independent official eval groups in parallel: "
        + " | ".join(",".join(group) for group in eval_groups[:2])
    )
    processes: list[tuple[subprocess.Popen[str], list[str], Path, Path]] = []
    try:
        for group in eval_groups[:2]:
            group_tag = _sanitize_group_tag(group)
            stdout_path = run_dir / f"official_eval_subrun_{group_tag}_stdout.log"
            stderr_path = run_dir / f"official_eval_subrun_{group_tag}_stderr.log"
            cmd = _build_eval_command(
                input_file=input_file,
                evaluations=group,
                llm_judge_model=llm_judge_model,
                llm_judge_reasoning_effort=llm_judge_reasoning_effort,
                llm_judge_temperature=llm_judge_temperature,
                llm_judge_batch_size=llm_judge_batch_size,
                llm_judge_batch_api=llm_judge_batch_api,
                embedding_api_base_url=embedding_api_base_url,
                embedding_model=embedding_model,
                embedding_api_key=embedding_api_key,
                embedding_batch_size=embedding_batch_size,
                embedding_timeout_s=embedding_timeout_s,
                embedding_max_retries=embedding_max_retries,
                embedding_retry_sleep_s=embedding_retry_sleep_s,
                truncate=truncate,
            )
            print("Launching:", " ".join(cmd))
            stdout_handle = stdout_path.open("w", encoding="utf-8")
            stderr_handle = stderr_path.open("w", encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=eval_root,
                    env=env,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                )
            except Exception:
                stdout_handle.close()
                stderr_handle.close()
                raise
            processes.append((proc, group, stdout_path, stderr_path))
            stdout_handle.close()
            stderr_handle.close()

        failures: list[str] = []
        for proc, group, stdout_path, stderr_path in processes:
            returncode = proc.wait()
            if returncode != 0:
                failures.append(
                    f"group={group} returncode={returncode} "
                    f"stdout={stdout_path} stderr={stderr_path}"
                )
        if failures:
            raise RuntimeError(
                "parallel official eval subruns failed:\n- " + "\n- ".join(failures)
            )

        for group in eval_groups[2:]:
            cmd = _build_eval_command(
                input_file=input_file,
                evaluations=group,
                llm_judge_model=llm_judge_model,
                llm_judge_reasoning_effort=llm_judge_reasoning_effort,
                llm_judge_temperature=llm_judge_temperature,
                llm_judge_batch_size=llm_judge_batch_size,
                llm_judge_batch_api=llm_judge_batch_api,
                embedding_api_base_url=embedding_api_base_url,
                embedding_model=embedding_model,
                embedding_api_key=embedding_api_key,
                embedding_batch_size=embedding_batch_size,
                embedding_timeout_s=embedding_timeout_s,
                embedding_max_retries=embedding_max_retries,
                embedding_retry_sleep_s=embedding_retry_sleep_s,
                truncate=truncate,
            )
            print("Running trailing eval group:", " ".join(cmd))
            subprocess.run(cmd, cwd=eval_root, env=env, check=True)
    finally:
        for proc, _, _, _ in processes:
            if proc.poll() is None:
                proc.kill()


def _sanitize_group_tag(evaluations: list[str]) -> str:
    joined = "__".join(evaluations)
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", joined).strip("_")
    return sanitized or "group"


def _collect_and_copy_results(
    eval_root: Path,
    input_file: Path,
    evaluations: list[str],
    eval_groups: list[list[str]],
) -> None:
    external_results_dir = eval_root / "results"
    run_dir = input_file.parent
    group_result_paths: list[tuple[list[str], Path, Path]] = []
    for group in eval_groups:
        group_suffix = _build_result_suffix(input_file, group)
        src_csv = external_results_dir / f"outputs_{group_suffix}.csv"
        src_metrics = external_results_dir / f"metrics_{group_suffix}.txt"
        if not src_csv.exists():
            raise FileNotFoundError(f"official eval output csv not found: {src_csv}")
        if not src_metrics.exists():
            raise FileNotFoundError(f"official eval metrics txt not found: {src_metrics}")
        dst_group_csv = run_dir / f"official_eval_outputs_{group_suffix}.csv"
        dst_group_metrics = run_dir / f"official_eval_metrics_{group_suffix}.txt"
        shutil.copy2(src_csv, dst_group_csv)
        shutil.copy2(src_metrics, dst_group_metrics)
        group_result_paths.append((group, dst_group_csv, dst_group_metrics))

    full_suffix = _build_result_suffix(input_file, evaluations)
    if len(group_result_paths) == 1:
        _, dst_csv, dst_metrics = group_result_paths[0]
        if dst_csv.name != f"official_eval_outputs_{full_suffix}.csv":
            final_csv = run_dir / f"official_eval_outputs_{full_suffix}.csv"
            final_metrics = run_dir / f"official_eval_metrics_{full_suffix}.txt"
            shutil.copy2(dst_csv, final_csv)
            shutil.copy2(dst_metrics, final_metrics)
            dst_csv = final_csv
            dst_metrics = final_metrics
    else:
        dst_csv = run_dir / f"official_eval_outputs_{full_suffix}.csv"
        dst_metrics = run_dir / f"official_eval_metrics_{full_suffix}.txt"
        _merge_group_result_csvs(
            group_csvs=[path for _, path, _ in group_result_paths],
            merged_csv_path=dst_csv,
        )
        summary = _build_official_eval_summary(
            results_csv=dst_csv,
            evaluations=evaluations,
            metrics_txt=dst_metrics,
            suffix=full_suffix,
        )
        _write_metrics_text(summary, dst_metrics)
        _write_summary_files(run_dir=run_dir, summary=summary)
        return

    summary = _build_official_eval_summary(
        results_csv=dst_csv,
        evaluations=evaluations,
        metrics_txt=dst_metrics,
        suffix=full_suffix,
    )
    _write_summary_files(run_dir=run_dir, summary=summary)


def _build_result_suffix(input_file: Path, evaluations: list[str]) -> str:
    input_stem = input_file.stem
    parent_stem = input_file.parent.name.strip() if input_file.parent.name.strip() else "root"
    return f"{parent_stem}_{input_stem}_eval_{','.join(evaluations)}"


def _build_official_eval_summary(
    results_csv: Path,
    evaluations: list[str],
    metrics_txt: Path,
    suffix: str,
) -> dict[str, object]:
    rows = list(csv.DictReader(results_csv.open("r", encoding="utf-8-sig", newline="")))
    metric_stats: dict[str, dict[str, object]] = {}
    for metric_name in OFFICIAL_METRIC_ORDER:
        values = _extract_metric_values(rows, metric_name)
        if not values:
            continue
        mean = sum(values) / len(values)
        std = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
        metric_stats[metric_name] = {
            "label": OFFICIAL_METRIC_LABELS[metric_name],
            "mean": mean,
            "std": std,
            "count": len(values),
        }
    return {
        "evaluations": evaluations,
        "suffix": suffix,
        "results_csv": str(results_csv),
        "metrics_txt": str(metrics_txt),
        "n_rows": len(rows),
        "metrics": metric_stats,
    }


def _merge_group_result_csvs(
    group_csvs: list[Path],
    merged_csv_path: Path,
) -> None:
    if not group_csvs:
        raise ValueError("group_csvs cannot be empty")
    key_columns = ["key", "prompt", "dialogue_idx", "turn_idx", "gt_turn", "pred_turn"]
    merged_rows: dict[tuple[str, ...], dict[str, str]] = {}
    merged_fieldnames: list[str] = []
    for csv_idx, csv_path in enumerate(group_csvs):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            missing_key_columns = [col for col in key_columns if col not in fieldnames]
            if missing_key_columns:
                raise ValueError(
                    f"{csv_path} missing merge key columns: {missing_key_columns}"
                )
            extra_columns = [col for col in fieldnames if col not in key_columns]
            if csv_idx == 0:
                merged_fieldnames = key_columns + extra_columns
                for row in reader:
                    row_key = tuple(str(row[col]) for col in key_columns)
                    if row_key in merged_rows:
                        raise ValueError(f"duplicate row key in {csv_path}: {row_key}")
                    merged_rows[row_key] = {col: str(row.get(col, "")) for col in key_columns + extra_columns}
            else:
                for col in extra_columns:
                    if col in merged_fieldnames:
                        raise ValueError(f"duplicate metric column during merge: {col}")
                    merged_fieldnames.append(col)
                matched_keys: set[tuple[str, ...]] = set()
                for row in reader:
                    row_key = tuple(str(row[col]) for col in key_columns)
                    if row_key not in merged_rows:
                        raise ValueError(f"row key from {csv_path} not found in base csv: {row_key}")
                    matched_keys.add(row_key)
                    merged_row = merged_rows[row_key]
                    for col in key_columns:
                        if merged_row[col] != str(row.get(col, "")):
                            raise ValueError(
                                f"row mismatch while merging {csv_path} on key {row_key}"
                            )
                    for col in extra_columns:
                        merged_row[col] = str(row.get(col, ""))
                if len(matched_keys) != len(merged_rows):
                    raise ValueError(
                        f"{csv_path} row count mismatch during merge: "
                        f"expected {len(merged_rows)}, got {len(matched_keys)}"
                    )

    ordered_keys = sorted(
        merged_rows,
        key=lambda row_key: (
            _safe_int(row_key[2]),
            _safe_int(row_key[3]),
            row_key[0],
        ),
    )
    with merged_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=merged_fieldnames)
        writer.writeheader()
        for row_key in ordered_keys:
            row = merged_rows[row_key]
            writer.writerow({col: row.get(col, "") for col in merged_fieldnames})


def _write_metrics_text(summary: dict[str, object], metrics_txt_path: Path) -> None:
    lines: list[str] = []
    metrics = summary["metrics"]
    for metric_name in OFFICIAL_METRIC_ORDER:
        metric = metrics.get(metric_name)
        if metric is None:
            continue
        lines.append(
            f"{metric_name}: {metric['mean']:.4f} +/- {metric['std']:.4f}"
        )
    metrics_txt_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _safe_int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        return 0


def _extract_metric_values(rows: list[dict[str, str]], metric_name: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        raw = str(row.get(metric_name, "") or "").strip()
        if not raw:
            continue
        if raw.lower() == "nan":
            continue
        values.append(float(raw))
    return values


def _render_summary_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Official Eval Summary",
        "",
        f"- Evaluations: {', '.join(summary['evaluations'])}",
        f"- Rows: {summary['n_rows']}",
        "",
        "| Metric | Mean | Std | Count |",
        "| --- | ---: | ---: | ---: |",
    ]
    metrics = summary["metrics"]
    for metric_name in OFFICIAL_METRIC_ORDER:
        metric = metrics.get(metric_name)
        if metric is None:
            continue
        lines.append(
            f"| {metric['label']} | {metric['mean']:.4f} | {metric['std']:.4f} | {metric['count']} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def _write_summary_files(run_dir: Path, summary: dict[str, object]) -> None:
    summary_json_path = run_dir / "official_eval_summary.json"
    summary_md_path = run_dir / "official_eval_summary.md"
    with summary_json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    summary_md_path.write_text(_render_summary_markdown(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
