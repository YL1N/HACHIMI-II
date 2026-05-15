# EEDI 强模型 Harness 方法说明书（2026-05-12）

## 1. 方法定位

EEDI 强模型 harness 面向的是**数学辅导对话中的 turn-level 学生模拟**。

它要解决的问题是：

> 给定当前 tutor-student 对话历史，预测学生下一轮会如何回应。

它和 XES 单题作答不同。  
XES 关心“学生遇到某道题会怎么答”，EEDI 关心：

- tutor 这一轮刚刚做了什么；
- 学生当前听懂了多少；
- 学生会接着说一句什么；
- 这句话体现的是理解、困惑、尝试、修正，还是错误延续。

因此，EEDI 强模型 harness 本质上是：

> 对话场景下的第三人称状态推进生成法。

---

## 2. 方法思想

EEDI 强模型 harness 的核心不是 role-play。

它不直接做：

`历史对话 -> 下一句学生回复`

而是做：

`历史对话 -> 学生当前状态 -> tutor 当前动作 -> 学生状态转移 -> 错误蓝图 -> 约束包 -> 当前学生回复`

这个设计来自四个教育思想：

- **Assessment Triangle**：学生状态、可观察证据、解释过程要分开；
- **Evidence-Centered Design**：先定义当前 turn 要推断什么，再决定哪些历史信息是证据；
- **ZPD / Scaffolding**：学生当前能说什么，取决于 tutor 当前支持打开了什么局部空间；
- **ICAP**：学生回复不仅有内容，还有参与方式。

参考：

- National Research Council, *Knowing What Students Know*：<https://www.nationalacademies.org/read/10019/chapter/4>
- Evidence-Centered Design：<https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.00853/full>
- ICAP framework：<https://icap.education.asu.edu/research>

---

## 3. 方法流程

主链路是：

`DialogueContextState -> StudentContextProfile -> TutorTurnProfile -> InteractionState -> StateTransitionPrediction -> ErrorBlueprint -> ConstraintBundle -> StudentTurn`

### 3.1 DialogueContextState

先整理当前可见对话。

它只包含：

- 当前 turn 之前的 tutor/student 历史；
- 当前题目文本；
- subject 信息；
- 最新 tutor turn；
- 上一个 student turn。

它不允许包含：

- 真实下一句学生回复；
- 当前 turn 之后的未来对话；
- 官方评测标签；
- correctness / acts / kcs 等注释。

### 3.2 StudentContextProfile

基于当前历史，系统推断学生当前画像。

它描述：

- 学生当前自我效能；
- 当前参与倾向；
- 当前控制感和价值感；
- 当前回答风格；
- 当前是否表现出困惑、猜测、回避或尝试。

这不是静态 persona，而是当前对话位置上的学生状态。

### 3.3 TutorTurnProfile

系统再分析 tutor 当前回合。

它回答：

- tutor 是在提示、追问、纠错、澄清，还是管理对话；
- 支持强度有多大；
- 支持颗粒度多细；
- 是否贴合学生前一轮状态；
- 当前局部数学对象是什么。

### 3.4 InteractionState

然后判断学生在这一轮前后的交互状态。

例如：

- 当前是否可达；
- 是否已经有局部理解；
- 是否需要帮助；
- 是否可能直接回答；
- 是否更可能给出片段、猜测或澄清。

### 3.5 StateTransitionPrediction

这一步预测：

> tutor 当前回合之后，学生最可能被推进到什么局部状态。

它不是预测最终学会没有，也不是预测未来多轮，只预测当前下一句前的状态变化。

### 3.6 ErrorBlueprint

如果当前状态支持错误外显，系统会构建错误蓝图。

错误蓝图包括：

- 是否存在具体错误；
- 错误属于什么知识类型；
- 错在解题流程哪个位置；
- 错误机制是什么；
- 是否存在局部错误 claim seed。

它定义的是错误边界，不是直接写 gold-like 错句。

### 3.7 ConstraintBundle

系统把前面的状态编译成生成约束。

约束包括：

- 最多几句；
- 是否允许完整解释；
- 是否允许直接答案；
- 是否必须保留局部困惑；
- 是否需要体现具体错误；
- 是否禁止过度成熟。

### 3.8 StudentTurn

最后才生成当前学生回复。

这一步只生成当前 turn。  
不生成后续对话，不提前规划未来。

---

## 4. Population Calibration

当前强模型主线加入了 `population calibration`。

这层的作用是：

> 用少量真实学生样本校准“这个学生群体在类似局部情境中常见的错误模式”。

它不直接告诉模型下一句应该怎么说。  
它只作为第三人称状态判断的群体先验。

当前配置使用：

- `train200`
- `top_k = 8`
- `structural_only`

相关文件：

- `D:\Study\sii\MathStudent\eedi\src\population_calibration.py:1`
- `D:\Study\sii\MathStudent\eedi\build_population_calibration_bank.py:1`

---

## 5. 代码入口

主入口：

- `D:\Study\sii\MathStudent\eedi\run_eedi_experiments.py:1`

核心模块：

- `D:\Study\sii\MathStudent\eedi\src\dialogue_context.py:1`
- `D:\Study\sii\MathStudent\eedi\src\student_model.py:1`
- `D:\Study\sii\MathStudent\eedi\src\tutor_turn_profile.py:1`
- `D:\Study\sii\MathStudent\eedi\src\student_turn_state.py:1`
- `D:\Study\sii\MathStudent\eedi\src\transition.py:1`
- `D:\Study\sii\MathStudent\eedi\src\error_blueprint.py:1`
- `D:\Study\sii\MathStudent\eedi\src\constraint_bundle.py:1`
- `D:\Study\sii\MathStudent\eedi\src\generation.py:1`

当前全量配置：

- `D:\Study\sii\MathStudent\eedi\configs\run_strong_population_calibrated_full4334_20260511.json:1`

---

## 6. 输出和评测

典型输出包括：

- `predictions.jsonl`
- `stage_traces.jsonl`
- `turn_level_predictions.csv`
- `official_eval_input.csv`
- `metrics.json`
- `task_retry_events.jsonl`

当前主看五个指标：

- `consistency`
- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

detached eval 入口：

- `D:\Study\sii\MathStudent\eedi\run_detached_eval.py:1`

---

## 7. 方法边界

允许：

- 使用当前 turn 前的历史；
- 使用题目和 subject 信息；
- 使用少量训练样本形成群体先验；
- 让强模型做第三人称状态推断。

不允许：

- 使用真实下一句学生回复；
- 使用未来对话；
- 使用官方标签进入生成；
- 为了指标改写输出；
- 跳过状态层直接生成。

---

## 8. 当前状态

截至 2026-05-12，EEDI 强模型 harness 是后续主线。

原因是：在全量 4334 task 对照中，它在五个核心指标里整体强于 weak harness，尤其在：

- `consistency`
- `error_realization`

上更值得继续推进。

当前短板是：

- `consistency` 仍不够高；
- population calibration 提高错误外显的同时，可能会伤一部分正确/错误一致性；
- 个别样本存在 JSON 截断导致运行不稳定。

---

## 9. 总结

EEDI 强模型 harness 的本质是：

> 在长对话辅导场景中，先判断学生当前学习状态和 tutor 当前支持，再在约束边界内生成当前学生回合。它不是直接 role-play，而是状态推进式学生模拟。
