# EEDI-static 对 XES 静态方法完整迁移审计（2026-05-20）

## 1. 当前结论

EEDI-static 和 XES 都属于**静态单题学生作答模拟**。

所以这里不应该另起一套方法，也不应该做“最小迁移版”。正确做法是：

> 保持 XES 已验证过的静态学生模拟元方法，只把数据读取、题目格式、知识点字段、OCR 文本和画像来源换成 EEDI-static 版本。

当前代码已经完成第一轮完整迁移。它不是直接 import XES，也不是删字段后的简化链路，而是 EEDI-static 独立入口下的 XES-equivalent 静态方法实现。

实现入口：

- `D:\Study\sii\MathStudent\static\eedi-static\run_eedi_static_benchmark.py`
- `D:\Study\sii\MathStudent\static\eedi-static\src\static_chain.py`
- `D:\Study\sii\MathStudent\static\eedi-static\src\data_loading.py`

## 2. 黄金测试集

当前默认使用 text-only clean 黄金集：

- 配置：`D:\Study\sii\MathStudent\static\eedi-static\configs\eedi_static_common_test_676x265_text_only_clean_20260520.json`
- 学生：`676`
- 测试题：`265`
- 总任务：`179140`
- 学生分层：`poor/low/medium/high` 各 `169` 人
- 作答覆盖：每个入选学生都做过全部 `265` 道测试题
- 历史题：每个学生至少还有 `113` 道非测试历史题，当前默认取 `30` 道构建学生模型

额外审计见：

- `D:\Study\sii\MathStudent\static\eedi-static\reports\eedi_static_ocr_answer_audit_20260520.md`

## 3. 方法链

当前 EEDI-static 静态链路为：

```text
真实非测试历史作答
-> StudentModel
-> StudentInternalSignals
-> ProblemRequirementProfile
-> StudentItemInteractionDecision
-> ItemResponseState
-> ConstraintBundle
-> StudentAnswer
-> Evaluation
```

这和 XES 的核心思想一致：

> 不是让模型直接装学生答题，而是先做第三人称状态判断，再在状态边界内生成学生答案。

## 4. 各模块含义

### 4.1 StudentModel

`StudentModel` 是学生画像。

它不是一个简单正确率分数，而是由 EEDI 非测试历史作答构建出的第三人称学生模型，包括：

- 学术水平；
- 强弱知识点；
- 自我效能判断；
- SRL 脆弱性；
- control-value 判断；
- engagement 倾向；
- response directness；
- 数学任务能力画像；
- 原始历史摘要和证据。

EEDI-static 和 XES 的不同点是：

- XES 可以接 Hachimi / persona-like profile；
- EEDI-static 当前先用真实历史作答和 subject path 生成 persona-like 学生画像；
- 如果某个能力维度在历史中没有足够证据，显式标为 `not_observed`，不硬说成低能力。

### 4.2 StudentInternalSignals

`StudentInternalSignals` 是把完整学生画像压缩成后续状态层能用的内部信号。

它包括：

- `efficacy_signal`：学生在哪类任务上更有/更没有把握；
- `srl_fragility_signal`：规划、监控、纠错上的脆弱点；
- `control_signal`：学生觉得哪些任务可控；
- `value_signal`：学生更愿意投入哪类题；
- `directness_signal`：学生通常是直接作答、犹豫作答，还是容易猜。

这层的作用是避免后续每道题都重新读一大段画像，也避免退化成“正确率 + prompt”。

### 4.3 ProblemRequirementProfile

`ProblemRequirementProfile` 是题目需求画像。

它只使用当前题目的 OCR 文本和 EEDI subject path，不使用当前正确答案、真实学生答案、真实对错或题目经验正确率。

它描述：

- 前置知识；
- 运算复杂度；
- 抽象程度；
- 知识整合需求；
- 表征转换需求；
- 作答格式要求；
- 猜测空间；
- 常见陷阱；
- OCR / 题面格式注意事项。

当前已经额外约束：这层不能写出正确选项，不能把完整正确解法塞进 notes。

### 4.4 StudentItemInteractionDecision

`StudentItemInteractionDecision` 判断“这个学生遇到这道题，大概能走到哪里”。

它包括：

- 可达性：低于能力、部分可达、基本可达；
- 正确性区间：更可能对、不确定、更可能错；
- 可能结果；
- 可能错误类型；
- 信心上限；
- 解释深度上限；
- 判断理由。

这一步仍然是第三人称判断，不直接生成学生答案。

### 4.5 ItemResponseState

`ItemResponseState` 把交互判断进一步落到当前作答状态。

它包括：

- 前置知识熟悉度；
- 当前作答状态；
- 可达层级；
- error path；
- commitment tendency；
- explanation depth cap；
- response style guidance。

这里做了一个重要修正：

> `response_style_guidance` 只能描述学生表达方式，比如短、犹豫、直接、例子化；不能写教学提示，不能提示正确解法。

代码中已经加入检查。如果模型把 `response_style_guidance` 写成“强调正确规则 / 引导学生发现正确结论”，会显式失败并要求重生，不做静默兜底。

### 4.6 ConstraintBundle

`ConstraintBundle` 把状态边界翻译成生成约束。

它包括：

- 是否必须提交一个选项；
- 是否允许完整解释；
- 最大句数；
- 最大内部步骤数；
- 是否禁止满分式讲解；
- preferred error path；
- style constraints；
- allowed commitment；
- 输出答案空间 `1/2/3/4`。

生成后会进行 violation check。若违反约束，只允许一次显式 retry；仍失败就报错。

## 5. EEDI-static 必须适配的地方

完整迁移不等于硬套 XES 代码。

EEDI-static 必须保留自己的数据适配：

| 适配点 | XES | EEDI-static |
|---|---|---|
| 题目来源 | 结构化题库 | OCR 后 EEDI 诊断题 |
| 题型 | 多种静态题型 | 固定 4 选 1 |
| 作答表 | XES 作答序列 | EEDI long-form answer table |
| 知识点 | XES route / module | EEDI subject path |
| 图像依赖 | 默认排除图片题 | 使用 text-only clean OCR 题 |
| 学生画像来源 | 真实历史 + Hachimi/persona-like profile | 真实历史 + EEDI subject 表现构建 persona-like profile |
| 答案空间 | 依题型变化 | 固定 `1/2/3/4` |

这些是数据集适配，不是方法降级。

## 6. 反作弊边界

generation path 不允许使用：

- 当前测试题的 `CorrectAnswer`；
- 当前真实学生的 `AnswerValue`；
- 当前真实学生的 `IsCorrect`；
- 当前题目的经验正确率；
- 未来作答；
- 评测结果。

允许使用：

- 非测试历史作答；
- 当前题目 OCR 文本；
- 当前题目 subject path；
- 由这些信息构建出的第三人称中间对象。

## 7. 已完成验证

已跑通：

- 编译检查：`python -m compileall D:\Study\sii\MathStudent\static\eedi-static\src D:\Study\sii\MathStudent\static\eedi-static\run_eedi_static_benchmark.py`
- 单元测试：`python -m unittest discover -s D:\Study\sii\MathStudent\static\eedi-static\tests -v`
- dry-run：`4 students × 5 questions`，输出目录 `D:\Study\sii\MathStudent\static\eedi-static\outputs\eedi_static_benchmark\run_20260520_174917`
- 真 LLM smoke：`4 students × 2 questions`，输出目录 `D:\Study\sii\MathStudent\static\eedi-static\outputs\eedi_static_benchmark\run_20260520_180838`
- 真 LLM 小样本复测：`6 students × 6 questions`，输出目录 `D:\Study\sii\MathStudent\static\eedi-static\outputs\eedi_static_benchmark\run_20260520_214134`
- 真 LLM 中等 smoke：`20 students × 20 questions`，输出目录 `D:\Study\sii\MathStudent\static\eedi-static\outputs\eedi_static_benchmark\run_20260520_214427`

真 LLM smoke 结果只用于确认链路和格式，不代表正式效果：

| 指标 | 数值 |
|---|---:|
| n_predictions | 8 |
| real_accuracy | 0.375 |
| pred_accuracy | 0.500 |
| consistency | 0.375 |
| answer_match | 0.250 |
| item_accuracy_pearson | 1.000 |
| item_accuracy_spearman | 1.000 |

由于样本只有 `8` 条，不能解读为方法表现。

### 7.1 中等 smoke 暴露的问题与根因

`20 × 20` 中等 smoke 一共包含 `400` 个 prediction 任务。

第一轮中等 smoke 暴露了两个工程稳定性问题：

1. `ItemResponseState.response_style_guidance` 偶尔被模型写成教学建议，例如“引导学生发现规则”，这会污染生成边界；
2. `StudentAnswer` 偶尔超过句数约束，导致 violation retry 后仍失败。

针对这两个问题，已经做了三处修正：

- `response_style_guidance` 只允许描述学生表达风格，不允许写成教学提示；
- `predicted_answer` 增加 schema repair，防止模型输出 `5` 这类非法选项；
- `ConstraintBundle.max_sentences` 从过紧的 1–2 句放宽到当前的 1–5 句，其中 `none` 仍保持 1 句。

修正后，`6 × 6` 真 LLM 小样本可以零失败跑通。

随后发现最后剩余的失败根因不是模型完全失控，而是 retry 逻辑本身有反向约束：

> 初次生成时 `brief/partial/complete` 状态最多允许 5 句，但 violation retry 时 `tighten_constraints` 会把 `max_sentences` 强行改成 1。

这会导致一种不合理情况：

- 原始边界认为学生可以用几句短解释；
- 模型第一次略超句数；
- retry 反而把边界压成 1 句；
- 结果更容易继续违反 `too_many_sentences`。

这不是方法层面的失败，而是 retry 策略和 `ConstraintBundle` 不一致。

### 7.2 修复后的中等 smoke

已经完成以下代码修复：

- `tighten_constraints` 不再把 `max_sentences` 强行压到 1，而是保留原始句数边界；
- generation prompt 不再写死“exactly one short sentence”，而是要求服从 `ConstraintBundle.max_sentences`；
- `generate_prediction` 支持多次显式 generation retry，默认 `--generation_attempts 4`；
- runner 增加 task-level retry，默认 `--task_retry_attempts 2`；
- 失败记录现在包含 `student_id`、`question_id` 和错误信息；
- 如果仍有失败，会写出 `predictions_partial.jsonl`，避免成功任务白跑。

修复后，最新 `20 × 20` 中等 smoke 已经完整跑通：

| 项目 | 结果 |
|---|---:|
| 总任务数 | 400 |
| 成功任务数 | 400 |
| 失败任务数 | 0 |
| 输出目录 | `D:\Study\sii\MathStudent\static\eedi-static\outputs\eedi_static_benchmark\run_20260522_004207` |

retry 分布：

| retry_count | 数量 |
|---|---:|
| 0 | 391 |
| 1 | 7 |
| 2 | 2 |

这说明当前稳定性已经足够进入更大规模实验：绝大多数任务一次生成成功，少数任务通过显式 retry 修复，没有静默兜底。

本次 `20 × 20` 的指标如下。注意它仍只是中等 smoke，不是正式全量结果：

| 指标 | 数值 |
|---|---:|
| n_predictions | 400 |
| real_accuracy | 0.6025 |
| pred_accuracy | 0.4300 |
| consistency | 0.5325 |
| answer_match | 0.3675 |
| student_accuracy_pearson | 0.8278 |
| student_accuracy_spearman | 0.7766 |
| item_accuracy_pearson | -0.1052 |
| item_accuracy_spearman | -0.0110 |

## 8. 当前状态

当前结论：

> EEDI-static 已经完成 XES 静态元方法的第一版完整迁移，并通过 `20 × 20` 真 LLM 中等 smoke。当前代码已经具备开启更大规模实验的基本稳定性。

下一步建议：

1. 开始更大规模实验前，优先加入缓存，复用 `StudentModel`、`StudentInternalSignals` 和 `ProblemRequirementProfile`；
2. 建议先跑 `100 × 50` 或 `100 × 100`，确认端点吞吐和成本；
3. 稳定后再进入完整 `676 × 265`。
