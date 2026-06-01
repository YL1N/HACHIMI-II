# EEDI strong harness revisit：block9 `ConstraintBundle` 字段级计划（2026-05-15）

## 1. 这一轮回答什么问题

block8 已经说明：

> 当前 EEDI strong 主线里，`ErrorBlueprint` 不需要默认强依赖具体 `wrong_claim_seed` 或具体 `buggy_rule`；保留错误结构层更稳。

但这留下了一个新问题：

> 错误结构层后面，还要经过 `ConstraintBundle` 翻译成生成边界。到底是哪些约束在帮忙，哪些约束反而把学生回复压得太硬？

所以 block9 不再继续拆 `ErrorBlueprint`，而是拆 `ConstraintBundle`。

---

## 2. 为什么要在 `error_structure_only` 上测

本轮不是重新比较原始 baseline，而是在 block8 的当前候选主线基础上继续诊断。

因此默认底座是：

`error_blueprint_mode = structure_only`

也就是：

- 保留 `error_presence`
- 保留 `newman_error_locus`
- 保留 `radatz_error_mechanism`
- 不默认强依赖具体 `buggy_rule`
- 不默认强依赖具体 `wrong_claim_seed`

这样做的原因很简单：

> 如果还在完整 `ErrorBlueprint` 上测约束，会把“错误蓝图字段是否必要”和“约束翻译是否过紧”混在一起。

---

## 3. 本轮版本

| version | 改动含义 |
|---|---|
| `original_baseline_pc_default` | 原始 strong population-calibrated baseline，用作历史参照 |
| `candidate_structure_default` | block8 当前候选主线：`structure_only + default constraints` |
| `constraint_no_specific_error_realization` | 不强制一定外显具体数学错误 |
| `constraint_no_local_wrong_claim_anchor` | 不要求回复锚定到局部 wrong-claim |
| `constraint_no_commitment_style` | 去掉强承诺风格约束，统一偏 tentative |
| `constraint_no_style_constraints` | 大幅移除表层风格约束，只保留长度和必要错误边界 |
| `constraint_minimal_length_only` | 只保留最小长度 / 禁止未来信息 / 禁止 tutor 化等底线约束 |

---

## 4. 关键假设

### 4.1 `must_realize_specific_error`

如果去掉后：

- `consistency` 上升；
- 但 `error_realization` 下降；

说明它确实帮助错误外显，但也可能导致过度犯错。

### 4.2 `must_anchor_to_local_wrong_claim`

如果去掉后指标变好，说明：

> 当前局部 wrong-claim 锚点可能太窄，把回复压到不自然的错误句子上。

如果去掉后 `error_realization` 明显下降，说明：

> 局部锚点仍然是错误外显的重要支架。

### 4.3 `required_commitment_style`

如果去掉强承诺风格后指标变好，说明：

> 之前对“学生应该多确定 / 多犹豫”的表层控制太硬。

### 4.4 `style_constraints`

如果大量去掉 style constraints 后指标变好，说明：

> 不是状态层错，而是状态到回复的表层翻译太重。

如果指标下降，说明：

> 风格约束不是摆设，它在防止强模型过度解释、过度 tutor 化。

### 4.5 `minimal_length_only`

这个版本是压力测试。

如果它不崩，说明大部分约束可能冗余。

如果它崩，说明：

> `ConstraintBundle` 仍然是第三人称状态层落到学生回复的必要边界。

---

## 5. 运行设置

先跑：

1. `40-task smoke`
2. `1000-task screening`

暂不直接全量 4334。

原因：

- block9 是字段级审计；
- 1000 screening 足够先判断方向；
- 只有明显优于当前候选主线的版本，才值得继续上 4334。

运行脚本：

- `D:\Study\sii\MathStudent\eedi\run_strong_revisit_block9_20260515.ps1`

输出目录：

- smoke：`D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block9_smoke_20260515`
- 1000 screening：`D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block9_1000_20260515`

---

## 6. 判断标准

本轮主要看五项指标：

- `consistency`
- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

优先级是：

1. 不能牺牲 `consistency`；
2. 不能让 `error_realization` 明显坍塌；
3. 如果两者接近，再看 `same_locus` 和 `same_mechanism`；
4. 如果只是工程稳定性更好，但教育指标更差，不作为主线优化。

---

## 7. 本轮预期产物

跑完后写：

- `D:\Study\sii\MathStudent\eedi\reports\eedi_strong_revisit_block9_constraint_bundle_results_20260515.md`

报告需要给出：

1. 哪些约束必要；
2. 哪些约束过紧；
3. 哪个版本是否值得上 4334；
4. EEDI strong 当前最终主线是否应该从 `default constraints` 改成某个更轻的约束版本。
