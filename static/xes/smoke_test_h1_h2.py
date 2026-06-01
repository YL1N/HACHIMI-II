"""
Quick smoke test for H1/H2 experiments with minimal samples.
"""

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
    print("=" * 80)
    print("H1/H2 Smoke Test (minimal samples)")
    print("=" * 80)

    # Smoke test parameters
    max_questions = 5
    max_personas = 4
    max_concurrency = 2

    print(f"\nTest parameters:")
    print(f"  Max questions: {max_questions}")
    print(f"  Max personas: {max_personas}")
    print(f"  Max concurrency: {max_concurrency}")

    # Test H1
    print("\n" + "=" * 80)
    print("Testing H1: Model analyzes difficulty")
    print("=" * 80)
    try:
        h1_run_dir = run_h1_difficulty_analysis(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / "H1_difficulty_analysis_smoke",
            config_path=DEFAULT_CONFIG_PATH,
            frozen_question_set_path=DEFAULT_FROZEN_QUESTION_SET_PATH,
            max_questions=max_questions,
            max_personas=max_personas,
            max_concurrency=max_concurrency,
        )
        print(f"\nOK H1 smoke test passed: {h1_run_dir}")
    except Exception as e:
        print(f"\nERROR H1 smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Test H2
    print("\n" + "=" * 80)
    print("Testing H2: Real difficulty labels")
    print("=" * 80)
    try:
        h2_run_dir = run_h2_real_difficulty_label(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / "H2_real_difficulty_label_smoke",
            config_path=DEFAULT_CONFIG_PATH,
            frozen_question_set_path=DEFAULT_FROZEN_QUESTION_SET_PATH,
            max_questions=max_questions,
            max_personas=max_personas,
            max_concurrency=max_concurrency,
        )
        print(f"\nOK H2 smoke test passed: {h2_run_dir}")
    except Exception as e:
        print(f"\nERROR H2 smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 80)
    print("OK All smoke tests passed!")
    print("=" * 80)
    print("\nYou can now run the full experiments with:")
    print("  python run_h1_h2_experiments.py --experiment both")


if __name__ == "__main__":
    main()
