from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.detached_eval import run_detached_eval
from src.llm_client import LLMConfig
from src.runtime_paths import PROJECT_ROOT


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "eedi/configs/run_local.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run detached EEDI evaluation without external/sim-student-eval."
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

    parser.add_argument("--embedding_api_base_url", type=str, default="")
    parser.add_argument("--embedding_model", type=str, default="")
    parser.add_argument("--embedding_api_key", type=str, default="")
    parser.add_argument("--embedding_api_key_env", type=str, default="")
    parser.add_argument("--embedding_batch_size", type=int, default=0)
    parser.add_argument("--embedding_timeout_s", type=float, default=None)
    parser.add_argument("--embedding_max_retries", type=int, default=-1)
    parser.add_argument("--embedding_retry_sleep_s", type=float, default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    config = _load_json(Path(args.config))
    _apply_config_defaults(args, config)
    _resolve_api_keys(args)
    _require_core_args(args)

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

    if args.embedding_batch_size <= 0:
        args.embedding_batch_size = 16
    if args.embedding_timeout_s is None:
        args.embedding_timeout_s = 60.0
    if args.embedding_max_retries < 0:
        args.embedding_max_retries = 3
    if args.embedding_retry_sleep_s is None:
        args.embedding_retry_sleep_s = 2.0

    input_file = Path(args.input_file)
    if not input_file.exists():
        raise FileNotFoundError(f"input_file not found: {input_file}")

    output_dir = Path(args.output_dir) if args.output_dir else input_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_config = LLMConfig(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        timeout_s=args.llm_timeout_s,
        temperature=args.llm_temperature,
        max_tokens=args.llm_max_tokens,
    )

    summary = run_detached_eval(
        input_file=input_file,
        output_dir=output_dir,
        llm_config=llm_config,
        embedding_base_url=args.embedding_api_base_url,
        embedding_model=args.embedding_model,
        embedding_api_key=args.embedding_api_key,
        embedding_batch_size=args.embedding_batch_size,
        embedding_timeout_s=args.embedding_timeout_s,
        embedding_max_retries=args.embedding_max_retries,
        embedding_retry_sleep_s=args.embedding_retry_sleep_s,
        max_concurrency=args.max_concurrency,
        truncate=args.truncate,
    )
    print(f"Wrote detached eval outputs to {output_dir}")
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
        "embedding_api_base_url",
        "embedding_model",
        "embedding_api_key",
        "embedding_api_key_env",
        "embedding_batch_size",
        "embedding_timeout_s",
        "embedding_max_retries",
        "embedding_retry_sleep_s",
    ):
        current = getattr(args, key)
        if isinstance(current, str):
            if current.strip():
                continue
        elif current not in (None, 0, 0.0, -1):
            continue
        if key in config:
            setattr(args, key, config[key])


def _resolve_api_keys(args: argparse.Namespace) -> None:
    _resolve_single_api_key(args, "llm_api_key")
    _resolve_single_api_key(args, "embedding_api_key")


def _resolve_single_api_key(args: argparse.Namespace, key_name: str) -> None:
    env_name = str(getattr(args, f"{key_name}_env") or "").strip()
    if not env_name:
        return
    env_value = os.environ.get(env_name, "").strip()
    if not env_value:
        raise ValueError(f"missing required environment variable for {key_name}: {env_name}")
    setattr(args, key_name, env_value)


def _require_core_args(args: argparse.Namespace) -> None:
    missing: list[str] = []
    if not str(args.llm_base_url or "").strip():
        missing.append("--llm_base_url")
    if not str(args.llm_model or "").strip():
        missing.append("--llm_model")
    if not str(args.llm_api_key or "").strip():
        missing.append("--llm_api_key")
    if missing:
        raise ValueError(f"detached eval config missing required args: {', '.join(missing)}")


if __name__ == "__main__":
    main()
