# XES 强模型 Harness Revisit 全序列报告（2026-05-13）

## 1. 这轮报告回答什么问题

这轮不是再证明 XES strong harness 有没有用。

这轮要回答的是：

> 在已经确认 strong 是 XES 主线之后，之前那一串模块到底哪些真有必要，哪些只是看起来合理，哪些可以删，哪些应该放松？

这里我们只看同一批 `60 x 96 = 5760` 任务上的统一对照结果。

当前这轮的比较基准不是老的 `baseline_hachimi_state_step`，而是已经更新过的主线：

> `hachimi_no_difficulty_signal`

也就是：

- 保留 Hachimi
- 保留第三人称状态链
- 去掉 `difficulty_anchor_context`
- 去掉 `real_difficulty_band`

---

## 2. 这轮一共跑了哪些实验

### 2.1 基准

| variant | 含义 |
|---|---|
| `hachimi_no_difficulty_signal` | 当前 revisit 基准 |

### 2.2 Internal signals

| variant | 含义 |
|---|---|
| `hachimi_no_difficulty_signal_no_internal_signals` | 完全不传 `StudentInternalSignals` |
| `hachimi_no_difficulty_signal_minimal_signals` | 只保留 `srl_fragility_signal` 和 `directness_signal` |

### 2.3 StudentModel 字段

| variant | 含义 |
|---|---|
| `hachimi_no_difficulty_signal_student_capability_only` | 只保留数学任务能力字段 |
| `hachimi_no_difficulty_signal_student_no_psych_fields` | 去掉自我效能、SRL、control-value |
| `hachimi_no_difficulty_signal_student_no_style_fields` | 去掉 engagement 和 directness |

### 2.4 ProblemRequirementProfile 字段

| variant | 含义 |
|---|---|
| `hachimi_no_difficulty_signal_problem_core_only` | 只保留题目核心结构 |
| `hachimi_no_difficulty_signal_no_problem_justifications` | 去掉 operation / abstraction justification |
| `hachimi_no_difficulty_signal_no_problem_notes` | 去掉 notes |

### 2.5 交互判断、状态字段、约束字段

| variant | 含义 |
|---|---|
| `hachimi_no_difficulty_signal_no_interaction_decision` | 不把 `StudentItemInteractionDecision` 传给后续状态和生成 |
| `hachimi_no_difficulty_signal_item_state_label_only` | `ItemResponseState` 只保留状态标签和硬边界 |
| `hachimi_no_difficulty_signal_loose_constraints` | 放松 `ConstraintBundle`，不再过紧限制句数、解释深度和 commitment |

---

## 3. 核心结果

| variant | acc | consistency | item_P | item_S | student_P | student_S | failure_rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| `hachimi_no_difficulty_signal` | 0.7382 | 0.6913 | 0.2635 | 0.3416 | 0.6701 | 0.6843 | 0.0000 |
| `hachimi_no_difficulty_signal_no_internal_signals` | 0.7309 | 0.6847 | 0.2560 | 0.3261 | 0.7017 | 0.7276 | 0.0000 |
| `hachimi_no_difficulty_signal_minimal_signals` | 0.7286 | 0.6870 | 0.2617 | 0.3372 | 0.6722 | 0.6987 | 0.0000 |
| `hachimi_no_difficulty_signal_student_capability_only` | 0.6932 | 0.6599 | 0.2365 | 0.2972 | 0.6216 | 0.6374 | 0.0123 |
| `hachimi_no_difficulty_signal_student_no_psych_fields` | 0.7148 | 0.6877 | 0.2915 | 0.3555 | 0.6121 | 0.6627 | 0.0189 |
| `hachimi_no_difficulty_signal_student_no_style_fields` | 0.7142 | 0.6729 | 0.2810 | 0.3140 | 0.6521 | 0.6644 | 0.0050 |
| `hachimi_no_difficulty_signal_problem_core_only` | 0.7736 | 0.7097 | 0.2298 | 0.3383 | 0.6769 | 0.7295 | 0.0019 |
| `hachimi_no_difficulty_signal_no_problem_justifications` | 0.7231 | 0.6877 | 0.2746 | 0.3388 | 0.6742 | 0.7002 | 0.0090 |
| `hachimi_no_difficulty_signal_no_problem_notes` | 0.7203 | 0.6727 | 0.2285 | 0.3621 | 0.6491 | 0.6496 | 0.0069 |
| `hachimi_no_difficulty_signal_no_interaction_decision` | 0.8227 | 0.7245 | 0.1441 | 0.2389 | 0.1572 | 0.5872 | 0.0276 |
| `hachimi_no_difficulty_signal_item_state_label_only` | 0.7731 | 0.7106 | 0.2442 | 0.2656 | 0.6690 | 0.6788 | 0.0000 |
| `hachimi_no_difficulty_signal_loose_constraints` | 0.7655 | 0.7134 | 0.2899 | 0.3497 | 0.7080 | 0.7404 | 0.0000 |

---

## 4. 逐块结论

### 4.1 `StudentInternalSignals`

这层不是强必要模块。

证据是：

- 去掉后 `consistency` 只从 `0.6913` 降到 `0.6847`
- 但 `student_P` 从 `0.6701` 升到 `0.7017`
- `student_S` 从 `0.6843` 升到 `0.7276`

这说明：

> `StudentInternalSignals` 更像一个软提示层，不是决定性状态层。

它对 `consistency` 有一点帮助，但会压平学生间差异。

当前判断：

- 不建议把它当成“必须保留的核心模块”
- 可以继续保留作对照
- 后续主线完全可以考虑直接去掉它

### 4.2 `StudentModel`

`StudentModel` 整体仍然必要，但内部字段不是全都同等必要。

先看最极端的：

- `student_capability_only` 直接掉到
  - `consistency = 0.6599`
  - `student_P = 0.6216`
  - `student_S = 0.6374`

这说明：

> 只保留数学能力字段不够，学生模型不能退化成一个纯“做题能力向量”。

再看两组字段：

- 去掉心理字段后，`consistency = 0.6877`，和基准接近，但 `failure_rate = 0.0189`
- 去掉风格字段后，`consistency = 0.6729`，下降更明显

这说明：

- 心理字段不是最硬的核心，但删掉后稳定性和学生层对齐会受伤
- 风格字段对当前生成边界更直接，删除后 `consistency` 更明显下滑

当前判断：

- `math_task_capability_profile` 必留
- `StudentModel` 整体必留
- 心理字段暂定为“条件必要”
- 风格字段比心理字段更像当前主链上的有效字段

### 4.3 `ProblemRequirementProfile`

这一块的结论很有意思。

`problem_core_only` 反而拿到了：

- `consistency = 0.7097`
- `student_P = 0.6769`
- `student_S = 0.7295`

但它的 `item_P = 0.2298`，低于基准 `0.2635`。

这说明：

> 题目对象不能删，但当前题目对象里有些软字段可能太多，反而让模型分心。

再拆开看：

- 去掉 justifications 后，`consistency = 0.6877`，接近基准，`item_P = 0.2746` 还略高
- 去掉 notes 后，`consistency = 0.6727`，明显变差

这说明：

- justification 文本不是强必要字段
- `notes` 反而更有信息量，不能轻易删

当前判断：

- `ProblemRequirementProfile` 必留
- `notes` 偏必要
- justification 可疑，后续可以继续精简
- 当前题目对象存在“过厚”的嫌疑

### 4.4 `StudentItemInteractionDecision`

这个模块不能拿 `accuracy` 和 `consistency` 表面变高就误判成可删。

虽然 `no_interaction_decision` 的表面数值是：

- `acc = 0.8227`
- `consistency = 0.7245`

但同时：

- `item_P = 0.1441`
- `student_P = 0.1572`
- `failure_rate = 0.0276`

几乎全面崩掉。

这说明：

> 去掉这层后，模型更像是在用一种更粗、更统一的方式答题，所以表面对错一致率会虚高，但学生差异和题目结构都丢了。

当前判断：

- `StudentItemInteractionDecision` 是硬必要模块
- 不能删
- 也不能被更模糊的 prompt 句子替代

### 4.5 `ItemResponseState`

`item_state_label_only` 的结果是：

- `consistency = 0.7106`
- `student_P = 0.6690`
- `student_S = 0.6788`

和基准非常接近，甚至 `consistency` 更高。

但：

- `item_P = 0.2442`
- `item_S = 0.2656`

题目层结构下降明显。

这说明：

> `ItemResponseState` 的“状态标签”本身很重要，但很多软字段未必都同样重要。

当前判断：

- `response_state`、`commitment_tendency`、`explanation_depth_cap` 这一类硬边界字段偏必要
- `reachable_level`、`error_path`、`response_style_guidance` 这一类软字段需要继续做字段级审计

### 4.6 `ConstraintBundle`

这是这轮最值得记录的新发现。

`loose_constraints` 的结果是：

- `consistency = 0.7134`
- `item_P = 0.2899`
- `item_S = 0.3497`
- `student_P = 0.7080`
- `student_S = 0.7404`
- `failure_rate = 0.0000`

它几乎在所有关键面向上都比当前基准更好。

这说明：

> 约束层不是不该有，而是当前默认约束太紧了。

也就是说，问题不在 `ConstraintBundle` 这个模块本身，而在它现在的参数和收紧方式。

当前判断：

- `ConstraintBundle` 必留
- 但当前“严格版”不是最优实现
- `loose_constraints` 是下一条非常强的主线候选

---

## 5. 当前模块必要性分类

| 模块 | 当前结论 | 原因 |
|---|---|---|
| `StudentInternalSignals` | 非强必要 / 可移除 | 去掉后 consistency 只小降，但 student-level 明显更好 |
| `StudentModel` | 必要 | capability-only 明显不够 |
| `StudentModel` 心理字段 | 条件必要 | 去掉后 consistency 近似，但 failure 和 student-level 受伤 |
| `StudentModel` 风格字段 | 偏必要 | 去掉后 consistency 下滑更明显 |
| `ProblemRequirementProfile` | 必要 | 题目对象不能删 |
| problem justifications | 可疑辅助层 | 去掉后没有明显伤害，item_P 还略升 |
| problem notes | 偏必要 | 去掉后 consistency 和 student-level 都变差 |
| `StudentItemInteractionDecision` | 强必要 | 去掉后 item-level 和 student-level 近乎崩掉 |
| `ItemResponseState` 状态标签 | 必要 | label-only 仍能撑住主链 |
| `ItemResponseState` 软解释字段 | 暂不单独定论 | label-only 结果说明它们未必都必要 |
| `ConstraintBundle` | 必要 | 但当前默认约束过紧 |
| strict constraints | 应放松 | `loose_constraints` 全面更优 |

---

## 6. 当前最重要的决策更新

这轮至少能明确三件事。

第一，`difficulty` 信号已经可以从默认主线拿掉，这点继续成立。

第二，`StudentInternalSignals` 不应再被当成核心模块，它更像一个可拆的辅助层。

第三，也是这轮最大的新增发现：

> 当前强模型主线里，真正该优先 revisiting 的不是“要不要约束”，而是“约束是不是太紧了”。

所以这轮之后，最值得优先推进的新候选不再只是：

> `hachimi_no_difficulty_signal`

而是：

> `hachimi_no_difficulty_signal_loose_constraints`

它暂时是这轮 12 个实验里最值得继续追的版本。

---

## 7. 下一步建议

接下来建议按这个顺序继续：

1. 把 `loose_constraints` 作为新的强候选，再单独复跑一次确认不是偶然波动。
2. 对 `ConstraintBundle` 做字段级审计，分开看：
   - `max_sentences`
   - `allow_complete_explanation`
   - `allowed_commitment`
   - `preferred_error_path`
   - `style_constraints`
3. 对 `ItemResponseState` 的软字段做单独审计，确认哪些字段只是解释文本，哪些真的会改变生成边界。
4. 如果后续主目标更偏学生层差异建模，可以认真考虑直接去掉 `StudentInternalSignals`。

---

## 8. 一句话总结

这轮全序列 revisit 的一句话结论是：

> XES strong harness 的核心仍然是第三人称状态链；`StudentItemInteractionDecision` 不能删，`StudentModel` 和 `ProblemRequirementProfile` 不能删，但很多软字段和当前默认紧约束都值得继续压缩，其中最明确的新方向是放松 `ConstraintBundle`。
