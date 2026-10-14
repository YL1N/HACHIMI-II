# Dynamic tutoring-dialogue baselines

This directory holds the dynamic-dialogue baselines only. It does not import the
static side.

## Coverage

- Datasets: `eedi_qatd2k`, `khan_comta`
- Baselines: `direct_roleplay`, `strong_prompting_ess`, `profile_conditioned`,
  `agent_style_memory`
- Unified sample fields: `dataset_name`, `dialogue_id`, `question_id`,
  `intervention_id`, `turn_idx`, `question_text`, `subjects`,
  `history_before_target`, and the evaluation-only `gt_turn`.

## Field isolation

The generation prompt may contain only:

- `question_text`
- `subjects`
- `history_before_target`
- `coarse_student_profile`, derived only from coarse statistics over prior
  student turns
- `short_visible_memory`, taken only from history before the current turn

Never enters the generation path:

- the real current student turn, future turns, and official
  correctness / acts / kcs / annotations / eval labels

`gt_turn` is written only to the output records and CSV for later offline
evaluation.

## Running

```powershell
python dynamic/baselines/run_dynamic_baselines.py `
  --dataset khan_comta `
  --baseline direct_roleplay `
  --output_root dynamic/baselines/outputs `
  --max_dialogues 1 `
  --max_tasks 1 `
  --dry_run
```

Non-dry-run requires an OpenAI-compatible endpoint:

```powershell
--llm_base_url http://127.0.0.1:8000/v1 --llm_model <model> --llm_api_key <key>
```

## Output

Each run writes:

- `predictions.jsonl`
- `turn_level_predictions.csv`
- `metrics.json`
- `run_config.json`
- `failure_cases.jsonl`
- `prompt_templates/*.md`

Only basic run metrics are computed here (`n_records`, `n_dialogues`,
`n_empty_outputs`, `violation_rate`, `retry_rate`). The metrics reported in the
paper are computed downstream from the stored judge labels by
`dynamic/evaluation/rescore_dialogue_metrics.py`.

## Baseline rationale

- The profile baselines follow the student-model idea from intelligent tutoring
  systems: represent learner knowledge and performance and use it for diagnosis
  or teaching decisions. Here the profile is built from coarse statistics over
  the prior student turns.
- `strong_prompting_ess` uses explicit prompting scaffolds only, directing the
  model's attention to the current tutor request, visible history, and math
  context, without predicting teaching strategy or future turns.
- `agent_style_memory` keeps only short visible memory, to test whether
  history-style continuity yields any gain.

References:

- Student modeling in ITS: https://doi.org/10.1177/089443939301100306
- Student modeling review: https://doi.org/10.1609/aiide.v8i5.12574
- Self-explanation effect: https://dblp.org/rec/journals/cogsci/ChiLCL94.html
- Cognitive apprenticeship / scaffolding: https://www.instructionaldesign.org/models/cognitive-apprenticeship/
