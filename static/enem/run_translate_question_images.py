from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from src.data_loading import load_area_item_bank, load_json
from src.image_direct_solve import load_direct_questions
from src.llm_client import LLMConfig, OpenAICompatClient
from src.question_images import build_question_page_manifest
from src.question_text_experiment import translate_question_image


ROOT = Path(__file__).resolve().parent
JSONL_LOCK = Lock()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_LOCK:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate ENEM question images into English text.")
    parser.add_argument("--config_path", default=str(ROOT / "configs" / "enem_cn_static_smoke_20260528.json"))
    parser.add_argument("--output_root", default=str(ROOT / "outputs" / "enem_cn_question_text_translation"))
    parser.add_argument("--run_dir", default=None)
    parser.add_argument("--build_page_images", action="store_true")
    parser.add_argument("--page_image_dpi", type=int, default=120)
    parser.add_argument("--llm_base_url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--llm_model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--llm_api_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max_tokens", type=int, default=2200)
    parser.add_argument("--timeout_s", type=float, default=180.0)
    parser.add_argument("--max_concurrency", type=int, default=8)
    parser.add_argument("--task_retry_attempts", type=int, default=3)
    return parser


def create_run_dir(args: argparse.Namespace) -> Path:
    run_dir = Path(args.run_dir) if args.run_dir else Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def maybe_build_effective_config(config_path: Path, run_dir: Path, args: argparse.Namespace) -> Path:
    config = load_json(config_path)
    if not args.build_page_images and config.get("question_image_manifest_path"):
        return config_path
    dataset_root = Path(str(config["source_dataset_root"]))
    area = str(config.get("target_area") or "CN")
    item_bank = load_area_item_bank(
        dataset_root=dataset_root,
        area=area,
        regular_codes=[str(code) for code in config.get("regular_codes", [])] or None,
        base_booklet_code=str(config["base_booklet_code"]) if config.get("base_booklet_code") else None,
    )
    cache_dir = (
        ROOT
        / "cache"
        / "question_images"
        / f"{area.upper()}_{item_bank.base_booklet_code}_dpi{args.page_image_dpi}_bbox_column_crop_v1"
    )
    manifest_path = cache_dir / "question_image_manifest.jsonl"
    build_question_page_manifest(
        dataset_root=dataset_root,
        item_bank=item_bank,
        output_path=manifest_path,
        page_image_dir=cache_dir / "pages",
        dpi=args.page_image_dpi,
    )
    config["question_image_manifest_path"] = str(manifest_path.resolve())
    config["question_image_cache_dir"] = str(cache_dir.resolve())
    effective_config_path = run_dir / "effective_config.json"
    write_json(effective_config_path, config)
    return effective_config_path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    if not args.llm_base_url or not args.llm_model:
        raise ValueError("--llm_base_url and --llm_model are required")
    if args.max_concurrency <= 0:
        raise ValueError("--max_concurrency must be positive")
    if args.task_retry_attempts <= 0:
        raise ValueError("--task_retry_attempts must be positive")

    run_dir = create_run_dir(args)
    effective_config_path = maybe_build_effective_config(Path(args.config_path), run_dir, args)
    questions = load_direct_questions(effective_config_path)
    manifest_path = run_dir / "question_text_manifest.jsonl"
    failure_path = run_dir / "failures.jsonl"
    existing = read_jsonl(manifest_path)
    completed_ids = {str(row["question_id"]) for row in existing}
    pending = [question for question in questions if question.question_id not in completed_ids]
    llm = OpenAICompatClient(
        LLMConfig(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            timeout_s=args.timeout_s,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            response_format_json=True,
        )
    )
    write_json(
        run_dir / "run_config.json",
        {
            "task": "enem_question_image_to_english_translation",
            "config_path": str(Path(args.config_path).resolve()),
            "effective_config_path": str(effective_config_path.resolve()),
            "n_questions": len(questions),
            "pending_at_start": len(pending),
            "llm_base_url": args.llm_base_url,
            "llm_model": args.llm_model,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "max_concurrency": args.max_concurrency,
            "task_retry_attempts": args.task_retry_attempts,
            "started_or_resumed_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    print(f"run_dir={run_dir}", flush=True)
    print(f"questions={len(questions)} completed={len(completed_ids)} pending={len(pending)}", flush=True)

    failures: list[dict[str, Any]] = []
    if pending:
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            tasks = {executor.submit(run_translate_one, question, llm, args.task_retry_attempts): question for question in pending}
            for idx, future in enumerate(as_completed(tasks), start=1):
                question = tasks[future]
                try:
                    append_jsonl(manifest_path, future.result())
                    if idx % 5 == 0 or idx == len(pending):
                        print(f"completed_pending={idx}/{len(pending)}", flush=True)
                except Exception as exc:
                    failure = {"question_id": question.question_id, "item_position": question.item_position, "error": repr(exc)}
                    failures.append(failure)
                    append_jsonl(failure_path, failure)
    if failures:
        raise RuntimeError(f"{len(failures)} translations failed; see {failure_path}")
    rows = read_jsonl(manifest_path)
    rows.sort(key=lambda row: int(row["item_position"]))
    with manifest_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_json(
        run_dir / "summary.json",
        {
            "n_questions": len(questions),
            "n_translations": len(rows),
            "manifest_path": str(manifest_path.resolve()),
        },
    )
    print(f"[Done] manifest_path={manifest_path}", flush=True)


def run_translate_one(question, llm: OpenAICompatClient, task_retry_attempts: int) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt_idx in range(1, task_retry_attempts + 1):
        try:
            translated = translate_question_image(question, llm)
            return {
                "question_id": question.question_id,
                "item_position": question.item_position,
                "question_text_language": "en",
                "question_text": translated["question_text"],
                "translation_notes": translated["translation_notes"],
                "source_image_path": str(question.image_path),
                "split": question.split,
                "skill_code": question.skill_code,
                "skill_summary": question.skill_summary,
                "competency_short_name": question.competency_short_name,
            }
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"translation failed after {task_retry_attempts} attempt(s): "
        f"question_id={question.question_id}, error={last_error!r}"
    )


if __name__ == "__main__":
    main()
