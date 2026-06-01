# XES 弱模型 Harness 方法说明书（2026-05-12）

## 1. 方法定位

XES 弱模型 harness 面向的仍然是**静态单题学生作答模拟**。

它和 XES 强模型 harness 的区别不在任务，而在分工：

- 强模型负责理解学生、理解题目、编译支架；
- 弱模型负责在支架内生成学生答案。

所以这条方法不是“让弱模型自己做题”，而是：

> 用强模型搭建作答边界，再让弱模型在边界内完成学生式表面作答。

---

## 2. 为什么需要弱模型 harness

强模型很容易过度解题。  
它常见的问题是：

- 太快给出完整答案；
- 解释过于成熟；
- 不像真实学生的局部尝试；
- 把本该不稳定的学生状态写得太稳定。

弱模型有另一种风险：

- 不会稳定做题；
- 容易格式漂移；
- 容易答非所问；
- 容易把“不懂”变成噪声。

因此，弱模型 harness 的目标不是压制弱模型，也不是放任弱模型，而是：

> 把强模型的理解能力转成弱模型能执行的支架，让弱模型只负责当前题目的学生式回答。

---

## 3. 方法思想

XES 弱模型 harness 的核心思想是：

> 学生模拟可以拆成“状态编译”和“表面实现”两件事。

强模型适合做状态编译：

- 分析学生历史；
- 分析题目要求；
- 判断当前风险；
- 生成支架卡片。

弱模型适合做表面实现：

- 给出短答案；
- 保留局部不成熟；
- 不写过度完整的解题过程；
- 体现学生式表达。

这条方法对应教育里的 scaffolding 思想：

> 支架不是替学生完成任务，而是把任务压到学生当前能处理的局部范围。

参考：

- Instructional scaffolding 背景：<https://en.wikipedia.org/wiki/Instructional_scaffolding>
- Evidence-Centered Design 介绍：<https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.00853/full>

---

## 4. 方法流程

主链路是：

`Student History -> StudentModel / ProblemProfile -> SupportProfile -> StudentState / TaskState -> ScaffoldBudget -> PromptLadder / RiskCard / ResponseProtocol -> Weak Answer`

### 4.1 构建学生条件

系统先从真实 XES 作答历史里构建 benchmark student。

每个学生包含：

- 历史题目；
- 测试题目；
- 历史正确率；
- 不同难度表现；
- 不同题型表现；
- 匹配到的 Hachimi persona。

### 4.2 强模型构建学生模型和题目模型

强模型负责构建：

- `StudentModel`
- `ProblemRequirementProfile`

这一步和强模型 harness 一样，仍然保留第三人称状态判断。

### 4.3 构建 task support profile

接着系统构建 `TaskSupportProfile`。

它回答：

- 这道题对这个学生主要难在哪里；
- 当前需要什么支架；
- 哪些错误风险最高；
- 弱模型应该避免哪些越界行为。

### 4.4 编译弱模型卡片

系统再把复杂对象压缩成弱模型可执行的几张卡：

- `student_state`
- `task_state`
- `scaffold_budget`
- `prompt_ladder`
- `risk_card`
- `response_protocol`

这些卡片的作用是：

> 把复杂推断翻译成弱模型能遵守的简单作答协议。

### 4.5 弱模型生成答案

弱模型读取这些卡片后，只输出：

- `predicted_answer`
- `student_response`
- `used_support_level`
- `support_trace`

它不需要独立完成完整解题。  
它只需要在支架里生成一个合理的学生回答。

### 4.6 输出校验

生成后会用 `validate_answer_output` 检查：

- 字段是否齐；
- 答案格式是否合法；
- 是否违反 response protocol。

不合法就失败，不做静默兜底。

---

## 5. 代码入口

主入口：

- `D:\Study\sii\MathStudent\xes\weak_model_harness\run_weak_student_benchmark.py:1`

依赖的 benchmark 基础设施：

- `D:\Study\sii\MathStudent\xes\run_student_conditioned_benchmark.py:1`
- `D:\Study\sii\MathStudent\xes\src\student_conditioned_benchmark.py:1`

weak harness 模块：

- `D:\Study\sii\MathStudent\xes\weak_model_harness\src\compile_cards.py:1`
- `D:\Study\sii\MathStudent\xes\weak_model_harness\src\support_profile.py:1`
- `D:\Study\sii\MathStudent\xes\weak_model_harness\src\weak_actor.py:1`
- `D:\Study\sii\MathStudent\xes\weak_model_harness\src\validate.py:1`

---

## 6. 运行方式

主命令形式：

`python xes/weak_model_harness/run_weak_student_benchmark.py --strong_llm_base_url ... --strong_llm_model ... --weak_llm_base_url ... --weak_llm_model ...`

必须提供两套模型配置：

- strong LLM：负责编译状态和支架；
- weak LLM：负责最终作答。

---

## 7. 输出和评测

典型输出包括：

- `benchmark_summary.json`
- `benchmark_students.jsonl`
- `problem_profiles.json`
- `task_support_profiles.json`
- `student_models.jsonl`
- `predictions.jsonl`
- `metrics.json`

评测仍然围绕：

- 是否答对；
- 是否和真实学生对错一致；
- 学生层级表现；
- 题目层级表现。

---

## 8. 方法边界

允许：

- 用强模型分析学生和题目；
- 用强模型编译支架；
- 用弱模型执行表面作答；
- 用显式协议校验输出。

不允许：

- 直接把标准答案塞给弱模型；
- 让弱模型无支架自由答题；
- 为了指标后处理改答案；
- 用题目 ID 或学生 ID 做特判。

---

## 9. 当前优缺点

优点：

- actor 更容易保持学生式短答；
- 支架对象可审计；
- 能研究“强编译器 + 弱 actor”的分工。

短板：

- 弱模型本身能力不稳；
- 效果高度依赖支架质量；
- 如果支架不清楚，弱模型容易漂移。

---

## 10. 总结

XES 弱模型 harness 的本质是：

> 强模型负责把学生和题目的交互状态编译成支架，弱模型负责在支架里生成学生答案。它不是弱模型自由做题，而是支架化的弱 actor 学生模拟。
