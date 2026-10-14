# Static student simulation

## Scope

This note describes the method used for the *static* setting: given a student's
history and a single target item, predict only that student's response on that
item. It is a one-shot, single-item prediction rather than a multi-turn
interaction. In this repository the static method is instantiated on XES3G5M,
Eedi (static), and ENEM.

## What the static setting predicts

For a given student and a given item:

- whether the student is likely to reach a correct answer,
- if not, where the local breakdown is most likely to occur,
- how mature or complete the response will be,
- whether the response stays within the student's current ability boundary.

The goal is not to make the model "talk like a student"; it is to keep the
predicted response consistent with the student's inferred state on this item.

## Method

The static method does not map `history/item -> student answer` directly.
Instead it runs:

```
history/item -> third-person state -> generation constraints -> student answer
```

The pipeline stages, in the order the entry scripts run them, are:

```
history -> observed profile -> persona candidate ranking -> persona selection
        -> StudentModel -> StudentInternalSignals
item    -> ProblemRequirementProfile
        -> StudentItemInteractionDecision -> ItemResponseState -> ConstraintBundle -> Response -> evaluation
```

which abstracts to `Context -> State -> Constraint -> Action`:

- Persona matching: a rule-based ranker keeps the top 8 persona candidates for
  the observed profile, and the model selects one of them
  (`llm_profile_matcher_v1`). The selected persona is fused with the observed
  profile.
- `StudentModel`: a durable third-person description of the student built from
  prior history and the matched persona (mastered content, behaviour across
  difficulty levels, typical failure modes, response style).
- `StudentInternalSignals`: a compact set of signals the model derives from the
  `StudentModel` for the later stages.
- `ProblemRequirementProfile`: what the item actually demands (prerequisites,
  single- vs multi-step, representation shifts, format sensitivity,
  guessability), not a restatement of the prompt. It is built once per item.
- `StudentItemInteractionDecision`: a prior on how this student meets this item
  (reachability, correctness band, likely error family, confidence and
  explanation caps). XES computes it by rule from the capability profile and
  the item profile; Eedi and ENEM obtain it from the model.
- `ItemResponseState`: the core third-person state layer — prerequisite
  familiarity, response state, reachable level, error path, commitment
  tendency, explanation-depth cap, and response-style guidance.
- `ConstraintBundle`: the state compiled by a fixed function into generation
  boundaries (`must_commit_answer`, `allow_complete_explanation`,
  `max_sentences`, `max_thinking_steps`, `forbid_full_mastery`,
  `preferred_error_path`, `style_constraints`, `allowed_commitment`, and, for
  Eedi and ENEM, `output_answer_space`).
- `Response`: the item-level student answer (`predicted_answer` and
  `student_response`), which only externalizes the state and constraints above
  rather than solving the item freely.

Dataset-specific behaviour of the last two stages:

- XES runs with `constraint_profile = "loose"` and
  `difficulty_signal_enabled = false` (`harness_version =
  "hachimi_no_difficulty_signal_loose_constraints"`). The compiled bundle is
  loosened before generation: the reasoning-step budget compiled from the state
  is kept, `max_sentences` is 3, and the error-path and style lists are empty.
  The answer is generated step by step within that budget, and a last step that
  does not commit a final answer is regenerated once.
- Eedi and ENEM pass the compiled bundle to the generator unchanged, check the
  output against it (answer space, committed answer, sentence limit, and for
  Eedi mastery markers), and regenerate under a tightened bundle, up to
  `--generation_attempts` attempts in total.

## Data boundary

Allowed in the generation path: student history, the current item and its
metadata, and the third-person intermediate objects derived from them.

Not allowed in the generation path: the gold answer, the real current-item
answer or correctness label, empirical item statistics, and any future
observation. No per-item or per-student special-casing, and no post-hoc
answer rewriting to move a metric.

## Inputs and outputs

Inputs: student history, the persona file used for matching, the current item,
and item metadata.

Outputs: the item-level student answer plus the intermediate objects and the
offline evaluation result. The intermediate objects make the method chain
auditable rather than a single opaque answer. Per-record keys:

- XES `predictions.jsonl`: `student_model`, `implementation_derived_signals`,
  `problem_requirement_profile`, `student_item_interaction_decision`,
  `item_response_state`, `constraint_bundle`, `thinking_trace`, the flags
  `harness_version`, `method_variant`, `response_persona`,
  `difficulty_signal_enabled`, `constraint_profile`, `ablation_mode`,
  `behavior_harness_used_in_generation`, and the scored fields `is_correct` and
  `correctness_label`.
- Eedi and ENEM `predictions.jsonl`: `student_model`, `internal_signals`,
  `problem_profile`, `interaction_decision`, `response_state`,
  `constraint_bundle`, `violation_report`, `retry_count`; `eval_rows.jsonl`
  holds the scored rows.

## Ablation modes

Every pipeline entry script takes `--ablation_mode`:

- `full`: all stages.
- `without_hachimi_prior`: no persona matching; the `StudentModel` is built
  from the visible history only.
- `without_task_local_state`: the interaction decision and the
  `ItemResponseState` are replaced by fixed neutral defaults and the bundle is
  the format-only bundle; the `StudentModel` is unchanged.
- `without_behavior_harness`: the state is inferred as in `full`, the bundle is
  the format-only bundle, and the bundle is left out of the generation prompt.
  Eedi and ENEM still check the output against the format-only bundle.

For Eedi and ENEM the persona prior is used only when `--hachimi_persona_paths`
is given; the `full`, `without_task_local_state`, and
`without_behavior_harness` runs pass it.

## Metrics

- XES (`metrics.json`): record-level agreement between simulated and real
  correctness, per-student accuracy Pearson and Spearman correlations, the
  Kolmogorov-Smirnov statistic and the Wasserstein-1 distance between the real
  and simulated per-student accuracy distributions, and per-item accuracy
  correlations. Simulated correctness comes from the rule-based answer matcher
  (`--official_correctness_mode rules_only`).
- Eedi, ENEM, and the baselines (`metrics.json`): `consistency` (agreement of
  simulated and real correctness), `answer_match`, and the per-student and
  per-item accuracy Pearson and Spearman correlations. Simulated correctness is
  the comparison of `predicted_answer` with the answer key.

## Running it

The static entry scripts live under `static/` and are run from the repository
root. Each takes an OpenAI-compatible endpoint via `--llm_base_url`,
`--llm_model`, and `--llm_api_key`. The script defaults are the settings of the
reported runs (temperature 0.2, JSON response format).

- `static/xes/` — XES3G5M, 60 students x 96 items
  (`configs/common_test_60x96_20260507.json`, 30 history items per student).
  The cohort is prepared offline and then simulated:

  ```
  python static/xes/run_irt_support_filter.py
  python static/xes/export_irt_calibration_inputs.py --eligible_question_path <irt_support run>/eligible_questions.json
  python static/xes/split_irt_calibration_by_module.py --input_dir <irt_calibration_inputs run>
  python static/xes/fit_rasch_module.py --module_dir <irt_calibration_inputs run>/modules/<module>   # once per module
  python static/xes/run_student_conditioned_benchmark.py \
    --eligible_question_path <irt_support run>/eligible_questions.json \
    --persona_path <personas.jsonl> --ablation_mode full \
    --llm_base_url ... --llm_model ... --llm_api_key ...
  ```

  The support filter selects the eligible item pool (966 items with the default
  thresholds), and the Rasch module fits under
  `static/xes/outputs/rasch_module_fits` give the easy/medium/hard bands used in
  the history summaries. The item difficulty signal is not passed to the
  generator. Add `--prepare_only` to build the cohort without model calls
  (`--ablation_mode without_hachimi_prior` needs no model for this step).
- `static/eedi-static/` — Eedi, 480 students x 107 items
  (`configs/eedi_static_image_age_balanced_480x107_20260526.json`).
- `static/enem/` — ENEM 2024 natural sciences, 7,200 students x 24 items
  (`configs/enem_cn_static_english_text_plus_image_20260529.json`, English item
  text plus the item image).
- `static/baselines/` — Direct Role-Play, Prompt-Constrained, and
  Profile-Conditioned baselines for the static setting. They read the cohort
  files written by the pipelines above.

See the `README.md` in `static/eedi-static/`, `static/enem/`, and
`static/baselines/` for the commands of those settings.

## When this method transfers

The static method fits tasks where samples are largely independent, each
prediction targets one local student behaviour, the focus is "how would this
student handle this task", and there is no long chain of state updates across
many turns.
