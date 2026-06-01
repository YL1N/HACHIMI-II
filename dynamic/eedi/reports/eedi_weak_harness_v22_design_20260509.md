# EEDI 弱模型 Harness v2.2 设计说明（2026-05-09）

## 1. 这次为什么改

v2.1 的方向是对的：不再把强模型 `ErrorBlueprint` 直接喂给弱模型，所以不会像 v2 那样过度造错。

但 v2.1 的问题也很清楚：

- 它把“是否应该出现具体数学错误”的闸门收得太窄；
- gold 里可编码数学错误有 `112` 条，但弱侧只判了 `27` 条为 `codable_math_error`；
- 即使弱侧判了 `codable_math_error`，表面生成也可能把错误洗白成正确表达。

所以 v2.2 不回到 v2 的强控错误，而是在 v2.1 上补一层：

> 先判断这一轮是否自然允许学生做一个局部数学尝试，再让弱模型在这个尝试空间里自己出手。

这层叫：

- `MathClaimAffordanceState`
- 中文意思是“局部数学 claim 机会状态”

它不决定答案对错，只决定：

- 当前学生是否应该只是回应 / 求澄清；
- 是否可以试着说一个局部数学判断；
- 是否大概率会说一个局部数学判断；
- 这个判断有没有自然出错机会。

## 2. 理论依据

这次不是加 prompt 补丁，而是把理论位置拆清楚。

### 2.1 ZPD / 动态评估

ZPD 关心的是学生在帮助下当前能做到什么，而不是未来学会以后能做到什么。

所以 v2.2 先判断：

> 当前 tutor 这句话，是否真的把学生推到了“能做一个局部数学动作”的范围内。

如果没推到，就不硬造数学答案。

如果推到了，就允许弱模型自然尝试，而不是继续被“不要 invent error”压住。

### 2.2 Scaffolding

支架不是替学生做题，而是让学生能在某个局部点上行动。

所以 v2.2 不问：

> 这题该不该错？

而是问：

> 这个支架现在打开了哪个局部动作？

### 2.3 ICAP

ICAP 区分学生只是被动听、主动注意、自己生成、还是互动建构。

所以 v2.2 把“是否应该有数学 claim”从 `support_uptake` 里单独拆出来：

- 只是注意到了：可以回应或求澄清；
- 已经能局部生成：应该允许数学 claim；
- 能局部生成但不稳：允许自然错误出现。

### 2.4 Newman / Radatz

Newman 和 Radatz 只在“已经有具体错误机会”时使用。

它们负责描述：

- 错在读题、理解、转化、过程、编码哪个环节；
- 错误机制是前置知识不足、错误联想、无关规则等。

它们不负责强行决定学生必须错。

## 3. v2.2 链路

当前 v2.2 链路是：

1. `StudentContextProfile`
   - 从历史里抽学生稳定互动特征。
2. `TutorTurnProfile`
   - 判断 tutor 当前这一轮在要求什么。
3. `LearningAccessState`
   - 判断学生在当前支架下能不能接近这个局部目标。
4. `SupportUptake`
   - 判断学生会怎样吸收 tutor 的支持。
5. `MathClaimAffordanceState`
   - 新增层。
   - 判断下一轮是否自然会出现局部数学 claim，以及有没有自然出错机会。
6. `LocalErrorRealizationState`
   - 只在 claim 机会存在时，判断是否可能形成具体可编码错误。
7. `TeachingSupportPacket`
   - 把前面状态编译成弱模型可执行边界。
8. `WeakTurnPlan`
   - 弱模型先做一个局部回复计划。
9. `WeakStudentTurn`
   - 弱模型再把计划表面化成学生回复。
10. `LearningStateUpdate`
   - 根据生成回复更新后续状态。

## 4. 和 v2.1 的关键差别

### 4.1 不再把“没有错误蓝图”理解成“不能做数学 claim”

v2.1 里，如果 `local_error_state=no_specific_error`，packet 会写：

> 不要 invent 具体数学错误。

这个规则本身没错，但它会让弱模型过于保守。

v2.2 改成：

- 如果没有数学 claim 机会：不要 invent 错误；
- 如果有可能做数学 claim：可以试一个局部判断，但不预设错法；
- 如果应该做数学 claim：必须允许弱模型自然出手，不能把它洗成纯回应。

### 4.2 强模型错误蓝图彻底退出生成路径

v2.2 中，强版 `ErrorBlueprint` 只在生成之后构建，用于分析对照。

它不进入：

- `MathClaimAffordanceState`
- `LocalErrorRealizationState`
- `TeachingSupportPacket`
- `WeakTurnPlan`
- `WeakStudentTurn`

这样避免“强模型提前写好错误，弱模型照演”的问题。

### 4.3 表面生成不再轻易洗白错误

如果 packet 要求 `codable_math_error`，现在校验会检查：

- plan 是否标记 `realizes_error=true`；
- 表面回复是否保留 `wrong_claim_seed` 的关键方向；
- 不能只靠一个被洗白后的 `plan_claim` 通过校验。

## 5. 反作弊边界

v2.2 没有使用：

- 真实下一轮学生回复；
- 官方 correctness 标签；
- 官方错误标签；
- detached eval 结果；
- 未来对话。

新增的 `MathClaimAffordanceState` 只看：

- 当前之前可见历史；
- 题目和 subject；
- 当前 tutor 轮；
- 已经生成的第三人称状态。

所以它不是贴答案，也不是贴指标。

## 6. 预期效果

v2.2 目标不是单独把 `error_realization` 拉高。

它要拉的是更合理的组合：

- `consistency` 不应像 v2 那样大幅掉；
- `error_realization` 应该高于 v2.1；
- `same_mechanism` 不应靠强模型蓝图硬撑；
- `same_locus` 和 `same_knowledge` 要看自然错误是否更接近真实学生。

如果 v2.2 生效，最先应该看到：

- `pred_codable_math_error_rows` 回升；
- `n_both_codable_math_error_rows` 回升；
- 但 `pred_distribution.incorrect` 不应像 v2 那样过度膨胀。

## 7. 当前改动文件

- `eedi/src/weak_harness.py`
  - 新增 `MathClaimAffordanceState`
  - 新增 `resolve_math_claim_affordance(...)`
  - packet 加入 `claim_affordance / error_opportunity / expected_claim_shape`
  - 强化“有 claim 机会时允许自然局部尝试”
- `eedi/src/weak_generation.py`
  - plan 和 surface generation 都读取 `math_claim_affordance`
  - 修正 codable error 的表面校验，减少错误被洗白
- `eedi/run_eedi_weak_harness.py`
  - v2.2 链路接入 `MathClaimAffordanceState`
  - 强版 `ErrorBlueprint` 移到生成之后，只做分析对照
- `eedi/src/prompts.py`
  - 新增 claim 机会判断 prompt
  - 更新本地错误判断和弱模型生成 prompt

## 8. 本地验证

已通过：

- `python -m py_compile eedi\src\weak_harness.py eedi\src\weak_generation.py eedi\run_eedi_weak_harness.py eedi\tests_smoke_weak_harness.py eedi\tests_smoke_weak_harness_ablation.py`
- `python eedi\tests_smoke_weak_harness.py`
- `python eedi\tests_smoke_weak_harness_ablation.py`

当前没有直接跑真实 7B 小样本，因为本机当前没有检测到 `DASHSCOPE_API_KEY` 环境变量。
