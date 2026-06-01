from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.llm_client import LLMConfig
from src.runtime_paths import EEDI_OUTPUTS_DIR, PROJECT_ROOT, resolve_eedi_path
from src.theory_error_eval import (
    _gold_turn_is_officially_incorrect,
    build_theory_error_summary,
    evaluate_theory_error_rows,
    load_theory_error_rows,
    write_theory_error_outputs,
)


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "dynamic/eedi/configs/run_local.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run theory-grounded EEDI error evaluation with LLM-as-a-judge."
    )
    parser.add_argument("--input_file", type=str, required=True)
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output_dir", type=str, default="")
    parser.add_argument("--truncate", type=int, default=0)
    parser.add_argument("--max_concurrency", type=int, default=0)
    parser.add_argument("--llm_base_url", type=str, default="")
    parser.add_argument("--llm_model", type=str, default="")
    parser.add_argument("--llm_api_key", type=str, default="")
    parser.add_argument("--llm_api_key_env", type=str, default="")
    parser.add_argument("--llm_timeout_s", type=float, default=None)
    parser.add_argument("--llm_temperature", type=float, default=None)
    parser.add_argument("--llm_max_tokens", type=int, default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    config = _load_json(resolve_eedi_path(args.config))
    _apply_config_defaults(args, config)
    _resolve_llm_api_key(args)
    _require_llm_args(args)
    if args.max_concurrency <= 0:
        args.max_concurrency = int(
            config.get("llm_total_concurrency_budget", 0)
            or config.get("max_concurrency", 0)
            or 8
        )
    if args.max_concurrency <= 0:
        raise ValueError("--max_concurrency must be > 0")
    if args.llm_timeout_s is None:
        args.llm_timeout_s = 120.0
    if args.llm_temperature is None:
        args.llm_temperature = 0.0
    if args.llm_max_tokens is None:
        args.llm_max_tokens = 1800

    input_file = resolve_eedi_path(args.input_file)
    if not input_file.exists():
        raise FileNotFoundError(f"input_file not found: {input_file}")
    if args.output_dir:
        output_dir = resolve_eedi_path(args.output_dir)
    else:
        output_dir = input_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_config = LLMConfig(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        timeout_s=args.llm_timeout_s,
        temperature=args.llm_temperature,
        max_tokens=args.llm_max_tokens,
    )
    rows = load_theory_error_rows(input_file=input_file, truncate=args.truncate)
    rows = [row for row in rows if _gold_turn_is_officially_incorrect(row)]
    if not rows:
        raise ValueError("no gold-incorrect rows found for theory error evaluation")
    records = evaluate_theory_error_rows(
        rows=rows,
        llm_config=llm_config,
        max_concurrency=args.max_concurrency,
    )
    summary = build_theory_error_summary(records)
    write_theory_error_outputs(
        output_dir=output_dir,
        records=records,
        summary=summary,
    )
    print(f"Wrote theory error eval outputs to {output_dir}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("config must be a JSON object")
    return raw


def _apply_config_defaults(args: argparse.Namespace, config: dict[str, object]) -> None:
    for key in (
        "llm_base_url",
        "llm_model",
        "llm_api_key",
        "llm_api_key_env",
        "llm_timeout_s",
        "llm_temperature",
        "llm_max_tokens",
    ):
        current = getattr(args, key)
        if isinstance(current, str):
            if current.strip():
                continue
        elif current not in (0, 0.0):
            continue
        if key in config:
            setattr(args, key, config[key])


def _resolve_llm_api_key(args: argparse.Namespace) -> None:
    env_name = str(args.llm_api_key_env or "").strip()
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if not env_value:
            raise ValueError(f"missing required environment variable for llm_api_key: {env_name}")
        args.llm_api_key = env_value


def _require_llm_args(args: argparse.Namespace) -> None:
    missing: list[str] = []
    if not str(args.llm_base_url or "").strip():
        missing.append("--llm_base_url")
    if not str(args.llm_model or "").strip():
        missing.append("--llm_model")
    if not str(args.llm_api_key or "").strip():
        missing.append("--llm_api_key")
    if missing:
        raise ValueError(f"LLM config missing required args: {', '.join(missing)}")


if __name__ == "__main__":
    main()
