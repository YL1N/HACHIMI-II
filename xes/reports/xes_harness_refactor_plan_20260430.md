# XES 当前系统改造方案

## 1. 改造目标

当前系统已经具备完整主链：

`学生画像 -> 学生模型 -> 题目需求画像 -> 学生-题目交互判断 -> 单题作答状态 -> 约束包 -> 答案生成 -> 评估`

但从最近结果看，主要问题已经很清楚：

- `模拟正确率 vs Rasch b_hat` 相关接近 `0`
- `strict_monotonic_item_count = 0`
- `same_dominant_answer_all_levels` 比例偏高

这说明当前系统的主要瓶颈不是“学生口吻不够像”，而是：

1. **题目难度感知没有稳定建立**
2. **学生差异没有稳定投射到题目上**
3. **最后生成层的输出同质化偏重**

所以这次改造不应继续加 prompt 修辞，而应继续补 harness。

---

## 2. 总体改造原则

这次改造只做三类事：

1. **增强题目环境**
2. **增强学生 × 题目交互判断**
3. **把潜在结果和表面回答拆开**

不做的事：

- 不先换更强模型
- 不先继续写“更像学生”“别太聪明”这类 prompt
- 不在运行时硬控 target accuracy
- 不把真实评测卷标签带入生成链

---

## 3. 改造一：给题目需求画像加入 difficulty anchor context

### 3.1 目的

当前 `ProblemRequirementProfile` 能描述题目结构，但还缺少一个“同域相对难度坐标系”。

所以模型现在经常知道题目有哪些形式特征，但不知道：

> 在三年级、同模块、同题型内部，这题到底算偏容易、居中还是偏难。

### 3.2 要改什么

改 `xes/src/problem_profile.py`

当前 `ProblemRequirementProfile` 只有：

- prerequisite_knowledge
- operation_complexity
- abstraction_level
- knowledge_integration_demand
- representation_shift_required
- response_format_demand
- guessability
- notes
- perceived_difficulty_for_target_grade
- real_difficulty_band

这里建议新增一个显式字段：

- `difficulty_anchor_context`

建议结构如下：

- `target_question_local_difficulty_hypothesis`
- `anchor_cases`
  - `easy_anchor`
  - `medium_anchor`
  - `hard_anchor`
- `difficulty_anchor_rationale`

其中每个 anchor case 只保留：

- question_id
- question_type
- module_name
- difficulty_band
- paper_b_hat
- question_text
- short_structural_reason

### 3.3 数据从哪里来

不从当前评测卷里找。

只从 XES support pool 里找，并且尽量同：

- 年级
- 模块
- 题型

如果完全同模块题不够，再放宽到同 route top，但必须显式记录放宽原因。

### 3.4 这些 anchor 放在哪一步

只放在：

- `ProblemRequirementProfile` 构建阶段

不要直接传给最终答案生成阶段。

原因很简单：

- 这里的目标是帮助模型理解题目难度
- 不是提示模型怎么答

### 3.5 新增文件建议

建议新增：

- `xes/src/difficulty_anchor_bank.py`

职责只做两件事：

1. 从 support pool 建立 `module × question_type × difficulty_band` 的 anchor 索引
2. 给目标题检索 easy / medium / hard 三个 anchor case

这个文件职责明确，值得单独拆。

### 3.6 prompt 要怎么改

改 `xes/src/prompts.py`

在 `PROBLEM_PROFILE_PROMPT` 相关部分加入明确约束：

- 当前题需要结合 anchor cases 做相对难度判断
- anchor 只用于解释题目难度，不用于泄露答案
- 输出中必须说明当前题与 easy / medium / hard anchor 的主要差异

### 3.7 验收标准

这一步改完后，首先看：

- `item_accuracy_pearson_vs_rasch_b_hat`
- `item_accuracy_spearman_vs_rasch_b_hat`

至少方向要稳定为负。

如果方向还经常错，说明题目难度坐标系仍然没立起来。

---

## 4. 改造二：重写学生—题目交互判断，不再用粗平均 margin

### 4.1 当前问题

当前 `xes/src/student_item_interaction.py` 的核心逻辑，本质上是：

- 把多个能力维度转成分数
- 把多个题目负荷维度转成分数
- 用平均能力减平均负荷

这太粗。

因为它默认所有维度都可以相互抵消。

但实际不是这样。

例如：

- 一个学生计算强，不代表他就能弥补表征转换弱
- 一个学生会排除选项，不代表他就能弥补多步稳定性不足

### 4.2 要改什么

改 `xes/src/student_item_interaction.py`

`StudentItemInteractionDecision` 当前字段有：

- predicted_reachability
- predicted_correctness_band
- likely_outcome
- likely_error_family
- confidence_cap
- explanation_cap
- decision_rationale

建议新增并重构为：

- `predicted_reachability`
- `predicted_correctness_band`
- `likely_outcome`
- `dominant_failure_mode`
- `bottleneck_dimensions`
- `supporting_dimensions`
- `confidence_cap`
- `explanation_cap`
- `decision_rationale`

### 4.3 新的判断逻辑

不要再算一个总平均 margin。

改成逐维判断：

- `arithmetic_fluency` ↔ `operation_complexity`
- `word_problem_transfer` ↔ `representation_shift_required`
- `multi_step_stability` ↔ `knowledge_integration_demand`
- `fill_blank_precision` / `option_elimination` ↔ `response_format_demand`
- `hard_item_persistence` ↔ `difficulty_band / complexity pressure`
- `guessing_tendency` ↔ `guessability`

最后再汇总成：

- 主瓶颈在哪些维度
- 支撑优势在哪些维度
- 预测是对、近错还是错

### 4.4 错误类型怎么来

当前 `likely_error_family` 过于依赖 persona 里的 `common_error_families`。

建议把错误类型拆成两部分：

1. **能力侧错误倾向**
2. **题目侧诱发错误**

最终的 `dominant_failure_mode` 由两边交叉生成。

例如：

- “表征转换失败”
- “多步整合中途断裂”
- “格式输出失误”
- “可猜题盲猜”

### 4.5 验收标准

这一步改完后，重点看：

- `strict_monotonic_item_count`
- `same_dominant_answer_all_levels_fraction`
- 分层 item Pearson / Spearman

如果四档还是大面积共享主导答案，说明交互判断还没有真正把学生差异投到题目上。

---

## 5. 改造三：把“潜在结果”和“表面回答”拆开

### 5.1 当前问题

当前流程里：

- `StudentItemInteractionDecision`
- `ItemResponseState`
- `ConstraintBundle`

之后就直接进入答案生成。

这样容易出现一个问题：

- 状态层说他只是 partial
- 但最终生成时仍然可能直接写出一个高度同质化、甚至偏完整的答案

因为中间缺了一层显式的“潜在作答结果表示”。

### 5.2 要改什么

建议改：

- `xes/src/response_state.py`
- `xes/src/generation.py`

建议新增一个中间对象，例如：

- `LatentResponsePlan`

字段建议包括：

- `target_outcome`: `correct | near_miss | wrong`
- `target_error_mode`
- `target_commitment_level`
- `target_explanation_depth`
- `target_answer_shape`
- `surface_style_guidance`

### 5.3 新链路应该变成什么

从现在的：

`ItemResponseState -> ConstraintBundle -> Answer`

改成：

`ItemResponseState -> LatentResponsePlan -> ConstraintBundle -> Answer`

这样做的意义是：

- 先决定“这次潜在上会发生什么”
- 再决定“它怎么被说出来”

这比当前直接从状态一路生成更稳。

### 5.4 direct 和 state_step 怎么处理

当前 `direct` 和 `state_step` 都可以保留，但都应经过 `LatentResponsePlan`。

区别只在于：

- `direct`：直接从 latent plan 生成最终答案
- `state_step`：分步地把 latent plan 表面化

### 5.5 验收标准

这一步改完后，重点看：

- 不同学生在同题上的答案分化是否增加
- `same_dominant_answer_all_levels_fraction` 是否下降
- 是否减少“明明是 partial / guessable 但最后大家都答得一样”的情况

---

## 6. 改造四：收紧学生模型输入，减少噪声污染

### 6.1 当前问题

`StudentModel` 当前保留了很多长段心理与人格文本。

这些字段不是没用，但对当前静态数学答题任务来说，噪声已经偏大。

尤其当我们目标是题目级模拟时，过长的自然语言人物描述容易把模型带偏。

### 6.2 要改什么

改 `xes/src/student_model.py`

不是删除字段，而是区分：

- **全量 student model**
- **作答链路用的 compact student model**

建议新增一个投影函数，例如：

- `project_student_model_for_answering(...)`

只保留与当前任务最相关的字段：

- grade
- academic_level
- math_task_capability_profile
- efficacy_signal
- srl_fragility_signal
- directness_signal
- 少量数学相关 summary

不把全部人格长文本一路喂到状态层和生成层。

### 6.3 验收标准

这一步不是看总分，而是看：

- 题目级相关是否更稳定
- 不同 persona 之间的噪声波动是否下降

如果压缩输入后相关性更稳，说明之前确实有文本噪声污染。

---

## 7. 改造五：固定评估口径，分开看“像不像真实学生”和“懂不懂题目难度”

### 7.1 当前问题

过去很容易把“和真实学生正确率相关”当成唯一题目级指标。

但现在已经很清楚，这其实混了两件事：

1. 模拟结果像不像真实学生群体
2. 模型有没有感知题目本身难度

### 7.2 要改什么

改：

- `xes/src/evaluation.py`
- 报告模板
- 分析脚本

固定分成两类指标：

#### A. 真实群体贴近度

- `item_accuracy_pearson_vs_real_students`
- `item_accuracy_spearman_vs_real_students`

#### B. 题目难度感知能力

- `item_accuracy_pearson_vs_rasch_b_hat`
- `item_accuracy_spearman_vs_rasch_b_hat`

注意：

- B 类指标理论上应当是负相关

### 7.3 当前所有分析文档也要同步

后面所有汇报都不要再只说“item Pearson”。

必须明确说是哪一条：

- 对真实学生
- 还是对 Rasch 难度

---

## 8. 建议改造顺序

按收益和依赖关系，建议顺序如下：

### 第一优先级

1. `problem_profile.py`：加入 `difficulty_anchor_context`
2. `difficulty_anchor_bank.py`：新增 anchor 检索模块
3. `prompts.py`：让题目画像阶段使用 anchor cases

### 第二优先级

4. `student_item_interaction.py`：改成逐维比较，不再用粗平均 margin

### 第三优先级

5. `response_state.py` + `generation.py`：加入 `LatentResponsePlan`

### 第四优先级

6. `student_model.py`：做 answering-only compact projection

### 持续动作

7. `evaluation.py` 与分析文档：固定双指标口径

---

## 9. 各文件的改动清单

### 必改

- `xes/src/problem_profile.py`
- `xes/src/prompts.py`
- `xes/src/student_item_interaction.py`
- `xes/src/response_state.py`
- `xes/src/generation.py`
- `xes/src/student_model.py`
- `xes/src/evaluation.py`

### 建议新增

- `xes/src/difficulty_anchor_bank.py`

### 需要同步文档

- `xes/reports/xes_overall_solution_architecture_20260430.md`
- 后续所有实验分析文档中关于 item-level correlation 的表述

---

## 10. 这次改造完成后的判定标准

改造是否有效，不看单一总分，重点看四件事：

1. `模拟正确率 vs Rasch b_hat` 是否稳定变成负相关
2. `strict_monotonic_item_count` 是否上升
3. `same_dominant_answer_all_levels_fraction` 是否下降
4. `模拟正确率 vs 真实学生正确率` 是否同步提升或至少不恶化

如果只提升了总体正确率，但这四件事没改善，那就不算真正改对。
