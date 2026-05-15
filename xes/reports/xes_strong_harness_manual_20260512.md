# XES 强模型 Harness 方法说明书（2026-05-12）

## 1. 方法定位

XES 强模型 harness 面向的是**静态单题学生作答模拟**。

它要解决的问题是：

> 给定一个学生画像和一道数学题，模拟这个学生在这道题上的作答表现。

这里的重点不是让大模型自由解题，而是让大模型先理解：

- 这个学生大概是什么水平；
- 这道题真正要求什么能力；
- 这个学生遇到这道题时，最可能卡在哪里；
- 当前回答应该成熟到什么程度。

所以它不是普通的“让模型扮演学生”，而是：

> 先做第三人称状态判断，再在状态约束内生成学生答案。

---

## 2. 方法思想

XES 强模型 harness 的核心思想可以概括为：

> 学生作答不是由题目单独决定，也不是由学生画像单独决定，而是由“学生能力 × 题目要求”的交互决定。

因此，系统不能直接从画像跳到答案。  
中间必须有一层明确的状态判断：

- 题目对这个学生是否可达；
- 学生是否掌握前置知识；
- 这道题更可能触发哪类错误；
- 当前回答应该是完整解法、局部尝试、猜测，还是错误答案。

这套方法借鉴了三类理论：

- **Assessment Triangle**：学生模型、观察证据、解释过程要分开。
- **Evidence-Centered Design**：先定义要推断的学生状态，再决定需要哪些证据。
- **IRT / Rasch 思路**：学生能力和题目难度可以作为离线分析参照，但当前主线不再把题目难度信号直接送进 generation path。

参考：

- National Research Council, *Knowing What Students Know*：<https://www.nationalacademies.org/read/10019/chapter/4>
- Evidence-Centered Design 介绍：<https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.00853/full>

---

## 3. 方法流程

主链路是：

`Student Persona -> StudentModel -> ProblemRequirementProfile -> StudentItemInteractionDecision -> ItemResponseState -> ConstraintBundle -> Student Answer`

### 3.1 学生建模

系统先把学生画像转成 `StudentModel`。

这个对象不只是记录“学生强还是弱”，还会分析：

- 自我效能；
- 自我调节；
- 控制感和价值感；
- 参与倾向；
- 回答风格；
- 数学任务能力锚点。

如果有真实 XES 历史作答信息，系统会把它转成更具体的数学能力信号，例如：

- easy / medium / hard 题表现；
- 不同题型表现；
- 不同能力点表现；
- 猜测倾向；
- 格式敏感性。

### 3.2 题目建模

然后把题目转成 `ProblemRequirementProfile`。

它描述的是：

- 这道题需要哪些前置知识；
- 操作复杂度有多高；
- 是否需要多步推理；
- 是否需要表征转换；
- 答案格式是否严格；
- 是否容易猜。

这一步的作用是把“题面文字”转成“能力要求”。

当前主线已经去掉 difficulty 信号：

- 不传 few-shot 难度对照；
- 不传真实 difficulty band；
- 只让模型根据题面和学生状态判断学生-题目交互。

这样做的原因是 2026-05-12 的模块审计发现：difficulty 信号能提高 item-level 难度结构相关性，但会伤害 `overall_consistency` 和 student-level 对齐。

### 3.3 学生-题目交互判断

接着系统进入 `StudentItemInteractionDecision`。

这一层回答：

- 这道题对这个学生是否可达；
- 更像是能做对、接近做对、还是容易做错；
- 主要风险来自知识缺口、步骤错误、格式错误，还是误用规则；
- 学生是否可能猜对。

这是整条链里最关键的第三人称判断层。

### 3.4 单题作答状态

系统不会直接从交互判断跳到答案，而是先生成 `ItemResponseState`。

它规定：

- 当前允许多完整的解释；
- 是否应该明确给出答案；
- 是否更像局部尝试；
- 是否应该保留不确定性；
- 是否允许表现出具体错误。

### 3.5 约束编译

再把状态编译成 `ConstraintBundle`。

约束包括：

- 最多几句；
- 最多几步内部思考；
- 是否允许完整解法；
- 是否必须给出答案；
- 是否禁止过度成熟；
- 是否偏向某种错误路径。

### 3.6 答案生成

最后才让强模型生成答案。

此时强模型已经不是自由 solver，而是被这些对象约束住的 student actor。

---

## 4. 代码入口

主入口：

- `D:\Study\sii\MathStudent\xes\run_experiments.py:1`

核心模块：

- `D:\Study\sii\MathStudent\xes\src\student_model.py:1`
- `D:\Study\sii\MathStudent\xes\src\problem_profile.py:1`
- `D:\Study\sii\MathStudent\xes\src\student_item_interaction.py:1`
- `D:\Study\sii\MathStudent\xes\src\response_state.py:1`
- `D:\Study\sii\MathStudent\xes\src\generation.py:1`
- `D:\Study\sii\MathStudent\xes\src\evaluation.py:1`

常用配置：

- `D:\Study\sii\MathStudent\xes\configs\run_local_9501_qwen.json:1`
- `D:\Study\sii\MathStudent\xes\configs\common_test_60x96_20260507.json:1`

---

## 5. 输入和输出

输入包括：

- 学生 persona；
- XES 真实作答日志；
- 题目元数据；
- 运行配置。

输出包括：

- `student_models.jsonl`
- `student_signals.jsonl`
- `problem_profiles.json`
- `predictions.jsonl`
- `metrics.json`

这些输出不是只为了留结果，而是为了审计：

> 每一道题的答案到底是从哪种学生状态、哪种题目要求、哪种约束中生成出来的。

---

## 6. 评测方式

XES 强模型 harness 当前主要看：

- 整体正确率；
- 学生分层表现；
- item-level Pearson / Spearman；
- student-level Pearson / Spearman；
- overall consistency。

固定 common-test 报告：

- `D:\Study\sii\MathStudent\xes\reports\common_test_60x96_harness_report_20260508.md:1`

---

## 7. 方法边界

这个方法允许：

- 使用学生历史作答构建能力锚点；
- 使用题目统计做离线分析和消融对照；
- 使用强模型做第三人称状态推断；
- 在约束内生成学生作答。

这个方法不允许：

- 直接把真实答案塞进生成路径；
- 默认把真实题目 difficulty band 塞进生成路径；
- 根据评测结果反向修答案；
- 跳过状态层直接 role-play；
- 用题目 ID 或学生 ID 写特判。

---

## 8. 当前优缺点

优点：

- 方法链路清楚；
- 保留第三人称状态层；
- 能区分学生强弱；
- 比直接 role-play 更可审计。

短板：

- 题目级错误模式仍不够稳；
- 更容易把握学生总体水平，不够擅长判断具体哪道题会错；
- 仍是静态单题方法，不处理长对话中的状态更新。

---

## 9. 总结

XES 强模型 harness 的本质是：

> 用强模型做受控的单题学生作答模拟。它不是自由解题，而是先判断学生状态和题目要求，再在约束边界内生成学生答案。
