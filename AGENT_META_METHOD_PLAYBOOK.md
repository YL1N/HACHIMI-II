# HACHIMII Agent 元方法迁移手册

这份文档是给 Codex / coding agent 看的，不是论文报告。

目标是让 agent 能把 HACHIMII 学生模拟元方法迁移到一个新的教育任务项目中。

---

## 1. 你的任务

当用户要求你把 HACHIMII 用到一个新项目时，你要做的不是直接写一个“扮演学生”的 prompt。

你要做的是：

> 先把新任务拆成 HACHIMII 的六个坑位，再基于这些坑位实现一个可审计、可运行、generation/evaluation 隔离的学生模拟 pipeline。

六个坑位是：

`Learner Context -> Task / Interaction Context -> Learner-Task Fit -> State Layer -> Harness / Constraint -> Surface Realization`

---

## 2. 第一原则

必须遵守：

1. **不直接 role-play 学生**  
   不能从 `context -> answer` 直接生成学生行为。

2. **必须有第三人称状态层**  
   必须先判断学生当前状态，再生成行为。

3. **必须有 harness / constraint 层**  
   状态必须被翻译成生成边界，不能只作为说明文字摆着。

4. **只生成当前一步**  
   静态任务只生成当前题作答；动态任务只生成当前轮学生回复。

5. **generation 和 evaluation 必须隔离**  
   真实标签、未来回复、官方评测注释、离线统计指标只能用于评测，不能进入生成链。

6. **不做 ID 特判和后处理改答案**  
   不能按题号、学生号、样本号写特例，也不能生成后为了指标改输出。

---

## 3. 迁移前先回答的问题

在写代码之前，先产出一份任务适配设计。

至少回答下面问题。

### 3.1 Action：最终要生成什么

先确定当前任务的学生行为是什么。

例子：

- 一道题的答案；
- 一段学习工具操作；
- 当前一轮对话回复；
- 一个认知任务里的下一步选择；
- 一个实验操作步骤。

如果 Action 不清楚，不要开始写 pipeline。

### 3.2 Learner Context：学生是谁

列出当前任务开始前可以知道的学生信息。

可能包括：

- 年龄、年级、学习阶段；
- 历史答题；
- 历史对话；
- 历史工具使用轨迹；
- 能力水平；
- 稳定强弱项；
- 学习动机、风格、偏好、非认知特征；
- 可选的 HACHIMI 元画像匹配结果。

注意：只能使用当前时点可见的信息。

### 3.3 Task / Interaction Context：当前任务是什么

列出当前这一步任务的输入。

静态任务可能包括：

- 当前题目；
- 当前材料；
- 当前工具界面；
- 当前操作要求；
- 当前学科能力要求。

动态任务可能包括：

- 当前轮之前的完整可见历史；
- 当前教师或系统发言；
- 当前工具状态；
- 当前交互目标；
- 当前轮次位置。

### 3.4 Learner-Task Fit：学生遇到任务会怎样

判断学生 context 和任务 context 的关系。

需要描述：

- 哪些要求正好落在学生强项；
- 哪些要求落在学生弱项；
- 可能卡在哪里；
- 可能误解什么；
- 是否可能猜测、求助、放弃、跳步或机械执行；
- 当前任务是否超出学生能力边界。

### 3.5 State Layer：第三人称状态是什么

设计一个结构化状态对象。

它必须回答：

- 当前理解程度；
- 当前策略；
- 当前错误机制；
- 当前信心；
- 当前可推进深度；
- 当前是否需要帮助；
- 当前是否会表现出犹豫、误解、猜测或局部正确。

状态字段必须会影响后面的 harness 和 generation。

### 3.6 Harness / Constraint：允许生成到哪里

把状态翻译成生成边界。

至少定义：

- 输出长度；
- 输出格式；
- 是否允许完整推理；
- 是否允许直接给最终答案；
- 是否应该暴露不确定性；
- 是否应该保留错误；
- 是否只能回应当前一步；
- 哪些内容绝对不能生成。

### 3.7 Evaluation：离线评测如何做

评测可以使用真实标签和未来信息，但必须离线使用。

要明确：

- 评测指标是什么；
- 哪些字段只用于评测；
- 哪些字段绝对不能进入 generation；
- 如何保存中间对象，方便审计。

---

## 4. 推荐实现顺序

按这个顺序做，不要反过来。

1. 写任务适配设计文档。
2. 定义数据结构：student、task、state、constraint、prediction。
3. 实现数据加载，只保留 generation 当前时点可见字段。
4. 实现 Learner Context 构建。
5. 实现 Task / Interaction Context 构建。
6. 实现 Learner-Task Fit。
7. 实现 State Layer。
8. 实现 Harness / Constraint。
9. 实现 Surface Realization。
10. 实现 evaluation，确保和 generation 隔离。
11. 写 smoke test。
12. 写 README 和运行命令。

---

## 5. 推荐代码形状

不要强行做大一统框架。

如果项目是静态模拟，可以用：

```text
run_static_benchmark.py
src/
  data_loading.py
  learner_context.py
  task_context.py
  fit_profile.py
  state_layer.py
  constraint.py
  generation.py
  evaluation.py
  llm_client.py
tests/
```

如果项目是动态模拟，可以用：

```text
run_dynamic_benchmark.py
src/
  data_loading.py
  learner_context.py
  dialogue_context.py
  tutor_or_system_turn.py
  turn_state.py
  constraint.py
  generation.py
  state_update.py
  evaluation.py
  llm_client.py
tests/
```

实际命名可以变，但职责边界要清楚。

---

## 6. Prompt 编写规则

Prompt 必须服务对象层，不要变成补丁墙。

每个 prompt 都要清楚说明：

- 当前输入是什么；
- 当前要构建哪个对象；
- 对象字段是什么意思；
- 不允许使用哪些信息；
- 输出 JSON schema 是什么。

禁止写：

- “尽量像真实学生”；
- “让结果更接近真实标签”；
- “如果不确定就猜一个更可能正确的”；
- “为了让评测更好……”；
- “参考真实学生下一句……”。

---

## 7. 自检清单

提交前逐项检查。

### 7.1 方法是否成立

- 是否有第三人称状态对象？
- 状态对象是否真的影响 constraint？
- constraint 是否真的影响 generation？
- 是否只生成当前一步？
- 是否可以解释模型为什么这样生成？

### 7.2 数据是否干净

- generation 是否只用了当前时点可见信息？
- 是否把真实标签放进 prompt？
- 是否把未来回复放进 prompt？
- 是否用了离线题目难度或目标指标？
- 是否存在题号、学生号、样本号特判？

### 7.3 工程是否可审计

- 是否保存了中间对象？
- 是否有失败样本记录？
- 是否没有静默 fallback？
- 是否有 smoke test？
- 是否有 README 或运行说明？

---

## 8. 给用户的首轮输出模板

当用户让你迁移 HACHIMII 到新项目时，首轮不要直接写代码。

先输出：

```text
我会先按 HACHIMII 元方法拆这个任务，不直接写 role-play prompt。

初步需要确认：
1. 当前任务最终要生成的学生行为是什么？
2. 当前时点可见的学生信息有哪些？
3. 当前任务/交互上下文有哪些？
4. 真实标签、未来信息、评测注释分别在哪里，如何隔离？

然后我会给出六个坑位设计：
Learner Context / Task or Interaction Context / Learner-Task Fit / State Layer / Harness / Surface Realization。
```

如果这些信息可以从代码或数据中读到，就主动探索，不要反复问用户。

---

## 9. 最小可运行版本标准

一个最小可运行迁移版至少要做到：

- 能读取一小批样本；
- 能构建 learner context；
- 能构建 task / interaction context；
- 能输出第三人称 state；
- 能输出 constraint；
- 能生成当前一步 action；
- 能离线计算至少一个基础指标；
- 能保存中间对象；
- 有一个 smoke test。

没有第三人称 state 的版本不算 HACHIMII。

---

## 10. 一句话提醒

如果你发现自己在做这些事，立刻停下来：

- 直接让模型扮演学生；
- 不建状态对象；
- 不建约束对象；
- 为了指标改 prompt；
- 用真实标签控制生成；
- 生成后改答案；
- 写一堆任务特判。

回到六个坑位，从 context、state、harness 重新设计。

