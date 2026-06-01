# EEDI strong harness revisit 最终决策报告（2026-05-19）

## 1. 这份报告回答什么问题

这份报告只回答一个最后决策问题：

> EEDI strong harness 在做完 revisit 之后，最终版到底保留原版，还是切到 `structure_only + no_commitment_style`？

答案是：

> 最终仍保留原版；revisit 候选版不进入 EEDI 最终主线。

---

## 2. 对比对象

### 2.1 原版 strong

- 版本名：`strong_population_calibrated_train200k8_structural_only`
- 结果目录：`D:\Study\sii\MathStudent\eedi\outputs\official_test_4334_strong_population_calibrated_train200k8_structural_only_20260511_minus_bad_104006_4779_turn6`

它的方法特点是：

- 完整 `ErrorBlueprint`
- default `ConstraintBundle`
- 保留 population calibration
- 4334 全量 strong 主线

### 2.2 revisit 候选版

- 版本名：`structure_only_no_commitment_style`
- 结果目录：`D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_final_candidate_structure_only_no_commitment_style_full4334_20260518`

它的方法特点是：

- `error_blueprint_mode = structure_only`
- `constraint_profile = no_commitment_style`
- 也保留 population calibration
- 也跑了 4334 全量

---

## 3. 为什么这次比较要重新对齐口径

原版 strong 当时有一个坏样本被剃掉了：

- `dialogue_id = 104006_4779`
- `turn_idx = 6`

所以原版的 detached eval 是在 `4154` 行上做的。

为了公平比较，这次把 revisit 候选版里同一个样本也剃掉，再重新跑 detached eval。

因此下面这组数字是：

> 原版 `4154` 行 vs 候选版同样 `4154` 行

是严格同口径比较。

---

## 4. 方法层面到底改了什么

revisit 候选版不是换了一套元方法。

两边都还是同一个主骨架：

`StudentModel -> DialogueContext -> TutorTurnProfile -> StudentTurnState -> ConstraintBundle -> StudentTurn`

也都保留：

- 第三人称状态层
- population calibration
- 单步生成
- 显式约束边界

真正改动只有两处：

### 4.1 `ErrorBlueprint` 从完整具体版改成结构版

候选版不再默认强依赖：

- 具体 `buggy_rule`
- 具体 `wrong_claim_seed`

而是主要保留：

- 是否有错
- 错在什么 locus
- 错误机制是什么

### 4.2 `ConstraintBundle` 去掉强承诺风格控制

候选版把：

- “这句话应该更确定”
- “这句话应该更犹豫”

这种默认强控放松掉，改成：

> 让回复的直接程度更多由局部数学状态决定，而不是被固定口吻压死。

---

## 5. 结果层面对比

### 5.1 五个核心指标

| metric | 原版 | 候选版 | delta |
|---|---:|---:|---:|
| `consistency` | `0.5773` | `0.6042` | `+0.0269` |
| `same_knowledge` | `0.7832` | `0.7367` | `-0.0466` |
| `same_locus` | `0.6713` | `0.6441` | `-0.0272` |
| `same_mechanism` | `0.6713` | `0.6548` | `-0.0165` |
| `error_realization` | `0.6034` | `0.5928` | `-0.0105` |

### 5.2 这组结果说明什么

候选版的优势很明确：

- `consistency` 更高

但代价也很明确：

- `same_knowledge` 下降
- `same_locus` 下降
- `same_mechanism` 下降
- `error_realization` 也下降

换句话说：

> 候选版更擅长对齐“这一轮该不该错”，但更不擅长把错误稳定地落在和真实学生一致的知识类型、错误位置和错误机制上。

---

## 6. 最终判断

如果只追 `consistency`，候选版是有吸引力的。

但 EEDI 当前主目标不是只做一个“对错一致性”版本，而是：

> 在 turn-level 上，既判断对错，又尽量把真实学生的局部错误机制复现出来。

在这个目标下，原版更平衡。

所以最终决策是：

> EEDI strong harness 当前最终版仍保留原版 `strong_population_calibrated_train200k8_structural_only`。

不把：

> `structure_only + no_commitment_style`

写进最终源码主线。

---

## 7. 这对 revisit 的意义

这次 revisit 不是白做。

它至少说明了两件事：

1. `consistency` 和错误结构对齐之间确实存在张力；
2. 放松承诺风格约束，确实能提升 `consistency`，但会损伤一部分错误结构复现。

所以这次 revisit 的结论不是“候选版胜出”，而是：

> 我们找到了一个很清楚的 trade-off，但它还不足以替代原版成为最终主线。

---

## 8. 当前最终版本

当前 EEDI 最终版一句话概括：

> 最终仍采用原始 strong population-calibrated 版本；revisit 候选版保留为分析版本，不作为最终交付主线。
