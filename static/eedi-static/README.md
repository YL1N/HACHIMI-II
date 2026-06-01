# EEDI-static Harness

这是 EEDI 2018-2020 静态诊断题数据上的独立学生模拟 harness。

它采用和 XES 静态主线一致的高层方法：**先做第三人称学生状态判断，再在状态边界内生成学生答案**。它不是 XES 代码的直接包装，也不是缩水版迁移；它只在数据读取、题型格式、知识点字段、OCR 文本和画像来源上做 EEDI-static 适配。

## 默认黄金集

- 配置：`configs/eedi_static_common_test_676x265_text_only_clean_20260520.json`
- 学生：`676`
- 测试题：`265`
- 总任务：`179140`
- 分层：`poor/low/medium/high` 各 `169` 人
- 历史题：每名学生至少还有 `113` 道非测试历史题，默认使用 `30` 道构建学生模型

## 方法链

```text
真实非测试历史作答 + 可选 HACHIMI 原始画像
-> HACHIMI 候选排序
-> 强模型选择最匹配画像
-> StudentModel
-> StudentInternalSignals
-> ProblemRequirementProfile
-> StudentItemInteractionDecision
-> ItemResponseState
-> ConstraintBundle
-> StudentAnswer
-> Evaluation
```

核心模块含义：

- `HACHIMI 候选排序`：只用规则做粗筛，把年龄、能力档、数学强弱和学习风格相近的画像排到前面；这一步不做最终决定。
- `强模型选择最匹配画像`：把 EEDI 观测画像和候选 HACHIMI 的完整原始字段一起交给强模型，由强模型选择 1 个画像，并输出匹配依据、冲突依据和融合规则。
- `StudentModel`：由非测试历史作答构建学生画像，包括强弱知识点、自我效能、SRL、control-value、engagement、response directness 和数学任务能力画像。
- `StudentInternalSignals`：把完整学生画像压缩成后续状态层可用的内部信号。
- `ProblemRequirementProfile`：只用 OCR 题面和 subject path 描述题目需求，不使用正确答案或经验正确率。
- `StudentItemInteractionDecision`：判断该学生遇到该题的可达性、正确性区间、可能错误和解释上限。
- `ItemResponseState`：确定当前作答状态、error path、commitment 和表达边界。
- `ConstraintBundle`：把状态翻译成生成约束，并做 violation check；失败时只允许一次显式 retry。

## 数据边界

生成链路不允许使用：

- 当前测试题的 `CorrectAnswer`
- 当前真实学生的 `AnswerValue`
- 当前真实学生的 `IsCorrect`
- 当前题目的经验正确率
- 未来作答或评测结果

允许使用：

- 非测试历史作答
- 当前题目图片
- 当前题目 subject path
- HACHIMI 原始画像字段，但只能作为学生画像先验，不能覆盖 EEDI 非测试历史中已经观察到的数学能力证据
- 由上述信息构建出的第三人称中间对象

## HACHIMI 画像融合

EEDI-static 的 HACHIMI 融合不是简单按年龄和能力档硬匹配。

当前流程是：

1. 从 EEDI 非测试历史构建 `eedi_observed_profile`，包括年龄、能力档、历史正确率、强弱数学领域和学习稳定性信号。
2. 用规则排序生成少量 HACHIMI 候选；规则只负责缩小范围，不负责最终匹配。
3. 强模型读取完整候选画像，字段包括 `姓名`、`年龄`、`性别`、`年级`、`发展阶段`、`代理名`、`擅长科目`、`薄弱科目`、`学术水平`、`人格`、`价值观`、`社交关系`、`创造力`、`心理健康`、`_采样约束`。
4. 强模型输出最终 `HachimiMatch`，包含 `selected_hachimi_id`、匹配依据、冲突依据和融合规则。
5. `StudentModel` 构建时再次接收完整 `raw_hachimi_persona`、压缩画像卡片和融合规则；后续状态层使用融合后的 `StudentModel`。

原则是：EEDI 非测试历史决定数学能力主证据；HACHIMI 补充学习风格、情绪调节、表达习惯、创造力和社交互动先验。若两者冲突，冲突必须保留，不允许让 HACHIMI 覆盖真实历史。

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

当前默认 `--max_tokens 1800`，因为完整 `StudentModel` 对象比较长。

带 HACHIMI 的运行需要强模型参与画像匹配，不能使用 `--dry_run`：

```powershell
python .\static\eedi-static\run_eedi_static_benchmark.py `
  --config_path .\static\eedi-static\configs\eedi_static_image_age_balanced_480x107_20260526.json `
  --llm_base_url "<openai-compatible-base-url>/v1" `
  --llm_model "<model-name>" `
  --llm_api_key "<api-key-or-dummy>" `
  --hachimi_persona_paths `
    .\data\personas_math_strong_grade5_exact_20x4_seed42.jsonl `
    .\data\personas_math_strong_grade6_exact_20x4_seed42.jsonl
```

## 当前验证状态

已通过：

- `compileall`
- `python -m unittest discover -s static/eedi-static/tests -v`
- `4×5` dry-run
- `4×2` 真 LLM smoke
- `6×6` 真 LLM 小样本复测
- `20×20` 真 LLM 中等 smoke，已完整产出 `metrics.json`

当前重试机制：

- generation 层默认 `--generation_attempts 4`
- task 层默认 `--task_retry_attempts 2`
- 若仍失败，会写出 `failures.jsonl` 和 `predictions_partial.jsonl`，不吞错

下一步建议先跑 `100×50` 或 `100×100`，再进入全量 `676×265`。

最新审计报告：

- `reports/eedi_static_full_xes_method_migration_audit_20260520.md`
