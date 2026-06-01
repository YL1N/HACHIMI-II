# XES 强模型 Harness 模块必要性 Revisit 计划（2026-05-12）

## 1. 这次 revisit 要解决什么问题

XES 侧现在选择 **强模型 harness** 作为最终主线。  
原因是它在 common-test 60×96 上已经取得了相对不错的结果：

- `overall_consistency = 0.6767`
- `student_P = 0.6782`
- `student_S = 0.6984`
- `item_P = 0.3013`
- `item_S = 0.3298`

但“结果不错”不等于“每个模块都必要”。  
现在要反过来审问：

> 之前设计的每个模块，到底有没有不可替代的作用？

这件事不是为了推翻现有方法，而是为了把方法变得更干净、更可解释、更能经得住老师追问。

---

## 2. 基本判断

模块必要性 revisit **不等于只做消融**。

它包含三层：

1. **理论必要性**
   - 这个模块解决了什么第一性问题？
   - 如果没有它，方法链条中哪一步会断？

2. **工程必要性**
   - 这个模块的输出有没有真的被后续使用？
   - 有没有字段只是写出来但没有进入决策？
   - 有没有和别的模块重复判断？

3. **实验必要性**
   - 拿掉它、替换它、简化它，指标会不会下降？
   - 如果不下降，说明它可能是冗余模块。
   - 如果反而上升，说明它可能正在伤害系统。

所以这次不是“证明所有模块都对”，而是允许出现四类结论：

- 必要模块：拿掉就明显变差；
- 条件必要模块：只有和某些模块组合时有用；
- 冗余模块：拿掉变化很小；
- 有害模块：拿掉反而更好。

---

## 3. 当前 XES 强模型 harness 主链路

当前主链路是：

`Student history / Hachimi persona -> StudentModel -> StudentInternalSignals -> ProblemRequirementProfile -> StudentItemInteractionDecision -> ItemResponseState -> ConstraintBundle -> State-step Generation -> Violation Check / Retry -> Evaluation`

可以拆成 8 个待审计模块：

1. 学生画像来源
2. `StudentModel`
3. `StudentInternalSignals`
4. `ProblemRequirementProfile`
5. difficulty anchor
6. `StudentItemInteractionDecision`
7. `ItemResponseState + ConstraintBundle`
8. state-step generation 与 violation retry

---

## 4. 指标优先级

这次不能只看 accuracy。

优先级如下：

1. `overall_consistency`
   - 最重要，表示逐学生逐题对错是否和真实学生一致。

2. `student_P / student_S`
   - 看是否保留学生强弱差异。

3. `item_P / item_S`
   - 看是否保留题目难度结构。

4. `acc` 与真实学生整体正确率的差距
   - accuracy 不能单独作为成功标准。
   - 如果 accuracy 高了，但 consistency 或相关性掉了，不算好。

5. failure rate
   - 如果一个模块效果好但大量失败，也不能作为稳定主线。

---

## 5. 第一阶段：理论和工程审计

先不跑实验，先做代码级和方法级审计。

### 5.1 学生画像来源

当前有两种：

- `xes_history_plus_hachimi`
- `xes_history_only`

要问：

- Hachimi 补充的是学生一般学习风格，还是引入噪声？
- XES 历史本身是否已经足够？
- Hachimi 对 `student_P/S` 是否有贡献？
- Hachimi 是否伤害 `item_P/S`？

初步判断：

- Hachimi 是“可能有用但不必然必要”的模块。
- 必须靠消融确认。

### 5.2 StudentModel

作用：

- 把 persona / 历史摘要转成学生状态对象。

要问：

- `StudentModel` 是否比直接用 history summary 更强？
- 自我效能、SRL、control-value 等字段是否真的影响后续判断？
- 这些心理字段是否只是“看起来合理”，但没有提升指标？

初步判断：

- `StudentModel` 理论上必要。
- 但其中字段可能需要精简。

### 5.3 StudentInternalSignals

作用：

- 把长文本学生模型压成更稳定的工程信号。

要问：

- 它是否真的降低了 LLM 消费负担？
- 后续状态判断是否依赖这些 signals？
- 如果直接把 `StudentModel` 给后续模块，指标是否变化？

初步判断：

- 这是“可能有用，但需要字段级消融”的模块。

### 5.4 ProblemRequirementProfile

作用：

- 把题目文本转成题目能力要求。

要问：

- 如果没有它，系统是否只能做表面题面理解？
- 它对 item-level alignment 是否有贡献？
- LLM 生成的题目画像是否稳定？

初步判断：

- 理论上必要。
- 但字段可能过多，需要看哪些字段真正进入交互判断。

### 5.5 Difficulty Anchor

作用：

- 把题目真实或估计难度纳入题目画像。

要问：

- 它是否提升 `item_P/S`？
- 它是否导致模型过度相信题目难度，从而伤害 `overall_consistency`？
- 它是否只在某些画像来源下有用？

初步判断：

- 这是最需要组合消融的模块。

### 5.6 StudentItemInteractionDecision

作用：

- 把学生能力和题目要求合成“这名学生遇到这道题会怎样”。

要问：

- 它是否真的比直接让 LLM 生成 `ItemResponseState` 更稳？
- 当前 margin 规则是否太粗？
- 它是否把好信号合成了坏判断？

初步判断：

- 理论上是核心模块。
- 但当前实现可能过于规则化，需要重点审计。

### 5.7 ItemResponseState + ConstraintBundle

作用：

- 把交互判断转成当前作答状态和生成边界。

要问：

- 它是否真的防止强模型过度解题？
- 它是否导致模型过度保守？
- `state_step` 是否明显优于 `direct`？

初步判断：

- 这是第三人称状态层的核心，需要重点消融。

### 5.8 Violation Check / Retry

作用：

- 检查输出是否越过状态边界，必要时重试。

要问：

- 它是否实际降低越界输出？
- 它是否改变了对错分布？
- 它是否只是让输出更规整，但不提升核心指标？

初步判断：

- 工程上有必要，但要确认是否影响指标。

---

## 6. 第二阶段：单模块消融

第一轮先做单模块消融，回答“某个模块独立看是否有贡献”。

### 6.1 实验矩阵

| variant | 改动 | 目的 |
|---|---|---|
| `baseline_hachimi_state_step` | 当前主线 | 基准 |
| `history_only_state_step` | 去掉 Hachimi，只用 XES 历史 | 检查 Hachimi 是否必要 |
| `hachimi_direct` | 去掉状态层，直接生成 | 检查第三人称状态层是否必要 |
| `hachimi_state_single` | 多步生成改成单步生成 | 检查 state-step 是否必要 |
| `hachimi_no_difficulty_anchor` | 去掉 difficulty anchor | 检查题目难度锚点是否必要 |
| `hachimi_third_person_response` | 第一人称改第三人称表达 | 检查输出人称是否影响判分 |

已有脚本：

- `D:\Study\sii\MathStudent\xes\run_strong_harness_ablation_60x96_20260512.ps1:1`

汇总脚本：

- `D:\Study\sii\MathStudent\xes\summarize_strong_ablation_60x96.py:1`

### 6.2 单模块判断规则

如果去掉模块后：

- `overall_consistency` 下降超过 `0.02`：倾向认为该模块有效；
- `student_P/S` 下降明显：说明模块对学生差异有贡献；
- `item_P/S` 下降明显：说明模块对题目结构有贡献；
- 指标几乎不变：模块可能冗余；
- 指标上升：模块可能有害或实现不佳。

阈值不是最终统计显著性，只是第一轮筛查标准。

---

## 7. 第三阶段：组合消融

单模块消融不够，因为模块可能有组合效应。

一个模块可能：

- 单独看没用；
- 但和另一个模块一起有用。

也可能：

- 单独看有用；
- 但和某个模块组合后反而有害。

### 7.1 组合实验矩阵

| variant | 组合 | 想验证什么 |
|---|---|---|
| `history_only_direct` | 无 Hachimi + direct | 最小链路能到什么水平 |
| `history_only_state_single` | 无 Hachimi + 单步状态生成 | Hachimi 是否只在多步状态链中有用 |
| `history_only_no_difficulty_anchor` | 无 Hachimi + 无 difficulty anchor | difficulty anchor 是否依赖 Hachimi |
| `hachimi_direct_no_difficulty_anchor` | 有 Hachimi + direct + 无 difficulty anchor | 状态层和难度锚点是否共同贡献 |
| `hachimi_state_single_no_difficulty_anchor` | 有 Hachimi + 单步 + 无 difficulty anchor | 多步生成是否依赖难度锚点 |
| `history_only_direct_no_difficulty_anchor` | 无 Hachimi + direct + 无 difficulty anchor | 极简强模型链路下限 |

### 7.2 组合判断重点

重点不是找“单项最高”的 run。  
重点是找：

> 哪个最小组合能稳定保住核心指标。

如果一个复杂组合只比简单组合高 `0.003`，它就不值得保留。  
如果一个模块只在某个组合里有效，就要把它标成“条件必要”，不能写成普遍必要。

---

## 8. 第四阶段：字段级审计

如果前两轮发现某个模块整体有效，再做字段级审计。

优先审计：

### 8.1 StudentModel 字段

候选字段：

- 自我效能
- SRL
- control-value
- engagement tendency
- response directness
- math task capability profile

问题：

- 哪些字段真的进入后续判断？
- 哪些字段只是解释文本？
- 哪些字段会引入噪声？

### 8.2 ProblemRequirementProfile 字段

候选字段：

- prerequisite knowledge
- operation complexity
- abstraction level
- knowledge integration
- representation shift
- response format demand
- guessability
- perceived difficulty

问题：

- 哪些字段直接影响 `StudentItemInteractionDecision`？
- 哪些字段只是给 LLM 看，但没有稳定作用？

### 8.3 InteractionDecision 字段

候选字段：

- predicted reachability
- predicted correctness band
- likely outcome
- likely error family
- confidence cap
- explanation cap

问题：

- 哪个字段真正影响 `ItemResponseState`？
- 当前规则是否过度简化？

---

## 9. 最终输出形式

revisit 最后应该产出一份正式报告：

- `xes/reports/xes_strong_harness_module_necessity_audit_20260512.md`

报告里每个模块都要给出结论：

| 模块 | 理论作用 | 工程证据 | 消融证据 | 结论 |
|---|---|---|---|---|
| Hachimi persona | 补充一般学习风格 | 进入 StudentModel | 待跑 | 保留/简化/删除 |
| StudentModel | 建学生状态 | 后续模块使用 | 待跑 | 保留/简化/删除 |
| ProblemProfile | 建题目要求 | 后续模块使用 | 待跑 | 保留/简化/删除 |
| DifficultyAnchor | 提供难度信号 | 进入 ProblemProfile | 待跑 | 保留/简化/删除 |
| InteractionDecision | 合成学生×题目 | 进入 ItemState | 待跑 | 保留/简化/删除 |
| ItemState/Constraint | 定义作答边界 | 进入 generation | 待跑 | 保留/简化/删除 |
| State-step generation | 控制生成过程 | 影响回答 | 待跑 | 保留/简化/删除 |
| Violation retry | 防越界 | 影响输出 | 待跑 | 保留/简化/删除 |

---

## 10. 执行顺序

建议按这个顺序做：

1. 先跑第一阶段单模块消融；
2. 汇总结果；
3. 根据结果挑组合消融，不要盲目全排列；
4. 再做字段级审计；
5. 最后写模块必要性结论。

不要一上来做所有组合。  
否则实验量太大，而且很容易变成“找最好结果”，偏离 revisit 目的。

---

## 11. 当前最关键的判断

当前最关键的不是证明 strong harness 每个模块都有用。

真正关键的是：

> 找出 XES 强模型 harness 的最小有效方法链。

如果最终发现：

- `StudentModel + ProblemProfile + ItemState` 必要；
- Hachimi 只是小幅提升；
- difficulty anchor 有条件有效；
- state-step 可能不如 state-single；

那也完全可以接受。

这说明方法变得更清楚，而不是变弱。

---

## 12. 一句话总结

这次 revisit 的目标不是给旧设计背书，而是做一次严肃的方法审计：

> 能证明必要的模块保留，不能证明必要的模块简化，拿掉更好的模块就删除。

---

## 13. 当前执行进度

### 13.1 第一块：difficulty 信号

状态：已完成。

独立报告：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_revisit_block1_difficulty_signal_20260512.md`

结论：

- `difficulty_anchor_context` 不再进入默认主线；
- `real_difficulty_band` 不再进入默认主线；
- difficulty 信号保留为离线分析和消融对照；
- 当前 XES 强模型主线更新为 `hachimi_no_difficulty_signal`。

核心证据：

- `overall_consistency = 0.6937`
- `student_P = 0.6958`
- `student_S = 0.7147`

### 13.2 下一块：StudentInternalSignals

状态：已完成。

独立报告：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_revisit_block2_internal_signals_20260512.md`

原因：

- 它目前主要作为 LLM 软提示进入后续链路；
- 没有进入硬规则；
- 可能是冗余压缩层，也可能帮助稳定状态推断。

已完成实验：

| variant | 改动 | 目的 |
|---|---|---|
| `hachimi_no_difficulty_signal` | 当前新主线 | 基准 |
| `hachimi_no_difficulty_signal_no_internal_signals` | 去掉 `StudentInternalSignals` | 检查 signals 是否必要 |
| `hachimi_no_difficulty_signal_minimal_signals` | 只保留 directness / srl 等少数字段 | 检查是否可精简 |

结论：

- full signals 的 `consistency` 最高：`0.6913`；
- no-signals 的 `student_P/student_S` 最高：`0.7017 / 0.7276`；
- `StudentInternalSignals` 不是强必要模块，只能暂时作为可疑辅助层保留。

### 13.3 下一块：StudentModel 字段

下一步优先审计 `StudentModel` 字段。

原因：

- `math_task_capability_profile` 进入 `StudentItemInteractionDecision` 的硬判断；
- 自我效能、SRL、control-value、engagement、response directness 主要作为 LLM 软输入；
- 需要判断哪些字段是真必要，哪些只是解释性文本。

建议新增实验：

| variant | 改动 | 目的 |
|---|---|---|
| `hachimi_no_difficulty_signal` | 当前 consistency 基准 | 保留完整 StudentModel |
| `hachimi_no_difficulty_signal_capability_only` | 只保留数学任务能力字段 | 检查心理/风格字段是否必要 |
| `hachimi_no_difficulty_signal_no_psych_fields` | 去掉自我效能、SRL、control-value | 检查心理字段贡献 |
| `hachimi_no_difficulty_signal_no_style_fields` | 去掉 engagement/directness | 检查风格字段贡献 |

---

## 14. 后续计划审核哪些模块

前两块已经抓出来：

- difficulty 信号：已从默认主线移除；
- `StudentInternalSignals`：不是强必要模块，暂时作为可疑辅助层保留。

接下来继续审核下面这些模块。

### 14.1 `StudentModel` 字段

它是什么意思：

> 把一个学生的历史表现和 persona，整理成“这个学生大概是什么样”的对象。

里面有两类字段：

1. 硬能力字段
   - 例如 `math_task_capability_profile`；
   - 包括计算流畅度、应用题迁移、多步稳定性、几何直觉、填空精度、猜测倾向等；
   - 这些字段会进入 `StudentItemInteractionDecision` 的硬判断。

2. 心理/风格字段
   - 例如自我效能、SRL、control-value、engagement、response directness；
   - 这些字段主要作为 LLM 软输入；
   - 它们可能有教育意义，但不一定提升当前静态单题指标。

要审核什么：

- 是否只保留硬能力字段就够了；
- 心理字段是否只是解释文本；
- 风格字段是否真的影响最终学生回答；
- 这些字段是否会把学生差异说得过度平滑。

初步判断：

> `math_task_capability_profile` 很可能必要；心理/风格字段需要字段级消融。

### 14.2 `ProblemRequirementProfile` 字段

它是什么意思：

> 把题面文字整理成“这道题到底要求什么能力”的对象。

它不是题目难度标签，而是题目结构画像。

主要字段包括：

- 前置知识；
- 操作复杂度；
- 抽象程度；
- 是否多知识点整合；
- 是否需要表征转换；
- 作答格式要求；
- 是否容易猜；
- justification / notes。

要审核什么：

- 哪些字段真的进入 `StudentItemInteractionDecision`；
- 哪些字段只是给 LLM 看的解释文本；
- justification / notes 是否有必要；
- 去掉软解释字段后，指标是否稳定。

初步判断：

> 题目结构画像本身大概率必要，但字段可能过多。

### 14.3 `StudentItemInteractionDecision`

它是什么意思：

> 把“学生能力”和“题目要求”合在一起，判断这个学生遇到这道题大概会怎样。

它回答：

- 这道题对这个学生是否可达；
- 预期是能做对、接近做对、猜测，还是不可达；
- 可能是什么错误类型；
- 答案信心和解释深度应该多高。

要审核什么：

- 当前 margin 规则是否太粗；
- `predicted_correctness_band` 是否真的有用；
- `likely_error_family` 是否稳定；
- 是否可以简化成更少的状态。

初步判断：

> 这是第三人称状态层的核心，不应删除，但实现方式可能要重审。

### 14.4 `ItemResponseState`

它是什么意思：

> 把学生-题目交互判断，翻译成“当前这道题上学生应该处于什么作答状态”。

它规定：

- 学生是否熟悉前置知识；
- 当前是 mastered / partial / guessable / unreachable；
- 可能走什么错误路径；
- 回答时能不能解释；
- 语气应该多确定。

要审核什么：

- 这些状态类别是否太多或太少；
- `reachable_level` 是否只是解释文本；
- `error_path` 是否真的影响最终回答；
- `commitment_tendency` 和 `explanation_depth_cap` 是否必要。

初步判断：

> 状态层必要，但字段需要压缩。

### 14.5 `ConstraintBundle`

它是什么意思：

> 把 `ItemResponseState` 变成具体生成边界。

它限制：

- 最多几句话；
- 最多几步内部思考；
- 是否允许完整解法；
- 是否必须提交答案；
- 是否禁止表现得像完全掌握；
- 应该偏向什么错误路径。

要审核什么：

- 哪些约束真正防止强模型过度解题；
- 哪些约束只是形式控制；
- `max_sentences` / `max_thinking_steps` 是否过紧；
- `preferred_error_path` 是否真的影响错误外显。

初步判断：

> 约束层是必要的，但约束项可能需要精简。

### 14.6 `state-step` 多步生成

它是什么意思：

> 不是让模型一次性给答案，而是让模型在状态边界内一步步决定，最后输出学生答案。

它的目的：

- 避免强模型直接解完整题；
- 让回答过程更可审计；
- 让状态边界持续约束生成。

要审核什么：

- 多步是否真的比单步好；
- 多步是否只是增加成本；
- 多步是否主要帮助 item-level，而不是 consistency；
- 是否可以改成更短的单步状态生成。

已有现象：

- state-step 更保 item-level；
- state-single 在 student-level 上有时更好。

初步判断：

> state-step 是条件必要模块，需要继续和主目标绑定判断。

### 14.7 violation check / retry

它是什么意思：

> 检查模型输出有没有越过状态边界；如果越界，就用更紧约束重试。

它防的是：

- 答案太长；
- 解释太完整；
- 猜测状态却表现得像掌握；
- 低信心状态却语气过度确定。

要审核什么：

- 它实际触发多少次；
- 触发后是否改善 consistency；
- 是否只改善格式，不改善核心指标；
- 是否会把自然学生回答压得太模板化。

初步判断：

> 工程上有用，但是否影响核心指标还要单独统计。

### 14.8 Hachimi persona

它是什么意思：

> 用外部匹配到的学生 persona 补充 XES 历史作答之外的学习风格信息。

它可能提供：

- 学习风格；
- 学科偏好；
- 参与方式；
- 回答习惯。

已有现象：

- 去掉 Hachimi 后，`consistency` 不一定下降；
- 但 item-level 结构会下降。

要审核什么：

- Hachimi 是否主要帮助题目结构，而不是学生个体；
- 它是否引入噪声；
- 当前 XES 历史是否已经足够；
- 是否只保留 Hachimi 的某些字段。

初步判断：

> Hachimi 是条件必要模块，不是主线硬必要模块。

---

## 15. 推荐审核顺序

接下来建议按这个顺序继续：

1. `StudentModel` 字段
   - 先抓硬能力字段 vs 心理/风格字段。

2. `ProblemRequirementProfile` 字段
   - 再抓题目结构字段 vs justification / notes。

3. `StudentItemInteractionDecision`
   - 审 margin 规则和状态类别。

4. `ItemResponseState + ConstraintBundle`
   - 审状态字段和约束字段能否压缩。

5. `state-step`
   - 决定是否继续保留多步生成。

6. violation check / retry
   - 最后看工程校验是否真有指标收益。

7. Hachimi persona
   - 作为组合模块复审，不单独优先。
---

## 16. 2026-05-13 连续 12 个主实验

这一轮从已经确认的新主线出发：

> `hachimi_no_difficulty_signal`：保留 Hachimi + 强模型第三人称状态链，但不再传入 difficulty anchor，也不再传入真实难度档。

这 12 个实验只做模块必要性审计，不引入真实学生标签，不按题目 ID 特判，不在生成后按评测目标改答案。

### 16.1 实验清单

| 顺序 | variant | 审核对象 | 改动 |
|---:|---|---|---|
| 1 | `hachimi_no_difficulty_signal` | 新主线基准 | 完整强模型状态链，去掉 difficulty 信号 |
| 2 | `hachimi_no_difficulty_signal_no_internal_signals` | `StudentInternalSignals` | 不把内部信号传给后续状态和生成 |
| 3 | `hachimi_no_difficulty_signal_minimal_signals` | `StudentInternalSignals` | 只保留 SRL 脆弱性和回答直接性 |
| 4 | `hachimi_no_difficulty_signal_student_capability_only` | `StudentModel` | 只保留数学任务能力，去掉心理、风格、摘要类字段 |
| 5 | `hachimi_no_difficulty_signal_student_no_psych_fields` | `StudentModel` | 去掉自我效能、SRL、控制-价值判断 |
| 6 | `hachimi_no_difficulty_signal_student_no_style_fields` | `StudentModel` | 去掉参与倾向和回答直接性字段 |
| 7 | `hachimi_no_difficulty_signal_problem_core_only` | `ProblemRequirementProfile` | 只保留核心题目结构，去掉软解释和部分细分需求 |
| 8 | `hachimi_no_difficulty_signal_no_problem_justifications` | `ProblemRequirementProfile` | 去掉复杂度、抽象度的文字理由 |
| 9 | `hachimi_no_difficulty_signal_no_problem_notes` | `ProblemRequirementProfile` | 去掉 notes |
| 10 | `hachimi_no_difficulty_signal_no_interaction_decision` | `StudentItemInteractionDecision` | 不把学生-题目交互判断传给状态层和生成层 |
| 11 | `hachimi_no_difficulty_signal_item_state_label_only` | `ItemResponseState` | 保留状态标签和硬边界，去掉 error path / style guidance 等软字段 |
| 12 | `hachimi_no_difficulty_signal_loose_constraints` | `ConstraintBundle` | 放松句数、解释深度、commitment 等生成边界 |

### 16.2 运行方式

主脚本：

`D:\Study\sii\MathStudent\xes\run_strong_harness_ablation_60x96_20260512.ps1`

默认会按上表顺序运行。已经有 `metrics.json` 的 variant 会跳过，避免重复烧同一轮实验。

```powershell
powershell -ExecutionPolicy Bypass -File .\xes\run_strong_harness_ablation_60x96_20260512.ps1
```

如果要强制重跑全部 12 个：

```powershell
powershell -ExecutionPolicy Bypass -File .\xes\run_strong_harness_ablation_60x96_20260512.ps1 -SkipCompleted:$false
```

如果只补某几个：

```powershell
powershell -ExecutionPolicy Bypass -File .\xes\run_strong_harness_ablation_60x96_20260512.ps1 -Variants @("hachimi_no_difficulty_signal_problem_core_only","hachimi_no_difficulty_signal_no_interaction_decision")
```

### 16.3 结果汇总

汇总脚本：

`D:\Study\sii\MathStudent\xes\summarize_strong_ablation_60x96.py`

```powershell
python .\xes\summarize_strong_ablation_60x96.py
```

输出报告：

`D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md`

最终人工解释会写入：

`D:\Study\sii\MathStudent\xes\reports\xes_strong_harness_module_necessity_audit_20260512.md`
