# EEDI strong harness 字段级 revisit：block2 计划（2026-05-14）

## 1. block2 要回答什么

block1 已经告诉我们：

- `population calibration` 先别删；
- `ConstraintBundle` 先别放松；
- `retry` 和 `LLM violation review` 先别删。

所以 block2 不再折腾外围工程层，而是直接问：

> 第三人称状态层内部，这些对象到底要多“厚”才有必要？

---

## 2. 这轮要 revis​it 的模块

### 2.1 `StudentContextProfile`

问题：

> 心理分析字段是不是都必要，还是只保留行为/表达倾向就够了？

实验：

- `student_behavioral_only`
  - 保留 `engagement_tendency_analysis`
  - 保留 `response_style_analysis`
  - 屏蔽 `self_efficacy` / `SRL` / `control_value`

### 2.2 `TutorTurnProfile`

问题：

> tutor move 是不是只需要粗粒度核心字段？

实验：

- `tutor_core_only`
  - 保留 `support_type`
  - 保留 `target_of_intervention`
  - 保留 `elicited_response_process`
  - 保留 `elicited_response_target_type`
  - 保留 `elicited_object_description`
  - 把 intensity / granularity / contingency / responsibility / uptake 统统压成中性粗粒度

### 2.3 `InteractionState` + `StateTransitionPrediction`

问题：

> 真正直接驱动生成边界的，是不是只需要少数核心状态标签？

实验：

- `interaction_transition_core_only`
  - 保留：
    - misconception
    - attempt readiness
    - engagement
    - commitment
    - maturity cap
    - trajectory shift
  - 压平：
    - competence
    - metacognition
    - help internalization
    - help seeking

### 2.4 `ErrorBlueprint`

问题：

> detailed blueprint 是不是只需要保留结构，不需要保留过细 seed？

实验：

- `error_structure_only`
  - 保留 `error_presence`
  - 保留 `newman_error_locus`
  - 保留 `radatz_error_mechanism`
  - 把 `buggy_rule` / `wrong_claim_seed` 压成结构占位

---

## 3. 组合实验

除了单模块 revis​it，还要做一个组合版本：

- `lean_state_stack`

它同时启用：

- `student_behavioral_only`
- `tutor_core_only`
- `interaction_transition_core_only`
- `error_structure_only`

目的不是立刻替代 baseline，而是看：

> 当第三人称状态层整体被压薄一圈后，EEDI strong 的主指标会不会明显掉。

---

## 4. full 4334 实验矩阵

本轮直接上全量 `4334` task。

| version | 含义 |
|---|---|
| `baseline_pc_default` | 当前 strong 全量基线 |
| `student_behavioral_only` | 只保留学生行为/风格层 |
| `tutor_core_only` | tutor move 只保留核心字段 |
| `interaction_transition_core_only` | 状态与状态转移只保留核心标签 |
| `error_structure_only` | 错误蓝图只保留结构层 |
| `lean_state_stack` | 四层一起压薄 |

---

## 5. 判定逻辑

这轮最重要的问题不是谁单项最高，而是：

1. 哪些对象压薄后几乎不掉？
2. 哪些对象一压薄，`consistency` 就掉？
3. 哪些对象主要影响 `error_realization`？
4. 哪些对象只是解释好看，但实际不决定生成？

如果某个对象压薄后：

- `consistency` 基本不掉；
- 其余四项也变化很小；

那它就不该再被当成“厚重核心模块”。

如果某个对象一压薄：

- `consistency` 或 `error_realization` 明显下滑；

那它就是当前 EEDI 元方法里的真核心层。

