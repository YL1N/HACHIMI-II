# 100-Sample Diagnostic (2026-04-16)

Run output:
- outputs/run_20260416_192520

## Setup
- personas: 10 (grade-3 filtered)
- questions: 10
- total predictions: 100
- level distribution: high=30, medium=30, low=20, poor=20

## Official (current pipeline) metrics
- overall_accuracy: 0.4000
- retries: 47
- remaining_violations: 46
- item_accuracy_mae_vs_xes: 0.4646
- item_accuracy_pearson_vs_xes: 0.4993

Level accuracy (official):
- high: 0.5333
- medium: 0.4333
- low: 0.3000
- poor: 0.2500

Grade accuracy (official):
- 三年级: 0.4000 (no cross-grade comparability in this run)

Item-side agreement at threshold 0.5 (official):
- 0.40

Top item gaps (official):
- q4: pred=0.00 vs xes=0.9213 (gap=0.9213)
- q12: pred=0.00 vs xes=0.8471 (gap=0.8471)
- q29: pred=0.00 vs xes=0.7672 (gap=0.7672)
- q31: pred=0.00 vs xes=0.5753 (gap=0.5753)
- q7: pred=0.40 vs xes=0.9684 (gap=0.5684)

## Diagnostic note (tolerant multi-blank scoring, exploratory only)
A quick exploratory recomputation treating multi-blank fill answers as correct when all required gold tokens appear in prediction gives:
- overall_accuracy: 0.6000
- item_mae_vs_xes: 0.3217
- item_pearson_vs_xes: 0.3692
- item-side-agreement@0.5: 0.60

This indicates the current official evaluator likely underestimates correctness on some multi-blank fill items.
