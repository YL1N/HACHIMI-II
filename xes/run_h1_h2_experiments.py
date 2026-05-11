"""
Run H1 and H2 difficulty perception experiments.

H1: Model analyzes difficulty with few-shot guidance
H2: Directly pass real difficulty band labels (diagnostic only)
"""

import argparse
import sys
from pathlib import Path

from src.root_cause_workflow import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_FROZEN_QUESTION_SET_PATH,
    ROOT_CAUSE_OUTPUT_ROOT,
    run_h1_difficulty_analysis,
    run_h2_real_difficulty_label,
)


def main():
    parser = argparse.ArgumentParser(description="Run H1 and H2 difficulty perception experiments")
    parser.add_argument(
        "--experiment",
        type=str,
        choices=["h1", "h2", "both"],
        default="both",
        help="Which experiment to run: h1 (model analysis), h2 (real labels), or both",
    )
    parser.add_argument(
        "--max_questions",
        type=int,
        default=150,
        help="Maximum number of questions to test",
    )
    parser.add_argument(
        "--max_personas",
        type=int,
        default=80,
        help="Maximum number of personas to test",
    )
    parser.add_argument(
        "--max_concurrency",
        type=int,
        default=16,
        help="Maximum concurrent LLM calls",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config file",
    )
    parser.add_argument(
        "--frozen_questions",
        type=str,
        default=str(DEFAULT_FROZEN_QUESTION_SET_PATH),
        help="Path to frozen question set",
    )

    args = parser.parse_args()

    config_path = Path(args.config)
    frozen_question_set_path = Path(args.frozen_questions)

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    if not frozen_question_set_path.exists():
        print(f"Error: Frozen question set not found: {frozen_question_set_path}")
        sys.exit(1)

    print("=" * 80)
    print("H1/H2 Difficulty Perception Experiments")
    print("=" * 80)
    print(f"Config: {config_path}")
    print(f"Frozen questions: {frozen_question_set_path}")
    print(f"Max questions: {args.max_questions}")
    print(f"Max personas: {args.max_personas}")
    print(f"Max concurrency: {args.max_concurrency}")
    print("=" * 80)

    if args.experiment in ["h1", "both"]:
        print("\n" + "=" * 80)
        print("Running H1: Model analyzes difficulty with few-shot guidance")
        print("=" * 80)
        try:
            h1_run_dir = run_h1_difficulty_analysis(
                output_root=ROOT_CAUSE_OUTPUT_ROOT / "H1_difficulty_analysis",
                config_path=config_path,
                frozen_question_set_path=frozen_question_set_path,
                max_questions=args.max_questions,
                max_personas=args.max_personas,
                max_concurrency=args.max_concurrency,
            )
            print(f"\n[OK] H1 completed successfully: {h1_run_dir}")
        except Exception as e:
            print(f"\n[FAIL] H1 failed: {e}")
            import traceback
            traceback.print_exc()
            if args.experiment == "h1":
                sys.exit(1)

    if args.experiment in ["h2", "both"]:
        print("\n" + "=" * 80)
        print("Running H2: Directly pass real difficulty band labels")
        print("WARNING: This uses real student statistics - diagnostic only!")
        print("=" * 80)
        try:
            h2_run_dir = run_h2_real_difficulty_label(
                output_root=ROOT_CAUSE_OUTPUT_ROOT / "H2_real_difficulty_label",
                config_path=config_path,
                frozen_question_set_path=frozen_question_set_path,
                max_questions=args.max_questions,
                max_personas=args.max_personas,
                max_concurrency=args.max_concurrency,
            )
            print(f"\n[OK] H2 completed successfully: {h2_run_dir}")
        except Exception as e:
            print(f"\n[FAIL] H2 failed: {e}")
            import traceback
            traceback.print_exc()
            if args.experiment == "h2":
                sys.exit(1)

    print("\n" + "=" * 80)
    print("All requested experiments completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()
