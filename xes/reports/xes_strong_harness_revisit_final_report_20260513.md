# XES 强模型 Harness 模块必要性 Revisit 与消融实验报告（2026-05-13）

## 1. 这份报告回答什么问题

这份报告回答老师要求的那个问题：

> 在 XES 已经确定采用 strong harness 作为主线之后，我们之前设计的那一串模块，到底哪些真有必要，哪些可以简化，哪些应该删除；在做完消融实验之后，我们最后应该采用哪个版本作为当前最终版本？

这里我们不再讨论 weak harness。  
这一轮只讨论 XES strong harness。

---

## 2. 实验设置

所有实验都使用同一批固定样本：

- 学生数：`60`
- 每个学生测试题数：`96`
- 总预测任务数：`5760`
- 历史题数：`30`
- 固定 cohort：`D:\Study\sii\MathStudent\xes\configs\common_test_60x96_20260507.json`
- 并发：`50`
- 模型：`qwen`
- 输出目录：`D:\Study\sii\MathStudent\xes\outputs\xes_strong_ablation_60x96_20260512`

这样做的目的很简单：

> 让不同版本之间的差异主要来自 harness 模块本身，而不是样本波动。

---

## 3. 我们到底跑了什么

这次 revisit 分两层。

第一层是旧一轮已经跑过的主干消融，用来回答：

- 第三人称状态层能不能拿掉；
- Hachimi 有没有必要；
- difficulty 信号要不要保留；
- state-step 和 state-single 谁更合理。

第二层是这次新补的 12 个主实验，用来回答：

- `StudentInternalSignals` 是否必要；
- `StudentModel` 里的哪些字段必要；
- `ProblemRequirementProfile` 里的哪些字段必要；
- `StudentItemInteractionDecision` 能不能删；
- `ItemResponseState` 里的软字段是否必要；
- `ConstraintBundle` 当前是不是过紧。

这 12 个主实验是：

| variant | 含义 |
|---|---|
| `hachimi_no_difficulty_signal` | 新基准：保留 strong 状态链，但去掉 difficulty 信号 |
| `hachimi_no_difficulty_signal_no_internal_signals` | 完全去掉 `StudentInternalSignals` |
| `hachimi_no_difficulty_signal_minimal_signals` | 只保留少量 internal signals |
| `hachimi_no_difficulty_signal_student_capability_only` | `StudentModel` 只保留能力字段 |
| `hachimi_no_difficulty_signal_student_no_psych_fields` | 去掉心理字段 |
| `hachimi_no_difficulty_signal_student_no_style_fields` | 去掉风格字段 |
| `hachimi_no_difficulty_signal_problem_core_only` | 题目对象只保留核心结构 |
| `hachimi_no_difficulty_signal_no_problem_justifications` | 去掉题目解释字段 |
| `hachimi_no_difficulty_signal_no_problem_notes` | 去掉题目 notes |
| `hachimi_no_difficulty_signal_no_interaction_decision` | 不传 `StudentItemInteractionDecision` |
| `hachimi_no_difficulty_signal_item_state_label_only` | `ItemResponseState` 只保留状态标签和硬边界 |
| `hachimi_no_difficulty_signal_loose_constraints` | 放松 `ConstraintBundle` 约束强度 |

完整汇总表见：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md`

---

## 4. 先给结论

这轮 revisit 最重要的结论有五条。

### 4.1 第三人称状态层必须保留

只要退化成 direct 路线，指标就会明显下滑。  
这说明 strong harness 真正的核心不是 prompt 里“像学生一点”，而是：

> 先做第三人称状态判断，再在状态边界内生成学生答案。

所以：

- `StudentItemInteractionDecision`
- `ItemResponseState`
- `ConstraintBundle`

这一组状态层对象必须保留。

### 4.2 difficulty 信号已经可以从默认主线拿掉

之前的补充实验已经说明：

- difficulty 信号对 `item-level` 有帮助；
- 但它会伤 `overall_consistency`；
- 去掉两类 difficulty 信号后，strong 主线整体更稳。

所以当前 XES strong 默认主线已经更新为：

> `hachimi_no_difficulty_signal`

也就是：

- 不传 `difficulty_anchor_context`
- 不传 `real_difficulty_band`

### 4.3 `StudentInternalSignals` 不是强必要模块

对比基准：

- `hachimi_no_difficulty_signal`
  - `consistency = 0.6913`
  - `student_P = 0.6701`
  - `student_S = 0.6843`

- `hachimi_no_difficulty_signal_no_internal_signals`
  - `consistency = 0.6847`
  - `student_P = 0.7017`
  - `student_S = 0.7276`

这说明：

> 去掉 internal signals 后，consistency 只小幅下降，但学生层级对齐明显更好。

所以它不能再被叫做“核心必要模块”。  
更准确的说法是：

> 它只是一个可疑辅助层。

### 4.4 `StudentItemInteractionDecision` 不能删

`hachimi_no_difficulty_signal_no_interaction_decision` 的表面数值看起来很高：

- `accuracy = 0.8227`
- `consistency = 0.7245`

但它同时出现了：

- `item_P = 0.1441`
- `student_P = 0.1572`
- `failure_rate = 0.0276`

这不是变好了，而是变粗了。  
也就是说模型更像在用一种统一模板答题，所以表面对错率会虚高，但学生差异和题目结构都丢掉了。

所以：

> `StudentItemInteractionDecision` 是硬必要模块，不能删。

### 4.5 当前默认 `ConstraintBundle` 太紧了

这是这轮最重要的新发现。

`hachimi_no_difficulty_signal_loose_constraints` 的结果是：

- `accuracy = 0.7655`
- `consistency = 0.7134`
- `item_P = 0.2899`
- `item_S = 0.3497`
- `student_P = 0.7080`
- `student_S = 0.7404`

和当前基准 `hachimi_no_difficulty_signal` 相比，它在主要指标上是整体更强的。

这说明问题不在“要不要约束”，而在：

> 我们当前默认的约束写得太紧了。

因此，接下来最值得继续推进的不是再删外围模块，而是：

> 重做 `ConstraintBundle` 的约束强度。

---

## 5. 各模块必要性结论

| 模块 | 当前结论 | 说明 |
|---|---|---|
| 第三人称状态层 | 必要 | direct 版本整体显著下滑 |
| `StudentItemInteractionDecision` | 必要 | 删掉后 item-level 和 student-level 近乎崩掉 |
| `ItemResponseState` | 必要 | 状态标签本身必须保留 |
| `ConstraintBundle` | 必要 | 但当前默认实现过紧 |
| Hachimi persona | 条件必要 | 对 item-level 有帮助，但不是 consistency 的硬前提 |
| difficulty 信号 | 不再进默认主线 | 对 item-level 有帮助，但伤 consistency |
| `StudentInternalSignals` | 非强必要 | 更像辅助层，可去掉 |
| `StudentModel` 整体 | 必要 | 不能退化成纯能力向量 |
| `StudentModel` 心理字段 | 条件必要 | 去掉后整体会受伤，但不是最硬核心 |
| `StudentModel` 风格字段 | 偏必要 | 对当前生成边界更直接 |
| `ProblemRequirementProfile` 整体 | 必要 | 题目对象不能删 |
| problem justifications | 可简化 | 去掉后没有明显伤害 |
| problem notes | 偏必要 | 去掉后 consistency 和 student-level 明显变差 |
| state-step | 条件必要 | 仍有价值，但不再默认比 single-step 更优 |

---

## 6. 我们的当前最终版本

在做完这轮 revisit 和消融之后，我建议当前 XES strong harness 的最终版本更新为：

> `hachimi_no_difficulty_signal_loose_constraints`

它的关键指标是：

- `accuracy = 0.7655`
- `consistency = 0.7134`
- `item_P = 0.2899`
- `item_S = 0.3497`
- `student_P = 0.7080`
- `student_S = 0.7404`

这个版本的含义是：

- 保留 strong harness 的第三人称状态链；
- 保留 `StudentModel`、`ProblemRequirementProfile`、`StudentItemInteractionDecision`、`ItemResponseState`、`ConstraintBundle`；
- 默认不再传 difficulty 信号；
- 当前不把 `StudentInternalSignals` 视为核心模块；
- 不再使用过紧的 strict constraints，而改用更松的约束版本。

更直白地说，当前最终版本的核心思想是：

> 保留真正必要的状态层，把无效或副作用更大的外围模块拿掉，同时放松过度保守的生成边界。

---

### 6.1 给项目组成员的默认运行配置

为了避免后续协作时大家被消融开关绕晕，这里把当前 XES strong harness 最终版的默认配置固定下来。

如果目标是复现或继续推进当前主线，请使用下面这一组配置：

| 开关 | 最终版取值 | 含义 |
|---|---|---|
| `method_variant` | `state_step` | 保留第三人称状态链，并按步骤生成学生答案 |
| `response_persona` | `first` | 最终回答仍以学生第一人称输出 |
| `enable_difficulty_anchor_context` | `false` | 不再向模型暴露 difficulty anchor 对照信息 |
| `enable_real_difficulty_band` | `false` | 不再直接告诉模型真实难度档位 |
| `constraint_mode` | `loose` | 使用更松的生成边界，避免 strict constraints 过紧 |
| `interaction_decision_mode` | `full` | 保留 `StudentItemInteractionDecision`，不能关 |
| `item_state_fields_mode` | `full` | 保留完整 `ItemResponseState`，不能只留标签 |
| `student_model_fields_mode` | `full` | 保留完整 `StudentModel` |
| `problem_profile_fields_mode` | `full` | 保留完整 `ProblemRequirementProfile` |
| `internal_signals_mode` | `full` | 默认仍生成 internal signals，但它不是核心必要模块 |
| `violation_retry_mode` | `off` | 当前最终版不依赖 violation retry 做后处理 |
| `max_thinking_steps` | `12` | 保持当前 state-step 预算 |

也就是说，协作成员不要默认跟进那些名字里带 `no_internal_signals`、`student_capability_only`、`problem_core_only`、`no_interaction_decision`、`item_state_label_only` 的消融版本。那些版本只用于证明模块必要性，不是当前主线。

当前主线的命令形态应当是：

```powershell
python xes/run_student_conditioned_benchmark.py `
  --method_variant state_step `
  --response_persona first `
  --constraint_mode loose `
  --internal_signals_mode full `
  --student_model_fields_mode full `
  --problem_profile_fields_mode full `
  --interaction_decision_mode full `
  --item_state_fields_mode full `
  --violation_retry_mode off `
  --no-enable_difficulty_anchor_context `
  --no-enable_real_difficulty_band
```

如果只想记一句话，就是：

> XES 当前最终源码版本 = `state_step + Hachimi + no difficulty signal + full state objects + loose constraints`。

## 7. 为什么最终版本不是旧 baseline

需要单独说明一下。

旧的 `baseline_hachimi_state_step` 仍然有一个优点：

- 它的 `item_P = 0.3469`
- `item_S = 0.3990`

在题目层结构上它依然更强。

但它的问题也很明确：

- `accuracy = 0.6939`
- `consistency = 0.6703`
- `student_P = 0.6757`
- `student_S = 0.6936`

都不如我们最后选出来的 `hachimi_no_difficulty_signal_loose_constraints`。

所以如果目标是“题目难度结构的最强 item-level checkpoint”，旧 baseline 还有保存价值。  
但如果目标是：

> 当前 XES strong harness 的综合主线版本

那么更合适的选择已经变成：

> `hachimi_no_difficulty_signal_loose_constraints`

---

## 8. 最终一句话结论

这轮老师要求的 revisit 可以收束成一句话：

> XES strong harness 真正必须保留的是第三人称状态层，而不是一堆外围辅助模块；在做完模块必要性消融之后，我们当前的最终版本应更新为 `hachimi_no_difficulty_signal_loose_constraints`。
