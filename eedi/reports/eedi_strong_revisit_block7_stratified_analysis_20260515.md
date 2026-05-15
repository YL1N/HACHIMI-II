# EEDI strong harness revisit：block7 分层分析报告（2026-05-15）

## 1. 这份报告回答什么问题

block2 已经告诉我们一个新现象：

- 压薄状态层以后，`consistency` 可能上升；
- 但 `error_realization` 往往下降。

所以 block7 不再问“哪个版本总分更高”，而是问：

> 到底是哪些样本、哪些 tutor move、哪些错误类型，让 `lean_state_stack` 比 baseline 更容易判断对错；又是哪些样本，让它更难把真实错误外显出来？

---

## 2. 本次分析怎么做

本次不重新跑模型，只读取已经完成的 block2 全量结果：

- `baseline_pc_default`
- `student_behavioral_only`
- `tutor_core_only`
- `interaction_transition_core_only`
- `error_structure_only`
- `lean_state_stack`

重点先做一组最关键的对照：

> `baseline_pc_default` vs `lean_state_stack`

原因很简单：

- `baseline_pc_default` 代表当前最完整的厚状态链；
- `lean_state_stack` 代表四层一起压薄后的最强简化版；
- 它们正好对应“厚状态更能外显错误” vs “薄状态更能对齐 correctness” 这组矛盾。

分析文件：

- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block2_4334_20260514\block7_baseline_vs_lean_analysis_20260515.json:1`
- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block2_4334_20260514\block7_field_stratified_metrics_20260515.csv:1`

---

## 3. baseline 和 lean 的直接分歧有多大

在两边共同可比的 `4154` 行里：

- `lean_consistency_win = 367`
- `baseline_consistency_win = 289`
- `lean_er_win = 57`
- `baseline_er_win = 77`

这说明：

1. `lean_state_stack` 确实更常把“这一轮该不该对”判断对；
2. 但 baseline 仍然更常把真实数学错误真正落到回复里。

也就是说，block2 里看到的总表趋势不是偶然噪声，而是逐样本层面也成立。

---

## 4. lean 更容易赢 consistency 的样本长什么样

`lean_consistency_win` 最集中的几类样本是：

- `support_type = conceptual_hint`
- `support_type = answer_elicitation`
- `support_type = procedural_hint`
- `target_of_intervention = missing_step`
- `target_of_intervention = misconception`
- `elicited_response_process = employ / interpret_evaluate / formulate`

同时，它们还有几个很明显的状态特征：

- `error_presence = codable_math_error`
- `required_commitment_style = tentative`
- `response_maturity_cap = fragment_only`
- `attempt_readiness = ready_for_local_attempt`
- `turn_bucket = late_11_plus`

这组模式说明：

> 当 tutor 已经把局部目标收得比较近，学生只需要给一个短的、局部的、带犹豫的回应时，`lean_state_stack` 更容易避免“想太多”，因此 correctness 更稳。

换句话说，压薄状态层最有利的，不是社交开场，也不是完全自由回答，而是：

> tutor 已经把问题压到一个局部步骤上，学生只要做短局部尝试。

---

## 5. baseline 更容易赢 error_realization 的样本长什么样

`baseline_er_win` 最集中的几类样本是：

- `support_type = conceptual_hint`
- `support_type = procedural_hint`
- `target_of_intervention = missing_step`
- `target_of_intervention = misconception`
- `error_presence = codable_math_error`
- `newman_locus = transformation / process_skills`
- `radatz_mechanism = deficient_prerequisites / incorrect_associations`

这说明 baseline 的优势不是体现在“泛泛地更会出错”，而是：

> 当真实学生的错误已经是一个可编码的局部数学错误，而且这个错误落在 transformation / process-skills 这类可描述机制上时，厚状态链更容易把这个错稳定说出来。

尤其是：

- `incorrect_associations`
- `comprehension`
- `transformation`

这几类样本里，`lean_state_stack` 往往出现：

> correctness 对齐更好了，但错误的外显结构反而被压平了。

---

## 6. 哪些字段最值得优先 revisit

从分层结果看，下一轮最值得优先 revisit 的不是 `StudentContextProfile`，而是下面两块。

### 6.1 第一优先：`ErrorBlueprint`

原因：

- `lean_state_stack` 在 `codable_math_error` 上，`consistency` 提升；
- 但在 `incorrect_associations`、`transformation`、`comprehension` 这些真正需要“把错说具体”的场景里，`error_realization` 明显下降。

这很像：

> 压薄后的 error 层还足够判断“学生大概会错”，但已经不够支撑“学生会把哪一种错外显出来”。

所以 block8 最该做的是：

1. 在 `error_structure_only` 基础上，分别单独加回：
   - `wrong_claim_seed`
   - `buggy_rule`
   - surface realization hint
2. 看谁真正帮助 `error_realization`，谁只是解释字段。

### 6.2 第二优先：`ConstraintBundle`

原因：

- `lean_state_stack` 在 `commitment = avoidant`、`explanation_request`、`error_challenge` 上反而更稳；
- 这说明当前 baseline 里的部分约束，可能会把某些本该简短、局部、犹豫的回复拉得太“重”。

所以 block9 最该做的是细拆：

1. `required_commitment_style`
2. `max_sentences`
3. `must_anchor_to_local_wrong_claim`
4. `must_realize_specific_error`

核心问题是：

> 到底是哪一条约束在帮 baseline 把错说出来，又是哪一条约束在伤害 correctness。

---

## 7. 哪些块目前不用优先 revisit

### 7.1 `StudentContextProfile` 暂时不作为第一优先

因为这轮分层里，最大分歧主要不是社交风格类样本，而是：

- 局部数学错误
- tutor 局部提示
- 错误结构能否外显

这说明当前最核心的矛盾不在“学生长期人格画像够不够厚”，而在：

> 当前轮局部错误结构如何被压进生成边界。

### 7.2 `TutorTurnProfile` 也不是第一优先

`tutor_core_only` 的总表并不差，说明 tutor move 的粗粒度核心骨架已经比较稳。

它当然还值得继续审计，但优先级低于 `ErrorBlueprint` 和 `ConstraintBundle`。

---

## 8. 当前 block7 结论

block7 可以收成三句话：

1. `lean_state_stack` 的确更容易赢 `consistency`；
2. 但 baseline 更容易在可编码数学错误上赢 `error_realization`；
3. 这个矛盾主要集中在：
   - `codable_math_error`
   - `transformation / process_skills / comprehension`
   - `incorrect_associations / deficient_prerequisites`
   - `conceptual_hint / procedural_hint / answer_elicitation`

所以后续 revisit 不应该继续平均地拆所有对象，而应该转成：

> **优先细拆 `ErrorBlueprint` 和 `ConstraintBundle`，专门解释“为什么 correctness 提高了，但错误外显变弱了”。**

---

## 9. 下一步计划

下一轮建议直接进入：

### block8：`ErrorBlueprint` 二轮 revisit

计划版本：

- `error_structure_plus_wrong_claim_seed`
- `error_structure_plus_buggy_rule`
- `error_structure_plus_surface_hint`
- `error_structure_no_mechanism`

### block9：`ConstraintBundle` 细拆 revisit

计划版本：

- `no_commitment_style_constraint`
- `no_specific_error_realization_requirement`
- `no_local_wrong_claim_anchor`
- `minimal_length_only_constraints`

目标不是继续追一个单一总分最高版本，而是把当前矛盾拆明白：

> 哪些字段帮助判断对错，哪些字段帮助把错说出来，最后再决定 EEDI strong 主线的最终精简版结构。
