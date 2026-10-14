# Eedi static harness

Standalone student-simulation harness for the Eedi static diagnostic items. It
follows the same high-level method as the XES static pipeline: build a
third-person student state first, then generate the student answer within the
inferred state boundary. It is not a wrapper around the XES code; it only adapts
data loading, item format, subject fields, item images, and persona source to
the Eedi static setting.

## Default set

- Config: `configs/eedi_static_image_age_balanced_480x107_20260526.json`
  (the set of the reported runs)
- Students: `480` (ages 11 and 12, `240` each)
- Test items: `107`, answered by every selected student
- Total tasks: `51360`
- Strata: `poor / low / medium / high`, `120` students each
- History: `30` non-test historical items per student (`--history_size 30`)
  are used to build the student model.

## Method chain

```text
real non-test history + optional raw persona prior
-> candidate persona ranking
-> strong-model persona selection
-> StudentModel
-> StudentInternalSignals
-> ProblemRequirementProfile
-> StudentItemInteractionDecision
-> ItemResponseState
-> ConstraintBundle
-> StudentAnswer
-> Evaluation
```

Key stages:

- Candidate persona ranking: a rule-based coarse filter that surfaces personas
  with similar age, ability band, math strength/weakness, and learning style.
  It does not make the final choice.
- Strong-model persona selection: the observed Eedi profile and the full raw
  fields of the candidate personas are given to the strong model, which selects
  one persona and outputs its match, conflict, and fusion rationale.
- `StudentModel`: built from non-test history — strong/weak knowledge points,
  self-efficacy, SRL, control-value, engagement, response directness, and a math
  task-capability profile.
- `StudentInternalSignals`: compresses the full student model into internal
  signals for the downstream state layers.
- `ProblemRequirementProfile`: describes item demands from the item image and
  the subject path only; it does not use the correct answer or empirical
  accuracy.
- `StudentItemInteractionDecision`: reachability, correctness band, likely
  error, and explanation cap for this student on this item.
- `ItemResponseState`: the current response state, error path, commitment, and
  expression boundary.
- `ConstraintBundle`: translates the state into generation constraints with a
  violation check; on a violation the answer is regenerated under a tightened
  bundle, up to `--generation_attempts` attempts in total.

## Data boundary

The generation path may not use:

- the current item's `CorrectAnswer`
- the current student's `AnswerValue`
- the current student's `IsCorrect`
- the current item's empirical accuracy
- any future response or evaluation result

The generation path may use:

- non-test historical responses
- the current item image
- the current item subject path
- raw persona fields, only as a student prior that cannot override the math
  ability evidence already observed in the Eedi non-test history
- the third-person intermediate objects built from the above

## Persona fusion

Persona fusion is not a hard age/ability match. The current flow is:

1. Build an `eedi_observed_profile` from the Eedi non-test history (age, ability
   band, historical accuracy, strong/weak math areas, stability signals).
2. Rank a small set of persona candidates by rule; ranking only narrows the
   pool.
3. The strong model reads the full candidate personas. The persona fields are:
   `name`, `age`, `gender`, `grade`, `developmental_stage`, `strong_subjects`,
   `weak_subjects`, `academic_level`, `personality`, `values`,
   `social_relationships`, `creativity`, and `mental_health`.
4. The strong model outputs a final `HachimiMatch` with `selected_persona_id`,
   match rationale, conflict rationale, and fusion rule.
5. `StudentModel` receives the raw persona, the compressed persona card, and the
   fusion rule; the downstream state layers use the fused `StudentModel`.

Principle: the Eedi non-test history is the primary evidence for math ability;
the persona only supplies priors for learning style, emotion regulation,
expression habits, creativity, and social interaction. Where the two conflict,
the conflict is preserved and the persona does not override the real history.

## Smoke test

```powershell
python .\static\eedi-static\run_eedi_static_benchmark.py --dry_run --max_students 4 --max_questions 5
```

## LLM smoke

```powershell
python .\static\eedi-static\run_eedi_static_benchmark.py `
  --llm_base_url "<openai-compatible-base-url>/v1" `
  --llm_model "<model-name>" `
  --llm_api_key "<api-key-or-dummy>" `
  --max_students 4 `
  --max_questions 2 `
  --max_concurrency 2
```

The default `--max_tokens 1800` accounts for the length of the full
`StudentModel` object.

Runs with persona fusion require the strong model for persona matching and
cannot use `--dry_run`. The reported `full` run uses the script defaults plus
the persona files:

```powershell
python .\static\eedi-static\run_eedi_static_benchmark.py `
  --config_path .\static\eedi-static\configs\eedi_static_image_age_balanced_480x107_20260526.json `
  --history_size 30 --ablation_mode full `
  --llm_base_url "<openai-compatible-base-url>/v1" `
  --llm_model "<model-name>" `
  --llm_api_key "<api-key-or-dummy>" `
  --temperature 0.2 --max_tokens 1800 --timeout_s 240 --response_format_json `
  --generation_attempts 4 --task_retry_attempts 2 --failure_rerun_rounds 6 `
  --hachimi_persona_paths `
    .\data\personas_grade5.jsonl `
    .\data\personas_grade6.jsonl
```

`--ablation_mode` selects `full`, `without_hachimi_prior`,
`without_task_local_state`, or `without_behavior_harness`. Without
`--hachimi_persona_paths` no persona is matched, so the `full`,
`without_task_local_state`, and `without_behavior_harness` runs pass the persona
files and `without_hachimi_prior` ignores them.

## Retry behaviour

- Generation layer: `--generation_attempts 4` by default.
- Task layer: `--task_retry_attempts 2` by default.
- Run layer: failed tasks are resubmitted for up to `--failure_rerun_rounds 6`
  further rounds; every failed attempt is logged in `failure_attempts.jsonl`.
- On persistent failure, `failures.jsonl` is written, completed rows stay in
  `predictions.jsonl`, and the script raises; errors are not swallowed.
