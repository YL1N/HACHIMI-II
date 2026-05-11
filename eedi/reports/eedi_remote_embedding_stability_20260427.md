# EEDI Remote Embedding Stability Note

## Current endpoint settings

- Main experiment and judge endpoint:
  - `https://ai-notebook-inspire.sii.edu.cn/ws-9dcc0e1f-80a4-4af2-bc2f-0e352e7b17e6/project-b795c114-135a-40db-b3d0-19b60f25237b/user-c6264b38-46a1-4bb6-a3a7-1db39453f6f8/vscode/60930ee7-02c0-4a60-bb43-aa934fbb5b65/5d5f1944-917d-40d6-ba98-89d76e7c5433/proxy/9501/v1`
- Embedding endpoint:
  - `https://ai.gitee.com/v1`
- Embedding model:
  - `Qwen3-Embedding-8B`

## Tested facts

- `100` independent concurrent embedding requests are not stable.
- Single-request embedding batches at `31+` inputs can return `400 BadRequest`.
- `embedding_batch_size=16` is the conservative stable setting for the current official eval path.

## Current runtime policy

- Keep `embedding_batch_size=16`.
- Use explicit remote embedding retry parameters:
  - `embedding_timeout_s=60.0`
  - `embedding_max_retries=3`
  - `embedding_retry_sleep_s=2.0`
- Judge path stays on the same OpenAI-compatible endpoint as the main experiment path.

## Why this change is acceptable

- It does not change the generation method.
- It only hardens the official eval transport layer against unstable third-party embedding service behavior.
- It does not introduce fallback scoring or hidden post-processing.
