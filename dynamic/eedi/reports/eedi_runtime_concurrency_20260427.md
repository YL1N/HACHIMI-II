# EEDI Runtime Concurrency Note

## Current runtime defaults

- `llm_total_concurrency_budget=100`
  - This is the single concurrency budget for the shared `9501/v1` endpoint.
  - Generation stage and `sim-corr-errs` judge stage run sequentially, so each stage can use this as its own cap.
- `max_concurrency`
  - Now only acts as an optional generation-stage override.
  - If omitted, generation uses `llm_total_concurrency_budget`.
- `llm_judge_batch_size`
  - Now only acts as an optional judge-stage override.
  - If omitted, the judge uses `llm_total_concurrency_budget`.
- `write_full_outputs_every_n=100`
  - Full CSV / metrics refresh happens every 100 completed tasks.
  - Incremental `predictions.jsonl` and `stage_traces.jsonl` still append every completed task.

## Why this change was needed

- The previous setup had two separate numbers:
  - `max_concurrency`
  - `llm_judge_batch_size`
- Even when both were set to `100`, the engineering meaning was ambiguous.
- The actual constraint from the deployment is simpler:
  - `100` means the total supported concurrency of the shared `9501/v1` endpoint.
- So the runtime now has one primary fact and two optional stage-specific overrides.

## Other runtime constraints

- Remote embedding still stays conservative:
  - `embedding_batch_size=16`
  - `embedding_timeout_s=60`
  - `embedding_max_retries=3`
  - `embedding_retry_sleep_s=2`

## Official eval execution policy

- If `sim-text` uses the remote Gitee embedding endpoint, and `sim-corr-errs` is also requested:
  - `eedi/run_official_eval_with_qwen.py` now splits them into two independent subruns.
  - `sim-text` uses the remote embedding endpoint.
  - `sim-corr-errs` uses the shared `9501/v1` judge endpoint.
  - The two subruns are launched in parallel, then their CSV outputs are merged back into one final official-eval artifact.
- This only changes engineering throughput.
- It does not change the scoring definition or generation path.

## Verified facts

- `run_eedi_experiments.py` thread-pool path was exercised on a 2-task live smoke run.
- `run_official_eval_with_qwen.py` judge path was exercised on a 5-sample live smoke run with cache bypass, and real requests were sent.
