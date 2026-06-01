# HACHIMII 学生模拟元方法报告

## 1. 研究问题

本研究关注的问题不是“如何让大模型更像学生说话”，而是：

> 如何构建一套可迁移、可审计、可适配不同教育任务的学生模拟方法？

现有 LLM 学生模拟容易走向直接 role-play：把学生历史、当前题目或对话历史放进 prompt，然后要求模型“扮演这个学生”。这种方式短期看方便，但有三个明显问题：

- 模型为什么这样回答不清楚；
- 换数据集或换学科时 prompt 很难复用；
- 很容易为了指标把真实标签、未来信息或评测偏好写进生成链。

因此，HACHIMII 的核心思路是：

> 不直接让模型扮演学生，而是先拆解模拟过程，再在第三人称状态边界内生成当前一步学生行为。

---

## 2. 核心 insight

HACHIMII 的核心 insight 可以概括为三句话：

1. 学生模拟不应该是一个端到端 role-play prompt，而应该被拆成若干可审计的中间建模步骤。
2. 这些步骤在不同任务中具有共同结构，但每一步需要填入的信息应由具体任务和具体学科理论决定。
3. 因此，可迁移的不是某个 prompt，而是“先找坑位，再找理论萝卜，再生成行为”的元方法。

这里的“坑位”是指所有学生模拟任务都需要回答的共同问题；“萝卜”是指不同任务中用于填充这些问题的具体理论、字段和数据。

---

## 3. 元方法总框架

HACHIMII 将学生模拟拆成六个核心坑位：

`Learner Context -> Task / Interaction Context -> Learner-Task Fit -> State Layer -> Harness / Constraint -> Surface Realization`

这六个坑位分别回答：

| 坑位 | 要回答的问题 | 典型内容 |
|---|---|---|
| Learner Context | 学生是谁 | 年龄、年级、历史表现、能力水平、强弱项、元画像 |
| Task / Interaction Context | 当前任务是什么 | 题目、知识点、对话历史、当前教师轮次、学科要求 |
| Learner-Task Fit | 这个学生遇到这个任务会怎样 | 匹配关系、卡点、误解、错误机制、猜测或求助倾向 |
| State Layer | 当前学生处在什么状态 | 理解程度、信心、策略、错误机制、可推进深度 |
| Harness / Constraint | 生成边界是什么 | 回答长度、推理深度、是否允许完整答案、是否保留不确定性 |
| Surface Realization | 当前一步学生行为是什么 | 单题答案、短解释、当前学生回复、局部错误表达 |

这套框架的关键不是要求所有任务使用同一批字段名，而是要求所有任务都显式回答这些问题。

---

## 4. Context 与 Harness 的分工

HACHIMII 可以从两个核心概念理解：`context` 和 `harness`。

### 4.1 Context：告诉系统当前能看见什么

Context 负责整理当前时点真实可见的信息。

它包括两部分：

- 学生侧 context：学生历史、能力水平、稳定特征、HACHIMI 元画像；
- 任务侧 context：当前题目、当前对话、当前教师轮次、当前学科要求。

Context 的纪律是：只允许使用当前时点可见的信息，不能把真实标签、未来回复、评测注释或离线统计指标放入 generation path。

### 4.2 Harness：告诉系统当前允许生成到哪里

Harness 负责把第三人称状态判断翻译成可执行的生成边界。

它不是给答案，也不是让模型更像学生的风格补丁，而是限制模型：

- 当前最多能答到什么程度；
- 是否应该完整推理；
- 是否应该暴露不确定性；
- 是否应该保留错误；
- 是否只能生成当前一步，不能提前生成未来步骤。

因此，HACHIMII 的生成不是自由生成，而是 harnessed generation。

---

## 5. 静态模拟中的实例化

静态模拟的任务形式是：

> 给定一个学生的历史记录和一道当前题目，预测该学生在这道题上的当前作答。

静态链路可以写成：

`StudentModel -> ProblemRequirementProfile -> ItemResponseState -> ConstraintBundle -> Response`

对应关系是：

- `StudentModel`：学生长期 context；
- `ProblemRequirementProfile`：当前题目的任务 context；
- `ItemResponseState`：学生面对该题的第三人称状态；
- `ConstraintBundle`：当前作答边界；
- `Response`：最终学生作答。

在 XES、EEDI-static 和 ENEM 中，静态模拟的共同点都是“学生 × 题目”的单步状态判断；不同点在于题目和学科理论不同。

例如：

- XES / EEDI-static 是数学题，需要关注数学知识点、题型、计算/推理要求、常见误解；
- ENEM 自然科学题需要关注科学实践、跨领域概念、自然科学能力矩阵、图文混合信息理解。

---

## 6. 动态模拟中的实例化

动态模拟的任务形式是：

> 给定当前轮之前的完整可见对话和当前 tutor turn，生成当前这一轮学生回复。

动态链路可以写成：

`StudentModel -> DialogueContextState -> TutorTurnProfile -> StudentTurnState -> ConstraintBundle -> StudentTurn -> StateUpdate`

对应关系是：

- `StudentModel`：学生长期 context；
- `DialogueContextState`：到当前为止的对话状态；
- `TutorTurnProfile`：当前教师轮次在做什么；
- `StudentTurnState`：学生当前交互状态；
- `ConstraintBundle`：当前轮回复边界；
- `StudentTurn`：当前学生回复；
- `StateUpdate`：当前轮后学生状态变化。

动态模拟和静态模拟的骨架相同，但动态任务多了对话历史、当前教师意图和状态更新。

---

## 7. 理论适配原则

HACHIMII 不要求不同任务使用同一个理论，而是要求：

> 每个坑位都必须由任务相关理论来支撑。

例如：

- 数学任务可以使用数学教育、认知诊断、误概念、解题策略等理论；
- 自然科学任务可以使用 ENEM 官方能力矩阵、NRC / NGSS 三维科学学习框架、PISA Science Framework；
- 动态辅导对话任务可以使用 instructional scaffolding、dialogue act、tutoring interaction、self-regulated learning 等理论。

可引用的理论来源包括：

- Wood, Bruner, and Ross, 1976, *The role of tutoring in problem solving*：<https://pubmed.ncbi.nlm.nih.gov/932126/>
- Next Generation Science Standards / NRC K-12 science framework：<https://www.nextgenscience.org/>
- OECD PISA 2025 Science Framework：<https://pisa-framework.oecd.org/science-2025/>

这就是“坑位—萝卜”原则：

- 坑位是共同的；
- 萝卜是任务特定的；
- 迁移时保留坑位，更换萝卜。

---

## 8. 方法边界

为了保证方法站得住，HACHIMII 明确不做以下事情：

- 不直接 role-play 学生；
- 不跳过第三人称状态层；
- 不把真实标签、未来回复或官方评测注释放进生成链；
- 不用题号、学生号或数据集特例做特判；
- 不靠后处理修改答案；
- 不靠一堆“更像学生一点”的 prompt 补丁堆结果。

如果一个实现不能解释自己的 context、state 和 harness，那么它就不属于 HACHIMII 元方法。

---

## 9. 与现有研究的区别

HACHIMII 的定位是：

> 理论引导的 context-harness student simulation meta-method。

它和三类已有方向不同：

1. **不同于传统学生建模**  
   传统方法多预测能力、知识状态或作答正确率；HACHIMII 进一步生成可观察的学生行为。

2. **不同于直接 LLM role-play**  
   直接 role-play 让模型自由扮演学生；HACHIMII 先构建第三人称状态，再受限生成。

3. **不同于单数据集 prompt 工程**  
   prompt 工程通常绑定某个任务；HACHIMII 提供的是可迁移的模拟过程拆分原则。

---

## 10. 贡献总结

HACHIMII 的贡献可以概括为三点：

1. **方法贡献**  
   提出一套可迁移的学生模拟元方法，将学生模拟拆成 context、state、harness 和 action 等可审计环节。

2. **适配贡献**  
   说明同一套元方法可以适配静态做题、动态辅导对话、数学题和自然科学题等不同任务形态。

3. **工程贡献**  
   给出可运行、可检查、generation/evaluation 隔离的 pipeline，使合作者可以按“坑位—萝卜”原则迁移到自己的项目。

---

## 11. 对外最终表述

可以这样介绍本研究：

> We propose HACHIMII, a context-harness meta-method for student simulation. Instead of directly prompting an LLM to role-play a student, HACHIMII decomposes simulation into learner context construction, task or interaction context modeling, learner-task fit analysis, third-person state inference, constraint compilation, and surface behavior realization. This decomposition makes student simulation more interpretable, auditable, and transferable across static answering tasks, dynamic tutoring dialogues, and different subject domains.
