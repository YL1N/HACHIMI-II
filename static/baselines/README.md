# Static item-response baselines

This directory implements the static-side baselines only. It provides no
top-level unified entry point and does not import `dynamic/`.

## Baseline families

- `direct_roleplay` (Direct Role-Play): the weakest single-stage role-play
  baseline; given only the current item and answer space.
- `strong_prompting_ess` (Prompt-Constrained): an ESS-inspired strong-prompting
  baseline that constrains the ability boundary in the prompt text.
- `profile_conditioned` (Profile-Conditioned): a profile-conditioned baseline
  that uses a visible history summary and student profile text.

`strong_prompting_ess` and `profile_conditioned` receive the same visible history
summary. `profile_conditioned` additionally receives the student profile text.

These are comparable inspired baselines and do not claim to fully reproduce any
external paper's system.

## Data source

Each baseline reads a prepared student-conditioned cohort produced by the
corresponding static pipeline (`benchmark_students.jsonl` and the associated
`questions.jsonl` / `student_models.jsonl`). Point the adapters in
`dataset_adapters.py` at the cohort directory produced by your own run for XES,
Eedi-static, and ENEM-CN.

## Field isolation

The generation prompt may use only:

- `dataset_name`
- `student_id`
- `question_id`
- `history_summary`
- `profile_text`
- `question_text`
- `image_path`
- `answer_space`

Used only for evaluation, never in the prompt:

- `real_answer`
- `correct_answer`
- `real_is_correct`

Item empirical statistics are not used in the prompt either.

Note: the XES final cache stores only test correctness, not real text answers.
For incorrect XES samples the `real_answer` is therefore recorded as
`__incorrect_or_unobserved_answer__`; XES can be reliably evaluated for
correctness consistency only, and this field must not be treated as a real
student text answer.

## Smoke test

```powershell
python static\baselines\run_static_baselines.py --dataset xes --baseline direct_roleplay --output_root static\baselines\outputs --llm_base_url http://unused --llm_model unused --llm_api_key unused --temperature 0 --max_tokens 16 --timeout_s 5 --max_students 1 --max_items 1 --max_concurrency 1 --dry_run
```

Eedi-static and ENEM dry runs:

```powershell
python static\baselines\run_static_baselines.py --dataset eedi_static --baseline direct_roleplay --output_root static\baselines\outputs --llm_base_url http://unused --llm_model unused --max_students 1 --max_items 1 --dry_run
python static\baselines\run_static_baselines.py --dataset enem_cn --baseline direct_roleplay --output_root static\baselines\outputs --llm_base_url http://unused --llm_model unused --max_students 1 --max_items 1 --dry_run
```

For real LLM calls, pass an OpenAI-compatible `/chat/completions` base URL. For
Eedi-static and ENEM, samples with an `image_path` are sent as a vision payload;
XES sends text only.

The reported runs use the script defaults `--temperature 0.2 --max_tokens 256
--timeout_s 180 --max_retries 2` on the full cohorts (no `--max_students` or
`--max_items`): XES 60 x 96, Eedi-static 480 x 107, ENEM-CN 7,200 x 24.

## Output

Each run writes:

- `predictions.jsonl`
- `eval_rows.jsonl`
- `metrics.json`
- `run_config.json`
- `failure_cases.jsonl`
- `progress.json`
- `prompt_templates/*.md`

`metrics.json` reports `consistency` (agreement of simulated and real
correctness), `answer_match`, the per-student and per-item accuracy Pearson and
Spearman correlations, `violation_rate` (answers outside the answer space), and
`retry_rate`.

LLM JSON parse failures are written to `failure_cases.jsonl`; predictions are
never fabricated.
