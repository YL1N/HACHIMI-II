# EEDI-static 原图学生模拟接入说明（2026-05-25）

## 1. 当前决定

EEDI-static 学生模拟从本版本开始切到 **image-only 当前题输入**。

也就是：

> 当前题目只传原始图片，不传 OCR 文本。

OCR 文本仍然可以保存在数据文件里用于离线审计，但不进入 prompt。

## 2. 链路变化

保持原来的元方法：

`StudentModel -> StudentInternalSignals -> ProblemRequirementProfile -> StudentItemInteractionDecision -> ItemResponseState -> ConstraintBundle -> Prediction`

其中当前题图片进入三个环节：

- `ProblemRequirementProfile`
- `StudentItemInteractionDecision`
- `Prediction` 生成

`ItemResponseState` 不直接看图片，它只读取前面已经形成的第三人称状态对象。

## 3. 不变的反作弊边界

生成链路不使用：

- 当前题真实学生作答；
- 当前题 `CorrectAnswer`；
- 当前题 `IsCorrect`；
- 当前题经验正确率；
- 当前题 OCR 文本；
- 未来信息；
- 生成后答案改写。

真实答案只用于离线评测。

## 4. 代码改动

- `static/eedi-static/src/data_loading.py`
  - `EediStaticQuestion` 增加 `image_path`。
- `static/eedi-static/src/llm_client.py`
  - 增加多模态 JSON 调用。
  - 默认传入 `chat_template_kwargs={"enable_thinking": false}`，避免 qwen3.5 只返回 reasoning。
- `static/eedi-static/src/static_chain.py`
  - 题目相关 prompt 改成 image-only。
  - 删除当前题 OCR 文本输入。

## 5. Smoke 结果

已跑通：

- 学生数：4
- 题目数：3
- 预测数：12
- `real_accuracy`: 0.5000
- `pred_accuracy`: 0.5000
- `consistency`: 0.5000
- `answer_match`: 0.4167

运行目录：

`static/eedi-static/outputs/eedi_static_image_student_sim_smoke/run_20260525_211302`

## 6. 推荐下一步

先不要直接跑 `676 × 265`。

推荐下一轮：

```powershell
$env:OPENAI_API_KEY="<INF_API_KEY>"
python static/eedi-static/run_eedi_static_benchmark.py `
  --llm_base_url "https://cge8kkjh9jgqcmjqkgpdedqqaog8gbkb.openapi-qb-ai.sii.edu.cn/v1" `
  --llm_model qwen3.5-397b `
  --llm_api_key $env:OPENAI_API_KEY `
  --max_students 20 `
  --max_questions 30 `
  --max_concurrency 6 `
  --task_retry_attempts 2 `
  --failure_rerun_rounds 1 `
  --max_tokens 3000 `
  --temperature 0.1 `
  --response_format_json `
  --output_root static/eedi-static/outputs/eedi_static_image_student_sim
```

如果 `20 × 30` 稳定，再放大到 `100 × 100`。
