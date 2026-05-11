# PROJECT_GUIDE.md

## 0. 项目定位

本项目是一个**面向数学题作答的学生模拟方法项目**。

目标不是做“通用学生模拟”，也不是做“更像学生语气的 prompt 工程”，而是：

> 给定一份最小必要的学生画像信息和一道数学题，构建一种方法，使大模型生成的学生作答在**题目级对错模式**、**整体正确率**、**题目难度相关性**以及**不同学生层级的区分度**上更接近真实学生，并显著减少能力泄露。

本项目当前只服务于：
- 数据集：XES3G5M 文本可直投数学题子集
- 任务：静态数学题作答
- 输出：单题答案 + 可选极简学生式短回应

本项目**不**尝试在 v1 中解决：
- 动态对话
- 任意任务
- 通用学生代理
- 错项分布拟合
- 单个真实学生的个体级数字分身

---

## 1. 非目标（非常重要）

本项目不做以下事情：

1. 不做“为了把平均分调准而疯狂堆 prompt”。
2. 不做“显式告诉模型这题该答对/答错”。
3. 不做“基于题号、题型、关键词的特殊兜底逻辑”。
4. 不做“按 XES 数据集人工调 prompt 到均值刚好贴近真实学生”的 dataset-specific hacking。
5. 不做“利用真实学生标签或 item accuracy 在推理时直接控制模型答案”。
6. 不做“构造一个完整的人”，只做**与数学题作答直接相关的学习者模型**。

---

## 2. 数据输入

本项目只依赖两类数据：

### 2.1 学生画像
来自已有画像库，但运行时只取**最小必要字段**。允许存在更多原始字段，但不应全部进入模型推理链。

建议保留：
- `id`
- `年级`
- `学术水平`
- `擅长科目`
- `薄弱科目`
- 与学习相关的短文本（如：遇到困难时是否退缩、是否自信、是否愿意坚持、是否表达保守）

不建议保留大段与数学作答弱相关的长文本，例如：
- 大量社交细节
- 大段价值观叙述
- 与数学作答无关的背景故事

### 2.2 XES3G5M
只使用：
- 题目文本
- 选项
- 正确答案
- 真实学生逐题对/错记录
- 可用于构造题目侧统计的必要字段

这些真实学生记录只用于：
- 离线评测
- 题目统计分析
- 构造评估基准

**绝不允许**在单题推理时把：
- 真实学生正确率
- 真实学生标签
- 题目平均难度结果
直接喂给模型作为作答提示。

---

## 3. 方法总述

本项目采用一个 **Math Student Answering Harness**。

它不是：
`学生画像 -> 直接答案`

而是：

`学生画像 -> StudentModel -> ProblemRequirementProfile -> ItemResponseState -> ConstraintBundle -> 答案 -> ViolationCheck -> 可选一次重试`

也就是说，模型不是直接“扮演学生”，而是先经过**第三人称侧写/状态推断**，把“这个学生对这道题大概会到什么程度”显式化，再在该边界内生成作答。

这就是本项目的核心 novelty 候选：

> 不是让高能力模型直接装作不会，而是让它充分利用自身能力去**预测/拟合学生在当前题目上的真实作答状态**，然后再在该状态下作答。

---

## 4. 理论框架（只保留与数学题作答直接相关的部分）

### 4.1 Bandura：自我效能（Self-Efficacy）
核心内容：
- 个体对“自己能否完成某一任务”的主观判断会影响努力、坚持、回避和表现。
- 自我效能不是泛化自信，而是**任务相关的能力信念**。

本项目的用法：
- 用来刻画学生面对数学题时的“我觉得我能不能做”的基线。
- 它影响：
  - 是否更容易进入 `mastered / partial / guessable / unreachable`
  - 是否更容易承诺答案
  - 是否更容易在困难题上快速放弃

本项目中的字段：
- `academic_self_efficacy`

映射规则（必要时）：
- 若画像中出现“容易自我怀疑 / 缺乏自信 / 面对学业挑战退缩 / 数学薄弱” -> 倾向 `low`
- 若画像中出现“较自信 / 学业稳定 / 数学不弱 / 面对题目较敢尝试” -> 倾向 `medium` 或 `high`

### 4.2 Zimmerman：自我调节学习（Self-Regulated Learning, SRL）
核心内容：
- 学习者差异不仅在“会不会”，还在于是否会计划、监控、坚持、修正。
- 可简化理解为：面对任务时，学生是否会持续投入并对自己的解题过程进行监控和调整。

本项目的用法：
- 用来解释为什么有些学生不是完全不会，而是“做到一半断掉”或“局部会但不稳定”。
- 它影响：
  - `partial` 状态的形成
  - 错误路径是否表现为“中途断裂”
  - 是否在第一次错误后愿意继续尝试

本项目中的字段：
- `monitoring_strength`
- `self_regulatory_persistence`

映射规则：
- 若画像中出现“主动性一般 / 自律不足 / 遇到困难容易放弃 / 缺乏稳定学习习惯” -> `monitoring_strength = low`, `self_regulatory_persistence = low/medium_low`
- 若画像中出现“耐心较好 / 能持续尝试 / 做事较认真” -> 提高相应等级

### 4.3 Pekrun：控制—价值理论（Control-Value Theory）
核心内容：
- 学生面对任务时的情绪和行为，不仅取决于“价值高不高”，也取决于“是否觉得自己可控”。
- 对数学作答来说，最关键的是“控制感不足时，更容易焦虑、回避、保守作答”。

本项目的用法：
- 不直接单独造很多情绪字段，而是把它收成一个紧凑字段：
  - `control_appraisal`
  - `task_value`
- 它影响：
  - 困难题上是否更倾向保守/犹豫
  - 是否在边界题上选择不承诺
  - 是否容易进入 `guessable` 而不是积极推理

映射规则：
- 若画像中“学业压力明显、容易焦虑、面对失败波动大” -> 偏 `low_control`
- 若画像中“任务价值感弱、对学业不太投入” -> 可记为 `low_value`
- 组合后形成：
  - `low_control_medium_value`
  - `low_control_low_value`
  - `medium_control_medium_value`
  等有限状态

### 4.4 ICAP：外显参与层级
核心内容：
- 外显行为可分为 Passive / Active / Constructive / Interactive。
- 对本项目来说，重点不在课堂互动，而在于：学生作答表现出多高层级的参与。

本项目的用法：
- 它不直接决定对错，但决定“答题表现成熟到什么程度”。
- 例如：
  - 只选答案、不给解释：更接近 Active
  - 给出局部理由：可能是低水平 Constructive
  - 给出完整成熟解释：更高层，不应轻易出现

本项目中的字段：
- `engagement_level_tendency`
- `response_directness`

映射规则：
- 若画像中“表达保守、犹豫、话少” -> `engagement_level_tendency` 更偏 `Passive / Active`
- 若画像中“更愿意表达、愿意解释” -> 可提高到 `constructive`

### 4.5 Webb DOK / TIMSS Cognitive Domains
核心内容：
- 题目不仅有难度，还有不同层级的认知处理要求。
- 对数学题可用较稳的层级：
  - 记忆/常规
  - 技能与概念应用
  - 策略性推理
  - 扩展建模（本项目大概率很少用）

本项目中的字段：
- `operation_complexity`

枚举值：
- `Level 1 Recall and Reproduction`
- `Level 2 Skills and Concepts`
- `Level 3 Strategic Thinking`
- `Level 4 Extended Thinking`

### 4.6 Stein & Smith：数学任务认知需求
核心内容：
- 数学任务的关键差别不只是步骤数，还在于其数学理解要求。
- 四层：
  - 记忆
  - 无联系程序
  - 有联系程序
  - doing mathematics

本项目中的字段：
- `abstraction_level`

枚举值：
- `Memorization`
- `Procedures Without Connections`
- `Procedures With Connections`
- `Doing Mathematics`

---

## 5. 核心对象与字段

### 5.1 StudentModel
这是**稳定的学生模型对象**，不是原始画像，也不是最终 prompt 文本。

建议数据结构：

```python
StudentModel(
    student_id: str,
    grade: str,
    academic_level: str,
    weak_subjects: List[str],
    strong_subjects: List[str],

    academic_self_efficacy: str,      # low / medium / high
    monitoring_strength: str,         # low / medium / high
    self_regulatory_persistence: str,        # low / medium / high
    control_appraisal: str,           # low / medium / high
    task_value: str,                  # low / medium / high
    engagement_level_tendency: str,   # Passive / Active / Constructive / Interactive
    response_directness: str,         # low / medium / high

    raw_summary: str
)
```

### 5.2 ProblemRequirementProfile
这是题目需求画像，不是题目答案。

```python
ProblemRequirementProfile(
    prerequisite_knowledge: List[str],
    operation_complexity: str,              # L1-L4
    abstraction_level: str,                 # A0-A3
    knowledge_integration_demand: str,      # single_knowledge / multiple_knowledge_combination
    representation_shift_required: str,     # none / low / high
    response_format_demand: str,            # selection_only / short_fill / constructed_numeric / constructed_explanation
    guessability: str,                      # unknown / low / medium   （辅助字段，不是核心）
    notes: List[str]
)
```

说明：
- `curricular_stage_estimate` / `prerequisite_band` **不做**。
- 因为我们不维护知识点到年级段映射表，也不希望让 LLM 自由猜年级。

### 5.3 ItemResponseState
这是当前学生面对当前题目的**题目级响应状态**，是方法最关键的中间层。

```python
ItemResponseState(
    prerequisite_familiarity: str,      # familiar / partially_familiar / mostly_unfamiliar
    response_state: str,                # mastered / partial / guessable / unreachable
    reachable_level: str,
    error_path: List[str],
    commitment_tendency: str,           # low / medium / high
    explanation_depth_cap: str,         # answer_only / short_reason / limited_reason / full_reason
    response_style_guidance: List[str]
)
```

### 5.4 ConstraintBundle
把 `ItemResponseState` 编译成可执行边界。

```python
ConstraintBundle(
    must_commit_answer: bool,
    allow_complete_explanation: bool,
    max_sentences: int,
    max_thinking_steps: int,
    forbid_full_mastery: bool,
    preferred_error_path: List[str],
    style_constraints: List[str],
    allowed_commitment: str
)
```

---

## 6. 方法流程（必须这样实现）

### Step 1：构建 StudentModel
输入：原始学生画像  
输出：`StudentModel`

实现原则：
1. 规则抽基础字段：
   - 年级
   - 学术水平
   - 擅长/薄弱科目
2. 再调用 LLM，在**理论框架显式写进 prompt** 的前提下，输出 StudentModel 的理论字段
3. 不允许把原始长画像直接喂给后续答题 prompt

### Step 2：构建 ProblemRequirementProfile
输入：题目文本、选项  
输出：`ProblemRequirementProfile`

实现原则：
1. 只分析题目需要什么，不解题
2. Prompt 中显式写明：
   - DOK/TIMSS 的 operation complexity 含义
   - Stein & Smith 的 abstraction level 含义
3. 不输出答案，不输出“这题该答对/答错”

### Step 3：解析 ItemResponseState
输入：
- `StudentModel`
- `ProblemRequirementProfile`
- 当前题目文本

输出：
- `ItemResponseState`

实现原则：
1. 必须通过第三人称侧写完成
2. 不直接回答题
3. 重点输出：
   - `prerequisite_familiarity`
   - `response_state`
4. 这里是从“稳定学生模型”到“当前题作答状态”的关键跳转

### Step 4：编译约束
输入：`ItemResponseState`  
输出：`ConstraintBundle`

实现原则：
- 规则主导
- 不用 LLM 自由发挥
- 静态数学题中 `must_commit_answer = True`
- `response_state` 决定：
  - 是否允许完整解释
  - 是否允许高承诺
  - 是否允许表现出完整掌握

### Step 5：生成答案
输入：
- `StudentModel`
- `ProblemRequirementProfile`
- `ItemResponseState`
- `ConstraintBundle`

输出：
- `predicted_answer`
- `student_response`（可选，简短）

实现原则：
1. LLM 负责生成
2. Prompt 中明确写：
   - 你不能使用超出 `ItemResponseState` 的知识
   - 你不能为了贴近目标均值而调整答案
   - 你不能表现得比当前状态更成熟
3. 输出必须是 JSON

### Step 6：违例检查
输入：
- 输出结果
- `ItemResponseState`
- `ConstraintBundle`

输出：
- `ViolationReport`

实现原则：
1. 先规则初筛
2. 边界样本可再做 LLM 复核
3. 检查重点：
   - 若 `response_state = unreachable`，却出现完整成熟作答 -> 违例
   - 若 `response_state = guessable`，却出现稳定完整推理 -> 违例
   - 若 `explanation_depth_cap = answer_only`，却长篇解释 -> 违例

### Step 7：局部重试（最多一次）
若有违例：
- 收紧约束
- 再生成一次
- 不允许无限重试

---

## 7. 具体提示词（必须照这个精神写，不要偷简化）

### 7.1 StudentModel Builder Prompt

```text
你要根据一份学生资料，构建一个“数学题作答学生模型”。

这个学生模型不是完整人格，也不是任务答案，而是用于后续数学题作答模拟的稳定学生表征。

请按以下理论理解字段：

1. academic_self_efficacy
含义：学生对自己完成数学任务能力的主观判断。
低：容易自我怀疑、遇到数学题容易觉得自己做不出来。
高：更敢尝试，较少因一时困难直接退缩。

2. monitoring_strength
含义：学生在做题时能否监控自己的过程，发现偏差并调整。
低：容易一条路走到底，不容易察觉自己哪里出了问题。
高：更可能及时发现问题并调整。

3. self_regulatory_persistence
Meaning: persistence after difficulty/failure (implementation-level operationalization, not theory-native category).

4. control_appraisal
Meaning: perceived control over success/failure (implementation-level operationalization, not theory-native category).

5. task_value
Meaning: perceived value/importance/usefulness of math tasks (implementation-level operationalization, not theory-native category).

6. engagement_level_tendency
Meaning: MUST use ICAP theory-native categories exactly: Passive / Active / Constructive / Interactive.

7. response_directness
含义：学生回答时是否直接、果断。
low：更犹豫、更保守
high：更直接

请只输出 JSON，不要复述原文，不要写故事。
```

---

### 7.2 ProblemRequirementProfile Prompt

```text
你是一个数学题需求分析器。你的任务不是解题，而是分析“做这道题需要什么”。

请按以下理论理解字段：

1. operation_complexity
使用 DOK/TIMSS 风格：
- Level 1 Recall and Reproduction：主要是直接回忆或熟练程序
- Level 2 Skills and Concepts：需要技能或概念应用
- Level 3 Strategic Thinking：需要策略性推理、关系判断、多步协调
- Level 4 Extended Thinking：需要扩展建模或长链条推理

2. abstraction_level
使用 Stein & Smith 风格：
- Memorization：记忆与直接回忆
- Procedures Without Connections：程序执行，但不要求理解概念联系
- Procedures With Connections：程序执行需要和概念意义联系起来
- Doing Mathematics：需要探索、重组关系、非模板化做数学

其他字段：
- prerequisite_knowledge：做这道题至少需要哪些先修知识
- knowledge_integration_demand：是否需要多个知识点组合
- representation_shift_required：是否需要做表征转换（例如文字到算式）
- response_format_demand：回答形式要求
- guessability：不会做时是否可能靠表面线索猜中（辅助字段，若不确定请输出 unknown）

请只输出 JSON，不要解题，不要给答案。
```

---

### 7.3 ItemResponseState Prompt

```text
你要做的是“第三人称侧写”，不是解题。

请根据：
- 学生模型
- 题目需求画像
- 当前题目

推断这个学生在这道题上的“题目级作答状态”。

请重点输出：

1. prerequisite_familiarity
- familiar
- partially_familiar
- mostly_unfamiliar

2. response_state
- mastered：大致在能力边界内，较稳定可做对
- partial：掌握一部分，有机会做对，但不稳定
- guessable：本身不会，但可能靠表面线索、排除法或格式感猜中
- unreachable：明显超出边界，通常做不出来

3. reachable_level
一句话说明最多能做到什么程度

4. error_path
如果不会或不稳定，最可能怎么错

5. commitment_tendency
- low / medium / high

6. explanation_depth_cap
- answer_only
- short_reason
- limited_reason
- full_reason

要求：
- 不要直接回答题目
- 不要给标准答案
- 不要把学生写得比其状态更强
- 输出必须是 JSON
```

---

### 7.4 Answer Generator Prompt

```text
你现在要以学生身份作答，但你必须严格遵守给定的 ItemResponseState 和 ConstraintBundle。

重要规则：
1. 你不能使用超出当前状态的知识。
2. 你不能为了让整体准确率更接近某个目标而故意答对或答错。
3. 你不能因为自己知道正确答案，就表现得比这个学生当前状态更成熟。
4. 如果 response_state = guessable，你可以猜中，但不能给出成熟完整推理。
5. 如果 response_state = unreachable，你不应表现出完整掌握。
6. 你只需要输出 JSON：
{
  "predicted_answer": "...",
  "student_response": "..."
}
7. student_response 尽量短，不要教师式总结。

这不是角色扮演游戏，而是基于当前学生状态的约束作答。
```

---

### 7.5 Violation Review Prompt（可选）

```text
你不是在判题对错，而是在判断“这个输出是否超出了学生当前应有边界”。

请根据：
- ItemResponseState
- ConstraintBundle
- 当前输出

判断：
1. 是否发生能力泄露
2. 是否发生不合理成熟化
3. 是否违反 explanation_depth_cap
4. 是否与 response_state 矛盾

输出 JSON：
{
  "has_violation": true/false,
  "reasons": [...],
  "severity": "low/medium/high"
}
```

---

## 8. 评测目标

主目标不是把平均分调到差不多，而是看：

1. 与真实学生的总体正确率 gap 是否下降
2. 题目级正确率相关性是否提高
3. 难度排序相关性是否提高
4. 高/中/低/差四档是否仍保留合理区分度
5. 一、二、三年级学生在三年级题上的表现是否满足单调性

---

## 9. 明确禁止的 cheating

以下行为一律禁止：

1. 在推理路径中直接使用真实学生正确率、题目平均准确率、真实标签。
2. 在 prompt 中显式告诉模型“这题应该答对/答错”。
3. 针对特定题号、题型、学生年级写特殊兜底逻辑。
4. 为贴近目标均值而在后处理阶段翻转答案。
5. 根据 XES 结果人工反复修改 prompt 直到均值贴上，而不改方法结构。
6. 根据题目 ID 建立白名单/黑名单。
7. 任何“如果是某类题就固定答错/答对”的硬编码。
8. 把 evaluation statistics 偷偷带入 generation path。

---

## 10. 最小工程落地要求

主项目文件尽量控制在：

- `run_experiments.py`
- `prompts.py`（可选）
- `data/`
- `outputs/`
- `PROJECT_GUIDE.md`
- `AGENTS.md`

必须实现的核心函数：

```python
build_student_model(...)
build_problem_requirement_profile(...)
resolve_item_response_state(...)
compile_constraints(...)
generate_student_answer(...)
check_violation(...)
retry_with_tighter_constraints(...)
```

---

## 11. 项目成功标准

v1 成功不要求“完美模拟”，但至少要求：

1. 不再依赖几千行手工均值校准 prompt 才勉强贴近平均分；
2. 主方法相较 baseline：
   - 题目级相关性更高
   - 平均分 gap 不显著变坏
   - 能力泄露更少
3. 方法结构明确，能解释“为什么这道题会做对/做错”，而不是只会调均值。

---

## 12. 参考理论（写入文档，不要求在代码中逐字引用）
- Bandura, Self-Efficacy
- Zimmerman, Self-Regulated Learning
- Pekrun, Control-Value Theory
- Chi & Wylie, ICAP
- Webb DOK / TIMSS cognitive domains
- Stein & Smith mathematical task cognitive demand

---

## 13. 2026-04-16 最小可运行实现说明

当前仓库已落地最小端到端 harness（`run_experiments.py` + `src/*.py`），实现如下：

1. 完整主流程：
   - `StudentModel -> ProblemRequirementProfile -> ItemResponseState -> ConstraintBundle -> Answer -> ViolationCheck -> Optional Retry`
2. 反作弊边界：
   - generation path 不读取题目真实正确率、真实标签、评测统计；
   - 真实答案与作答日志仅在 `evaluation.py` 离线评测使用；
   - 无题号特判、无后处理翻转答案。
3. 运行策略：
   - 默认启用 rule-based 最小后端，先确保小样本 smoke test 可稳定跑通；
   - 支持 `--backend llm` 接入 OpenAI-compatible 大模型后端（`src/llm_client.py`）；
   - 保留集中式 `src/prompts.py` 模板，便于 LLM 调用审计。
   - 当前 XES 题集为三年级设定，运行时默认按 `--target_grade 三年级 --grade_match_mode exact` 严格过滤画像，避免混入初三/高三等“同序号不同学段”学生。
   - 画像采样默认 `--persona_sampling stratified`，在目标年级内按 `academic_level` 分层抽样，避免“取前 N”导致样本偏置。
4. 可审计输出：
   - 每条预测保留中间对象（student/profile/state/constraints）与最终违例报告；
   - 输出 `predictions.jsonl`、`metrics.json`，并额外输出解析友好的 `predictions_compact.jsonl/.csv`。

---

## 14. 2026-04-16 Responsibility Split Update

This section overrides any older wording that allows semantic rule fallbacks.

1. LLM-mandatory semantic modules:
   - `build_student_model(...)`
   - `map_student_model_to_internal_signals(...)`
   - `build_problem_requirement_profile(...)`
   - `resolve_item_response_state(...)`
   - `generate_student_answer(...)`
   - `review_violation_with_llm(...)` (boundary samples only)

2. Rule-mandatory modules:
   - `compile_constraints(...)`
   - all schema/enum/list JSON validation
   - `check_hard_violation_rules(...)`
   - `retry_with_tighter_constraints(...)`
   - data loading, benchmark freezing, grade filtering, label isolation
   - evaluation/aggregation/reporting
   - official correctness is rule-first (`is_prediction_correct(...)`)
   - rule-based correctness may normalize formatting-equivalent answers (for example LaTeX wrappers, fraction syntax, outer parentheses, and equation-tail final values), but must not use real labels/statistics to relax scoring
   - for structurally ambiguous gold-answer formats only, an optional evaluation-only LLM secondary review may be used after a rule miss; this review must never enter generation/retry logic

3. Violation pipeline:
   - rules first: `check_hard_violation_rules(...)`
   - boundary-only LLM review: `review_violation_with_llm(...)`
   - merge reports; never use labels/statistics in generation path

4. Runtime enforcement:
   - `run_experiments.py` only supports `--backend llm`
   - semantic module call without `llm_client` must raise explicit error
   - optional diagnostic `LLM-as-a-judge` correctness is diagnostics-only and must not be used to alter generated answers or trigger retries
   - optional official LLM correctness review is allowed only as a secondary resolver for structurally ambiguous evaluation cases after rule miss

---

## 15. Field Taxonomy Update (2026-04-16)

This section is authoritative for field taxonomy and overrides older wording where conflicts exist.

### 15.1 Theory-native categories

These fields must use original theory category labels (not project-invented labels):

- `operation_complexity` (Webb DOK):
  - `Level 1 Recall and Reproduction`
  - `Level 2 Skills and Concepts`
  - `Level 3 Strategic Thinking`
  - `Level 4 Extended Thinking`
- `abstraction_level` (Stein & Smith):
  - `Memorization`
  - `Procedures Without Connections`
  - `Procedures With Connections`
  - `Doing Mathematics`
- `engagement_level_tendency` (ICAP):
  - `Passive`
  - `Active`
  - `Constructive`
  - `Interactive`

### 15.2 Implementation-level operationalizations

These fields are NOT theory-native discrete categories. They are project-level discretizations.
LLM must first interpret by theory meaning, then map to implementation labels.

- `efficacy_signal`: `low|medium|high`
- `srl_fragility_signal`: `low|medium|high`
- `control_signal`: `low|medium|high`
- `value_signal`: `low|medium|high`
- `directness_signal`: `low|medium|high`

### 15.3 Deprecated fields

The following are removed from runtime schema and must not appear in generation path:

- `revision_persistence` -> replaced by descriptive SRL fields in `srl_analysis`
- `control_value_balance` -> replaced by descriptive control/value fields in `control_value_analysis`
- `active_low_constructive` (non-theory ICAP hybrid label) -> replaced by original ICAP categories

---

## 16. Prompt-Schema Migration v2 (2026-04-16)

This section supersedes earlier field definitions where conflicts exist.

### 16.1 Three-layer taxonomy (authoritative)

1. theory-native categories
- `engagement_level_tendency` (ICAP): `Passive|Active|Constructive|Interactive`
- `operation_complexity` (Webb DOK):
  - `Level 1 Recall and Reproduction`
  - `Level 2 Skills and Concepts`
  - `Level 3 Strategic Thinking`
  - `Level 4 Extended Thinking`
- `abstraction_level` (Stein & Smith):
  - `Memorization`
  - `Procedures Without Connections`
  - `Procedures With Connections`
  - `Doing Mathematics`

2. theory-grounded descriptive outputs
- `self_efficacy_analysis`:
  - `efficacy_belief_description`
  - `efficacy_belief_evidence`
- `srl_analysis`:
  - `primary_srl_vulnerability`
  - `srl_process_evidence`
- `control_value_analysis`:
  - `control_appraisal_description`
  - `value_appraisal_description`
  - `control_value_evidence`
- `engagement_evidence`
- `response_directness_description`
- `response_directness_evidence`
- `operation_complexity_justification`
- `abstraction_level_justification`

3. implementation-level derived signals (internal only)
Derived by explicit mapping layer (`map_student_model_to_internal_signals(...)`), e.g.:
- `efficacy_signal`
- `srl_fragility_signal`
- `control_signal`
- `value_signal`
- `directness_signal`

These are internal helper signals for state inference and constraint compilation.
They are NOT theory-native outputs.

### 16.2 Why no forced low/medium/high for non-categorical theories

Bandura self-efficacy, Zimmerman SRL, and Pekrun control-value are explanatory constructs/processes.
They are not provided as one canonical universal discrete label set in original theory text.
Forcing them directly into fake "theory-native" low/medium/high bins causes construct distortion and weakens auditability.

### 16.3 Why mapping layer is required now

After moving StudentModel to descriptive theory-grounded outputs, downstream modules still need structured internal signals.
Therefore we use an explicit, auditable implementation mapping layer.
This mapping is LLM-based with strict JSON schema validation, and heuristic keyword mapping is disallowed.
This preserves:
- theory-faithful upstream representation,
- stable downstream execution,
- clear boundary between theory outputs and engineering signals.

### 16.4 Current schema contracts

StudentModel (public runtime object):
- basic: `student_id`, `grade`, `academic_level`, `weak_subjects`, `strong_subjects`
- analyses: `self_efficacy_analysis`, `srl_analysis`, `control_value_analysis`
- engagement: `engagement_level_tendency`, `engagement_evidence`
- directness: `response_directness_description`, `response_directness_evidence`
- `raw_summary`

ProblemRequirementProfile (public runtime object):
- `operation_complexity`, `operation_complexity_justification`
- `abstraction_level`, `abstraction_level_justification`
- `prerequisite_knowledge`, `knowledge_integration_demand`
- `representation_shift_required`, `response_format_demand`
- `guessability`, `notes`

### 16.5 Benchmark freezing rule update

Question-set construction remains rule-driven and stays outside the generation path.

- `question_selection_mode = difficulty_balanced`
  - first filters candidate XES items by `min_item_response_count`
  - then splits the eligible pool into threshold-based `hard / medium / easy` bands by real item accuracy
  - default thresholds:
    - `hard`: `< 0.5`
    - `medium`: `0.5 - 0.75`
    - `easy`: `> 0.75`
  - then samples the same number of items from each band to form a frozen benchmark
- `min_item_response_count`
  - is a benchmark-quality control threshold only
  - must not be used by any semantic module or answer generation module
- frozen selected items should be exported so later runs use the same benchmark definition instead of silently drifting

### 16.6 Step-by-step generation contract

Default production path:

- `method_variant = state_step`
- `generate_student_answer(...)` runs a bounded step-by-step internal thinking loop

Main loop:

`ItemResponseState + ConstraintBundle + thinking_history -> one incremental thinking step -> ... -> final_answer`

Rules:
- each LLM call may output only one incremental thought step
- the full prior `thinking_history` must be passed into the next step
- the model must decide `continue` or `final_answer` itself
- if the model notices it is circling, it should stop and emit the best current answer
- the effective step cap is `min(global max_thinking_steps, constraint_bundle.max_thinking_steps)`
- if `remaining_step_budget = 1`, the last allowed step must end with `final_answer`
- if the loop exceeds the effective step cap, the run must fail explicitly; no fallback answer is allowed
- each step must stay brief; it should not restate the whole prior history

Step output schema:
- `internal_thought`
- `next_action`
- `decision_reason`
- `predicted_answer`
- `student_response`

Field consistency:
- if `next_action = continue`, then `predicted_answer = ""` and `student_response = ""`
- if `next_action = final_answer`, then both must be non-empty

Output logging:
- full `thinking_trace` is stored in `predictions.jsonl`
- `thinking_steps_n` is stored in `predictions.jsonl` and `predictions_compact.jsonl/.csv`

Config:
- `max_thinking_steps` is a required runtime control for the bounded loop
- this is a global hard ceiling only, not a fallback mechanism
- actual per-item step budget is further constrained by `ConstraintBundle.max_thinking_steps`

Root-cause experiment-only method ablations:

- `method_variant = direct`
  - keeps `StudentModel`, implementation-derived signals, and `ProblemRequirementProfile`
  - skips `ItemResponseState` and `ConstraintBundle`
  - generates the final answer directly in one call
- `method_variant = state_single`
  - keeps `ItemResponseState` and `ConstraintBundle`
  - forces the answer stage to finish in exactly one final-answer step
  - still keeps the same violation check and optional single retry
- `method_variant = state_step`
  - current default main method
  - keeps bounded multi-step generation, violation check, and optional single retry

These ablation branches are for diagnosis only. They do not change the default main method contract.

### 16.7 Schema validation retry rule

For LLM modules that must emit structured JSON objects, one schema-driven regeneration is allowed when:
- JSON parsing succeeded
- but required keys / nested objects / enum values fail schema validation

This retry is rule-governed infrastructure behavior, not semantic fallback.
It is allowed for:
- `build_student_model(...)`
- implementation-level signal mapping

Constraints:
- at most one extra regeneration
- must use the same semantic task
- must not inject real labels, target metrics, or answer supervision
- if schema still fails after the retry, the run must fail explicitly

For step-by-step generation, one protocol-driven regeneration is also allowed only when:
- the model is already on the last allowed step
- but still violates the terminal-step contract

This retry is still rule-governed protocol correction, not semantic fallback.
