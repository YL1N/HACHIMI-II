# EEDI 弱模型 Harness 方法说明书（2026-05-12）

## 1. 方法定位

EEDI 弱模型 harness 面向的是**数学辅导对话中的 turn-level 学生模拟**。

它和 EEDI 强模型 harness 解决同一个任务：

> 给定当前 tutor-student 对话历史，预测学生下一轮会如何回应。

但它的方法分工不同。

EEDI 弱模型 harness 把系统拆成两部分：

- 强模型 compiler：负责理解当前教学情境；
- 弱模型 actor：负责生成当前学生回复。

所以它的核心不是“弱模型自己会不会做题”，而是：

> 强模型把当前教学条件编译成弱模型能执行的局部条件包，再让弱模型在这个包里生成学生回合。

---

## 2. 为什么这样设计

弱模型本身有一个特点：

- 它不太会完整解题；
- 但它可以遵循清楚的指令；
- 它的回答更容易短、更局部、更不成熟。

这看起来像缺点，但在学生模拟里也可能是优点。  
真实学生本来也不是稳定 solver。

问题是，弱模型如果没有支架，很容易：

- 乱答；
- 偏离 tutor 当前问题；
- 产生格式错误；
- 把困惑写成无意义文本。

所以 EEDI 弱模型 harness 的设计目标是：

> 不让弱模型自由发挥，而是用强模型把 tutor 当前支持翻译成清楚的学习条件。

---

## 3. 方法思想

这条方法的核心是：

> 不是控制答案，而是控制教学条件与学习吸收。

也就是说，系统不直接告诉弱模型：

- 这轮应该答对；
- 这轮应该答错；
- 这轮真实学生会说什么；
- 这轮标准错误句是什么。

系统只告诉它：

- 当前 tutor 在支持什么；
- 学生现在大概够得到哪里；
- 这轮允许什么类型的回应；
- 哪些回应越界。

这对应四个教育思想：

- **ZPD**：看学生在当前帮助下能到哪里；
- **Scaffolding**：支架打开局部空间，不替学生完成答案；
- **Dynamic Assessment**：学生对帮助的即时吸收本身就是评估对象；
- **ICAP**：学生回复还要体现参与方式，而不只是内容。

参考：

- Dynamic Assessment 综述：<https://pmc.ncbi.nlm.nih.gov/articles/PMC7375920/>
- ICAP framework：<https://icap.education.asu.edu/research>
- Instructional scaffolding 背景：<https://en.wikipedia.org/wiki/Instructional_scaffolding>

---

## 4. 方法流程

主链路是：

`VisibleContext -> StudentPrior -> TutorMove -> LearningAccessState -> SupportUptake -> TeachingSupportPacket -> WeakStudentTurn -> LearningStateUpdate`

### 4.1 VisibleContext

只保留当前 turn 前可见内容：

- 题目文本；
- subject；
- 历史 tutor/student turns；
- 最新 tutor turn；
- 上一个 student turn。

作用是防止未来信息进入生成。

### 4.2 StudentPrior

强模型先把学生当前画像压缩成弱模型能读懂的学生先验。

包括：

- 自我效能；
- 自我调节弱点；
- control-value；
- 参与倾向；
- 回答风格；
- 当前历史证据。

### 4.3 TutorMove

系统再把 tutor 当前回合翻译成教学动作。

它描述：

- tutor 的教学意图；
- 支持类型；
- 支持强度；
- 支持颗粒度；
- 当前局部数学对象；
- tutor 是否正在把责任交给学生。

### 4.4 LearningAccessState

这是弱模型链路的核心状态。

它判断：

- 当前局部对象学生是否够得着；
- tutor 支持是否足够；
- 学生是否准备尝试；
- 当前更像被动、主动、建构还是互动；
- 主要障碍是什么。

### 4.5 SupportUptake

这一步判断学生会如何吸收 tutor 当前支持。

例如：

- 只是注意到；
- 能局部照做；
- 能提出澄清；
- 能修正一点；
- 仍然卡住。

### 4.6 TeachingSupportPacket

系统把前面的状态编译成弱 actor 的输入包。

它规定：

- 当前焦点；
- 回应空间；
- 最大句数；
- 允许动作；
- 禁止动作；
- 是否允许数学 claim；
- 是否需要保留局部错误或困惑。

这个包不包含 gold 下一句，也不包含未来信息。

### 4.7 WeakStudentTurn

最后由弱模型生成当前学生回合。

它只负责当前 turn：

- 不生成未来；
- 不写完整成熟解法；
- 不扮演 tutor；
- 不越过条件包。

### 4.8 LearningStateUpdate

生成后，系统再回写一次学习状态。

这一步用来记录：

- 学生是否更主动；
- 是否吸收了当前支持；
- 是否仍有障碍；
- 后续状态可能如何延续。

---

## 5. 代码入口

主入口：

- `D:\Study\sii\MathStudent\eedi\run_eedi_weak_harness.py:1`

核心模块：

- `D:\Study\sii\MathStudent\eedi\src\weak_harness.py:1`
- `D:\Study\sii\MathStudent\eedi\src\weak_harness_v4.py:1`
- `D:\Study\sii\MathStudent\eedi\src\weak_harness_v5.py:1`
- `D:\Study\sii\MathStudent\eedi\src\weak_harness_v51.py:1`
- `D:\Study\sii\MathStudent\eedi\src\weak_harness_v52.py:1`
- `D:\Study\sii\MathStudent\eedi\src\weak_generation.py:1`

当前主要配置：

- `D:\Study\sii\MathStudent\eedi\configs\run_weak_v31_population_calibrated_full4334_20260511.json:1`

---

## 6. 运行方式

主命令形式：

`python eedi/run_eedi_weak_harness.py --config ...`

它需要两套模型：

- `compiler_llm_*`：强模型，负责状态判断和条件包编译；
- `actor_llm_*`：弱模型，负责当前学生回复生成。

当前 v31 全量版本使用：

- `architecture_version = v31`
- `ablation_mode = commitment_first`
- compiler：`qwen`
- actor：`qwen2.5-7b-instruct`

---

## 7. 输出和评测

典型输出包括：

- `predictions.jsonl`
- `official_eval_input.csv`
- `metrics.json`
- `progress.json`
- `task_retry_events.jsonl`

每条预测里会保留大量中间对象，例如：

- `visible_context`
- `student_prior`
- `tutor_move`
- `learning_access_state`
- `support_uptake`
- `teaching_support_packet`

评测主要看：

- `consistency`
- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

---

## 8. 方法边界

允许：

- 强模型做第三人称状态判断；
- 强模型编译 teaching support packet；
- 弱模型在 packet 内生成回复；
- 使用当前 turn 之前可见历史。

不允许：

- 使用真实下一句学生回复；
- 使用未来对话；
- 让弱模型直接看 gold；
- 直接规定“本轮必须答对/答错”；
- 用后处理强改输出。

---

## 9. 当前结果和状态

在 4334 task 全量对照中，weak harness 没有整体超过 strong harness。

它的特点是：

- `same_mechanism` 略高；
- 但 `consistency`、`same_knowledge`、`same_locus`、`error_realization` 都低于 strong；
- 说明它能在部分错误机制上贴近真实学生，但整体“该不该错”和“能否把错稳定外显”仍不够稳。

因此，当前项目决策是：

> EEDI weak harness 暂时冻结，后续主线回到 strong harness。

---

## 10. 总结

EEDI 弱模型 harness 的本质是：

> 强模型先把当前 tutor 支持和学生状态编译成局部学习条件，弱模型再在这个条件包内生成当前学生回复。它不是弱模型自由作答，而是支架化的弱 actor 学生模拟。
