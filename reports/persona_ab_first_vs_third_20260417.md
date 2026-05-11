# First vs Third Persona A/B (Prompt-Isolated)

Date: 2026-04-17

## Experiment setup
- Same dataset/sampling settings
- Same model endpoint and concurrency
- Same persona/question counts: 10 x 10 = 100 predictions each
- Only changed variable: answer-generation system prompt perspective
  - first-person prompt
  - third-person prompt

## Runs
- first-person: `outputs/run_20260417_113403`
- third-person: `outputs/run_20260417_113729`

## Core metrics

| persona | overall_accuracy | item_mae_vs_xes | item_pearson_vs_xes | retries | remaining_violations |
|---|---:|---:|---:|---:|---:|
| first | 0.6000 | 0.318360 | 0.406378 | 5 | 15 |
| third | 0.5900 | 0.295457 | 0.410957 | 3 | 11 |

## Level accuracy

- first: high=0.6667, medium=0.6667, low=0.6000, poor=0.4000
- third: high=0.7000, medium=0.6333, low=0.5500, poor=0.4000

## Item-gap profile (top gaps)
Both settings share the same dominant hard items:
- q4, q29, q31 are the largest mismatch sources.

## Interpretation
- Prompt isolation is implemented: first/third are separate system prompts.
- First-person gives slightly higher overall accuracy in this batch.
- Third-person gives slightly better item-level alignment (lower MAE, slightly higher Pearson) and fewer violations/retries.
- Difference is modest; current bottleneck remains specific hard items, not perspective alone.
