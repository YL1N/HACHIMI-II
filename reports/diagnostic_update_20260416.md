# Diagnostic Update (2026-04-16)

## A. Evaluator and Prompt Updates
- Updated `src/evaluation.py` to support multi-blank fill scoring with ordered matching logic.
- Updated `src/prompts.py` answer generator with stricter `predicted_answer` format rules for fill/multi-blank outputs.

## B. Main Grade-3 100-Sample Run (after evaluator fix)
- run: `outputs\run_20260416_193843`
- n_predictions: 100
- overall_accuracy: 0.5600
- item_accuracy_mae_vs_xes: 0.366138
- item_accuracy_pearson_vs_xes: 0.529952
- level accuracy:
  - high: 0.7000 (n=30)
  - medium: 0.5333 (n=30)
  - low: 0.5500 (n=20)
  - poor: 0.4000 (n=20)

## C. Cross-Grade Comparison (same config: 6 personas x 10 questions)
| run | output_dir | n | overall_acc | item_mae | item_pearson |
|---|---|---:|---:|---:|---:|
| grade1_cross_60 | `outputs\run_20260416_194730` | 60 | 0.5000 | 0.426138 | 0.534607 |
| grade2_cross_60 | `outputs\run_20260416_195147` | 60 | 0.5500 | 0.345182 | 0.515018 |
| grade3_cross_60 | `outputs\run_20260416_195853` | 60 | 0.5333 | 0.361848 | 0.598005 |

## D. Goal Check
1. Grade/level separation
- Level separation exists in the grade-3 100-sample run, but not perfectly stable in small-sample cross-grade runs.
- Cross-grade accuracy ranking is not strictly monotonic in this batch (G2 slightly above G3).
2. Agreement with real student correctness
- Improved after evaluator fix, but still not high-consistency yet (MAE remains around 0.35~0.37 in current runs).
- Correlation is moderate (around 0.52~0.60), not yet strong enough for target-quality simulation.

## E. Prompt-Update Smoke
- run: `outputs\run_20260416_201715`
- n_predictions: 1, overall_accuracy: 1.0000
- pipeline is runnable after prompt update.

## F. Largest Per-Item Gaps in main grade-3 run
- q4: pred=0.00 vs xes=0.9213 (gap=0.9213), retry_rate=0.80, violation_rate=0.70
- q29: pred=0.00 vs xes=0.7672 (gap=0.7672), retry_rate=0.70, violation_rate=0.70
- q31: pred=0.10 vs xes=0.5753 (gap=0.4753), retry_rate=0.60, violation_rate=0.50
- q1: pred=0.20 vs xes=0.6389 (gap=0.4389), retry_rate=0.40, violation_rate=0.10

Interpretation:
- There are still item-specific failure clusters with both low correctness and high retry/violation load.
- Current bottleneck is likely state calibration + generation consistency on some fill items, not just scoring format.
