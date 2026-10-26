# Dynamic student simulation

## Scope

This note describes the method used for the *dynamic* setting: given the
tutor-student interaction so far, predict only the next student turn. It is a
step-by-step prediction over an unfolding dialogue rather than a one-shot
item response. In this repository the dynamic method is instantiated on
Eedi-QATD2k (question-anchored tutoring dialogues) and Khan/CoMTA.

## What the dynamic setting predicts

Given the visible dialogue up to the current point:

- what the tutor just did in this turn,
- the student's current local state,
- whether this turn advances, stalls, misunderstands, or partially takes up the
  support,
- how the next student utterance externalizes that state.

The emphasis is on the *next* turn. The model should not hallucinate many
future turns at once.

## Method

The dynamic method does not map `dialogue history -> next student turn`
directly. Instead it runs:

```
dialogue history -> third-person state -> generation constraints -> current student turn
```

The generic skeleton is:

```
StudentModel -> DialogueContext -> TutorTurnProfile -> StudentTurnState -> StateTransitionPrediction -> ErrorBlueprint -> ConstraintBundle -> StudentTurn
```

which abstracts to `Context -> State -> Constraint -> Action`:

- `StudentModel`: the student's relatively stable long-term traits (baseline
  ability, common confusions, engagement tendency, expression style, typical
  reaction to help).
- `DialogueContext`: the interaction context visible at the current point —
  prior turns, the current item and metadata, and the current tutor turn. It
  must not contain the real next student turn, any future dialogue, or official
  evaluation labels.
- `TutorTurnProfile`: what the tutor is doing this turn (hint, follow-up,
  correction, clarification), its support strength and granularity, and the
  local direction it pushes the student.
- `StudentTurnState`: the core third-person state layer — whether the student
  currently understands, half-understands, is stuck, misunderstands, or
  hesitates; whether the student can take up the current tutor request; and, if
  not, the most likely local sticking point.
- `StateTransitionPrediction`: the state predicted for the next student turn
  given the current tutor turn — whether the student advances, remains stuck,
  or keeps a misconception.
- `ErrorBlueprint`: the predicted error of the next turn — its presence, locus,
  mechanism, and faulty rule.
- `ConstraintBundle`: the predicted state and error translated into this turn's
  generation boundaries — how much may be said, whether a full conclusion is
  allowed, whether hesitation or local confusion is retained, how strongly an
  error should surface, and which out-of-bounds behaviours are disallowed. The
  translation is a fixed rule-based mapping.
- `StudentTurn`: the current student turn, generated for this turn only.

## Data boundary

Allowed in the generation path: the dialogue history visible before the current
turn, the item and subject information, a persona prior matched from
HACHIMI-1M, and third-person state judgments over the above.

Not allowed in the generation path: the real next student turn, future
dialogue, official labels, or any post-hoc rewriting of the student turn to move
a metric. The generation path never skips the state layer to role-play
directly.

## Inputs and outputs

Inputs: prior dialogue, the current tutor turn, item text and metadata, and
subject information.

Outputs: the current student turn plus the intermediate objects (tutor-turn
profile, student-turn state, state-transition prediction, error blueprint,
constraint bundle) and the offline evaluation result. Each record in
`predictions.jsonl` stores them under `student_context_profile`,
`dialogue_context`, `tutor_turn_profile`, `interaction_state`,
`state_transition_prediction`, `error_blueprint`, and `constraint_bundle`,
next to `draft_turn`, `pred_turn`, `violation_check`, `surface_realization`,
`semantic_preservation`, and the run flags in `revisit_flags`. As in the static setting, the intermediate objects make the
full chain auditable.

## Running it

The dynamic entry scripts live under `dynamic/`. Each takes an
OpenAI-compatible endpoint via `--llm_base_url`, `--llm_model`, and
`--llm_api_key`. The next section lists the run configuration of each reported
run:

- `dynamic/eedi/` — the main dynamic pipeline (student-context profile,
  task-local learner state, state-transition prediction, behavior harness,
  single-step generation, dynamic violation check, optional one-step retry). It
  supports a HACHIMI-1M persona prior; see Appendix A (Persona Matching) in the paper.
- `dynamic/khan/` — Khan/CoMTA tutoring dialogues.
- `dynamic/baselines/` — Direct Role-Play, Prompt-Constrained,
  Profile-Conditioned, and Agent-Style Memory baselines for the dynamic
  setting.

## Run configurations of the reported runs

Run the commands from the repository root, and replace the endpoint, the API
key, and the output directory with local values.

### Eedi QATD2k, HACHIMI-II and ablations

```bash
python dynamic/eedi/run_eedi_experiments.py \
  --config dynamic/eedi/configs/<config>.json \
  --llm_base_url ... --llm_api_key ... --output_dir ...
```

| Run | Config |
| --- | --- |
| HACHIMI-II | `run_eedi_qatd2k_train_full_20260614.json` |
| w/o Prior | `run_eedi_qatd2k_train_without_hachimi_prior_20260619.json` |
| w/o State | `run_eedi_qatd2k_train_without_task_local_state_20260619.json` |
| w/o Harness | `run_eedi_qatd2k_train_without_behavior_harness_20260619.json` |

All four runs read `anchored-dialogues/train.csv` with `max_dialogues` 0 and
`max_tasks` 0, which selects every dialogue and turn. They use temperature 0.2,
`llm_max_tokens` 1200, a 240 s timeout, `constraint_profile` `default`,
`error_blueprint_mode` `structure_only`, and `retry_until_success` with at most
200 attempts per task. Concurrency is 80 for the full run and 48 for the
ablations. The configs set `skip_official_eval`, which affects only an optional
step that runs after generation. `persona_bank_path` in the configs is a
placeholder for the local persona bank file.

### Khan/CoMTA, HACHIMI-II and ablations

```bash
python dynamic/khan/run_khan_experiments.py \
  --dataset_path dynamic/khan/CoMTA_dataset.json \
  --ablation_mode <full|without_hachimi_prior|without_task_local_state|without_behavior_harness> \
  --max_dialogues 0 --max_tasks 0 --max_concurrency 48 \
  --write_full_outputs_every_n 50 \
  --llm_model Qwen3.5-397B --llm_temperature 0.2 --llm_max_tokens 1200 \
  --llm_timeout_s 240 --error_blueprint_mode full \
  --retry_until_success --retry_sleep_s 0.5 --max_retry_attempts 200 \
  --persona_bank_path <bank.jsonl> --persona_matching_top_k 8 \
  --llm_base_url ... --llm_api_key ... --output_dir ...
```

The dataset yields 917 student turns. `error_blueprint_mode` is `full` on
Khan/CoMTA and `structure_only` on Eedi QATD2k. With
`--ablation_mode without_hachimi_prior` no prior reaches any stage, and the
two prior-bank arguments can be omitted.

### Baselines

```bash
python dynamic/baselines/run_dynamic_baselines.py \
  --dataset <eedi_qatd2k|khan_comta> \
  --baseline <direct_roleplay|strong_prompting_ess|profile_conditioned|agent_style_memory> \
  --max_dialogues 0 --max_tasks 0 --max_concurrency 50 --max_retries 2 \
  --temperature 0.2 --max_tokens 1200 --timeout_s 180 --resume \
  --llm_base_url ... --llm_model ... --llm_api_key ...
```

`eedi_qatd2k` reads `anchored-dialogues/train.csv`
(`--eedi_anchored_dialogues_path`), and `khan_comta` reads
`CoMTA_dataset.json` (`--khan_dataset_path`). `strong_prompting_ess` is the
Prompt-Constrained baseline.

## Evaluation pipeline

All methods share the same evaluation pipeline. After generation, each method's
output goes through the same three steps:

1. **Export**: Convert `predictions.jsonl` to the judge input format by joining
   with annotated EEDI data.

   ```bash
   python dynamic/evaluation/export_eval_input.py \
     --run_dir <any_method_output_dir> \
     --annotated_eedi_dir external/sim-student-eval/data/annotated/eedi
   ```

   This works identically for HACHIMI-II, ablations, and baselines.

2. **Judge**: Run the GPT-5.4 judge on the exported CSV.

   ```bash
   python dynamic/eedi/run_detached_eval.py \
     --input_file <run_dir>/official_eval_input.csv \
     --config dynamic/eedi/configs/run_local.json
   ```

3. **Rescore**: Compute the reported metrics from the stored judge labels.

   ```bash
   python dynamic/evaluation/rescore_dialogue_metrics.py \
     --root <results_dir>
   ```

   The results directory must follow `<root>/<dataset>/<method>/eval_results.jsonl`.

## When this method transfers

The dynamic method fits tasks where the data unfolds step by step, each
prediction targets the next local behaviour, that behaviour depends strongly on
the prior interaction, and the same student's state evolves across multiple
turns.
