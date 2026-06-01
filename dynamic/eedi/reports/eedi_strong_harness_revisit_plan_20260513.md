# EEDI 强模型 Harness 模块必要性 Revisit 计划（2026-05-13）

## 1. 这次 revisit 要回答什么问题

XES 那边我们已经做过一轮 revisit，发现了两件事：

- 有些看起来“合理”的模块，拿掉以后不一定变差；
- 有些约束默认写得太紧，反而在伤主指标。

现在 EEDI 既然也已经确定以 strong harness 为主线，我们就要回答同一个问题：

> 在 EEDI 这条长链路 turn-level 学生模拟里，当前 strong harness 的哪些部分是元方法的硬骨架，哪些只是局部实现，哪些值得继续保留，哪些应该放松，哪些可能应该拿掉？

---

## 2. 这次 revisit 不会碰什么

这次 revisit **不是**：

- 把 EEDI 退化成 `history -> direct student turn`；
- 为了跑分把未来信息塞回 generation path；
- 把官方标注偷偷带进生成；
- 用 prompt 补丁代替对象层分析。

这次 revisit 必须始终保留同一个元方法骨架：

> `可见历史 -> 第三人称状态层 -> 约束编译 -> 当前学生回合生成`

也就是说，我们 revis​it 的不是“要不要第三人称状态层”，而是：

- 第三人称状态层内部哪些辅助层真的有用；
- 状态到约束的编译是不是过紧；
- 生成后的违规审查和重试层是不是必要。

---

## 3. 我们当前认定的元方法骨架

EEDI strong 当前实际主链路是：

`DialogueContextState -> StudentContextProfile -> TutorTurnProfile -> InteractionState -> StateTransitionPrediction -> ErrorBlueprint -> ConstraintBundle -> StudentTurn`

这条链路里：

- `DialogueContextState`：只整理当前 turn 之前可见的信息；
- `StudentContextProfile`：第三人称判断学生当前倾向；
- `TutorTurnProfile`：第三人称判断 tutor 这一轮到底在干什么；
- `InteractionState`：判断学生此刻所处交互状态；
- `StateTransitionPrediction`：预测 tutor 这一轮后学生会被推进到什么局部状态；
- `ErrorBlueprint`：如果要错，错会以什么局部机制外显；
- `ConstraintBundle`：把状态翻译成生成边界；
- `StudentTurn`：只生成当前这一轮学生回复。

这就是我们想跨任务保住的元方法骨架。

---

## 4. 为什么 EEDI revisit 不需要和 XES 得到一模一样的最优结论

XES 上我们发现：

- 不要暴露 difficulty 信号；
- 默认 `ConstraintBundle` 太紧。

EEDI 上很可能会得到：

- 有些群体先验是有用的；
- 有些约束也太紧；
- 但某些违规审查层可能是必要的。

这不构成“不是同一种方法”。

更准确地说：

- **元方法层**要求相同：都必须先做第三人称状态判断，再把状态编译成约束，再做受限生成；
- **任务适配层**允许不同：XES 和 EEDI 面对的任务结构不同，所以最佳局部实现不必一样。

---

## 5. 第一轮优先 revisit 哪些模块

这次先不一口气把所有字段都拆开。

先做三类最高价值 revisit：

### 5.1 Population Calibration 层

问题：

> 群体校准到底是在帮 EEDI，还是在把模型推向过度“群体化”的错误？

原因：

- 它是当前 strong 主线中最干净、最容易切换的辅助层；
- 它最接近 XES 里“difficulty 信号”那种额外先验；
- 它会同时影响 `StudentContextProfile`、`InteractionState`、`StateTransitionPrediction`、`ErrorBlueprint`。

首轮实验：

- `baseline_pc_default`
- `no_population_calibration`

### 5.2 ConstraintBundle 强度

问题：

> 当前 EEDI strong 的生成边界是不是也写得过紧了？

原因：

- `ConstraintBundle` 现在会控制句数、步数、是否允许完整推理、是否必须保留局部困惑、是否必须保留局部错误连续性；
- 这和 XES 里已经证实“可能过紧”的模块最相似；
- 它非常可能直接影响 `consistency` 和 `error_realization`。

首轮实验：

- `baseline_pc_default`
- `pc_loose_constraints`

### 5.3 违规审查 / 重试层

问题：

> 当前 strong 的“硬规则检查 + LLM 违规审查 + tightened retry”到底有没有必要？

原因：

- 这一层在 EEDI strong 里是真正在工作的；
- 它可能在帮我们压越界输出；
- 也可能在把回复压得过于保守。

首轮实验：

- `baseline_pc_default`
- `pc_no_retry`
- `pc_hard_violation_only`

---

## 6. 第一轮实验矩阵

先跑 1000-task revisit block，而不是直接上 4334 全量。

原因很简单：

- 先看趋势；
- 先确认开关实现没问题；
- 先确认 detached eval 能稳定跑完；
- 再决定哪些版本值得上全量。

第一轮 5 个版本：

| version | 改动 | 想回答的问题 |
|---|---|---|
| `baseline_pc_default` | 当前 strong 1000-task 基线 | 做对照 |
| `no_population_calibration` | 关闭 population calibration | 群体先验是否必要 |
| `pc_loose_constraints` | 放松 `ConstraintBundle` | 当前约束是否过紧 |
| `pc_no_retry` | 关闭 violation 后的重试 | retry 是否必要 |
| `pc_hard_violation_only` | 关闭 LLM violation review，只保留硬规则 | LLM 审查层是否必要 |

---

## 7. 评测口径

这次不看 embedding，不讨论表面相似度。

主看五个指标：

- `consistency`
- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

其中优先级最高的是：

1. `consistency`
2. `error_realization`
3. 其余三项错误解释指标

同时辅助看：

- `retries`
- `remaining_violations`
- generation 成功率

---

## 8. 第一轮结束后的判定规则

如果一个版本：

- `consistency` 提升明显；
- `error_realization` 不明显受损，或反而更高；
- 剩余 violation 没有灾难性上升；

那么它就是值得继续推进的候选版本。

如果一个版本：

- 只是让输出更“安全”；
- 但 `consistency` 和 `error_realization` 都掉；

那它就是保守但没价值的层。

如果一个版本：

- 拿掉后指标几乎不变；

那它就是“非强必要模块”。

---

## 9. 第二轮预告

如果第一轮确认三件事中的某些方向成立，第二轮再做更细的字段级 revisit：

- `StudentContextProfile`：哪些心理分析字段真在起作用；
- `TutorTurnProfile`：哪些 tutor move 字段是必要的；
- `InteractionState / StateTransitionPrediction`：哪些状态标签是必要的；
- `ErrorBlueprint`：详细错误结构是否都需要保留。

但这一步必须建立在第一轮先跑清楚之后。

---

## 10. 当前执行顺序

接下来按这个顺序做：

1. 实现 revisit 开关；
2. 先跑小样本烟测；
3. 跑 1000-task 第一轮 5 个版本；
4. 读取 detached eval 结果；
5. 写 block1 报告；
6. 再决定第二轮要不要做更细字段级 revisit。

