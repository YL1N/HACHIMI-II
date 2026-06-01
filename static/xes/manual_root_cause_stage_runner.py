from __future__ import annotations

import argparse

from src.root_cause_workflow import (
    ROOT_CAUSE_OUTPUT_ROOT,
    run_d1_simple_forced_state,
    run_d2_full_forced_state,
    run_e1_counterfactual_sensitivity,
    run_f1_stability,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one root-cause experiment stage without writing reports or updating plans."
    )
    parser.add_argument("--stage", choices=["D1", "D2", "E1", "F1"], required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    smoke = bool(args.smoke)
    stage = args.stage

    if stage == "D1":
        run_dir = run_d1_simple_forced_state(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("D1_simple_forced_state_smoke" if smoke else "D1_simple_forced_state"),
            samples_per_state=2 if smoke else 20,
            max_questions=4 if smoke else None,
            max_concurrency=4 if smoke else 16,
        )
    elif stage == "D2":
        run_dir = run_d2_full_forced_state(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("D2_full_forced_state_smoke" if smoke else "D2_full_forced_state"),
            samples_per_state=2 if smoke else 20,
            max_questions=4 if smoke else None,
            max_concurrency=4 if smoke else 16,
        )
    elif stage == "E1":
        run_dir = run_e1_counterfactual_sensitivity(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("E1_counterfactual_sensitivity_smoke" if smoke else "E1_counterfactual_sensitivity"),
            max_questions=4 if smoke else 20,
            repeats_per_side=1 if smoke else 5,
            max_concurrency=4 if smoke else 12,
        )
    else:
        run_dir = run_f1_stability(
            output_root=ROOT_CAUSE_OUTPUT_ROOT / ("F1_stability_smoke" if smoke else "F1_stability"),
            max_questions=4 if smoke else 20,
            max_personas=4 if smoke else 8,
            repeats=2 if smoke else 3,
            max_concurrency=4 if smoke else 12,
        )

    print(run_dir)


if __name__ == "__main__":
    main()
