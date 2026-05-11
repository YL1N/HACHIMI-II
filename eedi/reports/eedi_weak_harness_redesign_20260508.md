# EEDI 弱模型 Harness 设计稿（2026-05-08）

## 1. 这份设计稿解决什么问题

现有 `eedi/` 主链是为强模型 student actor 设计的。

它的核心是：

- 先做第三人称状态判断；
- 再做状态转移预测；
- 再把这些状态编译成约束；
- 最后让 actor 在约束内生成当前学生回合。

这条链对强模型是合理的，因为强模型本身太会做题，必须防止它直接越过学生边界。

但如果 actor 本身就是一个较弱模型，问题就变了。

这时真正该利用的，不是“继续压它”，而是：

> 把弱模型当成一个本来就不会完整做题、正在被老师引导的学生本体。

所以新的弱模型 harness 不再把重点放在“能力压制”上，而放在：

> 这轮教师支持，究竟让这个学生**现在**能做出什么样的局部回应。

也就是从“限制 actor 太强”，改成“编译教学条件与可见学习吸收”。

---

## 2. 为什么不能直接复用现有强模型链的后半段

现有强模型链后半段最核心的是：

- `InteractionState`
- `StateTransitionPrediction`
- `ErrorBlueprint`
- `ConstraintBundle`

这条链默认在做一件事：

> 预测 actor 应该维持什么成熟度、什么错误连续性、什么表达上限。

这对强模型很重要，因为它天然会：

- 抢答；
- 讲完整解法；
- 比学生更早“学会”；
- 用过度成熟的表达把学生状态冲掉。

但弱模型天生就没有这么强的独立解题能力。

如果继续把弱模型也主要当成“需要被压制的 solver”，会出现两个问题：

1. 设计中心错位  
   我们会把大量精力放在“防它太强”，而不是“理解这轮教师支持真正打开了什么”。

2. consistency 可能被上限机制卡住  
   弱模型本来就更容易维持“不完全理解、局部尝试、半吸收”这些真实学习状态。
   如果再用一套强压制约束把它写死，反而容易把自然的学生不稳定性压平。

所以弱版本必须平行设计，不能只是把强版本 prompt 改弱一点。

---

## 3. 理论依据

这版弱模型 harness 只站在四类理论上，不靠工程补丁。

### 3.1 ZPD：当前能独立做、在支持下能做、这轮还做不到

Vygotsky 的近侧发展区强调：

- 学生独立能做什么；
- 在成人或更有能力者支持下能做什么；
- 当前支持仍然够不到什么。

放到 EEDI 里，这意味着我们每一轮真正要判断的不是：

> 这句学生回复最后应该像不像 gold。

而是：

> 这轮 tutor 说完以后，学生现在对这个局部数学对象，到底已经：
>
> - 自己会了，
> - 在当前支持下够得着，
> - 还是这一轮仍然够不着。

所以弱版本里最核心的新状态之一就是 `LearningAccessState`。

### 3.2 Scaffolding：帮助是开局部通道，不是替学生做完

Wood、Bruner、Ross 提出的 scaffolding 不是“代做”，而是：

- 把学生的注意力拉到关键局部；
- 降低无关负担；
- 只在学生当前够不到的地方给支持；
- 学生一旦能自己做，就逐步把支持退掉。

这直接决定了我们的弱版本不能做成：

- 直接给 actor 标准答案；
- 直接规定 actor 这题就该对/该错；
- 直接写一个 gold-like 回复模板让它照着说。

我们应该编译的是：

- tutor 当前支持作用在什么局部对象上；
- 它是提示、澄清、追问、纠错还是局部引导；
- 这种支持现在最多打开了什么回应空间。

所以弱版本里第二个核心对象是 `TeachingSupportPacket`。

### 3.3 Dynamic Assessment：看“在帮助下的表现”，不是只看裸能力

dynamic assessment 的关键点是：

> assessment 和 teaching 不是完全分开的。

真正有信息量的，不只是学生独立会不会，而是：

> 给出当下支持以后，学生立刻能吸收到什么。

这和 EEDI 的 tutor-student 对话非常贴。

因为这里本来就是教师干预后的学生反应，不是静态考试。

因此弱版本里一定要显式建模：

- tutor 这轮支持的类型；
- 学生对这轮支持的即时吸收深度；
- 这种吸收在下一句里会表现成哪种回应空间。

这就是 `SupportUptake` 的理论来源。

### 3.4 ICAP：下一句学生回复不是只看内容，还要看参与方式

Chi 和 Wylie 的 ICAP 把可见参与分成：

- Passive
- Active
- Constructive
- Interactive

这很适合约束 student turn 的“外显行为形状”。

因为两句都可能是错的，但它们很不一样：

- 被动附和；
- 主动跟着做一个局部动作；
- 生成自己的局部解释；
- 和 tutor 来回协商。

弱版本里我们不再主要用“成熟度上限”来压回复，
而是用：

> 当前这轮更像哪一种可见参与方式。

这样更符合教学交互场景。

---

## 4. 新弱模型 harness 的核心思想

一句话：

> 不是控答案，而是控教学条件与学习吸收。

再具体一点：

> harness 负责编译“这轮老师的支持现在为学生打开了什么局部回应空间”，
> 弱模型负责在这个空间里生成当前 student turn。

注意，这里仍然保留第三人称状态层。

不是直接：

`历史 -> 弱模型 student reply`

而是：

`历史 -> 第三人称教学/学习状态 -> 编译支持包 -> 弱模型生成当前回复`

所以它没有违背项目里最重要的硬约束。

---

## 5. 新 pipeline

### Step 1：读取当前 turn 样本

输入还是现有 `TurnPredictionTask`：

- 题目文本
- 历史对话
- 当前要预测的 student turn 位置

### Step 2：构建 `VisibleContext`

它只保留当前时点可见信息：

- 到目前为止的历史回合
- 最新 tutor 话语
- 上一轮 student 话语
- 题目文本
- 学科标签

作用：

> 明确 generation path 能看到什么，不能看到什么。

### Step 3：构建 `StudentPrior`

这一步先复用现有强编译器做好的 `StudentContextProfile`，再把它压成更适合弱 actor 的学生先验卡。

保留的是：

- 自我效能描述
- 自我调节薄弱点
- control-value 描述
- ICAP 倾向
- 回答风格倾向

作用：

> 说明这个学生在一般意义上是怎样的学习者。

### Step 4：构建 `TutorMove`

这一步复用现有 `TutorTurnProfile`，再映射成弱版本使用的 tutor move 卡。

保留的是：

- 这轮教学意图
- 支持类型
- 支持强度
- 支持颗粒度
- 支持是否紧贴学生状态
- 责任是 tutor 扛、共享，还是往 student 回推
- 当前正盯着哪个局部数学对象

作用：

> 说明老师这轮到底在教什么、扶什么、扶到哪里。

### Step 5：解析 `LearningAccessState`

这是弱版本最核心的新增第三人称状态。

它回答：

- 这个局部对象，学生是已经能做，还是当前支持下够得着，还是这轮还够不着；
- 学生有没有读对 tutor 当前意图；
- 当前是 tutor-regulated、shared-regulation 还是 self-regulation；
- 当前最可能的外显参与形态是什么；
- 主要剩余障碍是什么。

作用：

> 把“老师说了什么”翻译成“学生现在能接到什么程度”。

### Step 6：预测 `SupportUptake`

这一步不预测 gold answer，也不预测固定错误。

它只预测：

- 学生对这轮支持会不会吸收；
- 吸收到什么深度；
- 吸收会落在什么局部焦点；
- 所以下一句更可能是什么回应空间：
  - 简短回应
  - 澄清提问
  - 局部尝试
  - 修正旧想法
  - 局部解释

作用：

> 把“教学支持”翻译成“下一句学生最可能出现的回应类型空间”。

### Step 7：编译 `TeachingSupportPacket`

这是给弱模型 actor 的直接输入卡。

它不含未来标签，不含标准答案，不含“你该故意错成什么样”。

它只包含：

- 当前局部焦点
- 当前可达区
- 允许的回应空间
- 目标参与方式
- 最长几句
- 允许做什么
- 不允许做什么
- 这轮支持应该如何被使用

作用：

> 把第三人称状态层翻译成一个可执行的本轮教学条件包。

### Step 8：弱模型生成当前 `student turn`

这一步由弱模型 actor 执行。

它读取：

- `VisibleContext`
- `StudentPrior`
- `TutorMove`
- `LearningAccessState`
- `SupportUptake`
- `TeachingSupportPacket`

然后只生成：

- 当前这一轮学生要说的话

注意：

- 不要求它完整会做题；
- 不要求它假装成熟；
- 也不要求它按某个预设错误模板演戏。

它只需要在这轮支持打开的空间里，给出一个合理的学生当下回应。

### Step 9：协议校验

这一层只做轻量协议检查：

- 是否为空
- 是否超过句数上限

如果越界，允许一次显式重试。
如果还越界，直接失败，不做静默修补。

### Step 10：更新 `LearningStateUpdate`

生成后再做一次第三人称回写：

- 这句回复体现出什么 ICAP 参与水平；
- 实际吸收深度是多少；
- 下一轮 readiness 变成什么；
- 主要障碍还剩什么。

作用：

> 给后续 full dialogue 链路留下真正能延续的学习状态。

### Step 11：落盘

保留：

- 各阶段对象
- 最终 student turn
- 协议校验结果
- post-turn 学习状态更新

作用：

> 保证可审计、可续跑、可比较。

### Step 12：离线评测

这一层与 generation path 隔离。

后续可以接：

- 官方 EEDI turn-level eval
- 自定义 consistency 分析
- uptake / engagement / response-space 分布分析

---

## 6. 这版弱 harness 与现有强 harness 的关系

两者不是替代关系，而是并行关系。

### 强版本更像

- 强 student actor
- 需要防止 actor 太强
- 重点是能力边界、错误连续性、成熟度控制

### 弱版本更像

- 弱 student actor
- 本身就不会完整做题
- 重点是教学支持如何转化成当下可见学习行为

所以仓库层面应该保持：

- 现有 `run_eedi_experiments.py` 不动
- 新增独立入口 `run_eedi_weak_harness.py`
- 两条链平行存在

---

## 7. 非作弊边界

这版弱模型 harness 明确不做以下事情：

1. 不把真实未来 student turn 带入生成链  
2. 不把官方 correctness / acts / kcs / persona 带入生成链  
3. 不告诉弱模型“这句应该答对/答错”  
4. 不告诉弱模型“你应该沿某个错误标签去演”  
5. 不在生成后按评测指标去改写输出  

也就是说：

> 我们编译的是支持条件，不是结果标签。

---

## 8. 第一版最小实现范围

这次先做最小可测版本：

1. 保留现有 `StudentContextProfile`
2. 保留现有 `TutorTurnProfile`
3. 新增：
   - `VisibleContext`
   - `StudentPrior`
   - `TutorMove`
   - `LearningAccessState`
   - `SupportUptake`
   - `TeachingSupportPacket`
   - `LearningStateUpdate`
4. 新增独立运行入口：
   - `eedi/run_eedi_weak_harness.py`
5. 新增弱 actor 生成模块：
   - `eedi/src/weak_generation.py`
6. 新增 smoke test：
   - `eedi/tests_smoke_weak_harness.py`

这版先保证：

- 理论结构站得住；
- 代码能跑；
- 中间状态能落盘；
- 可以小样本测试。

后续再继续加：

- detached eval 对接
- full dialogue rollout
- 更正式的 uptake / engagement 分析报表

---

## 9. 一句话总结

这版 EEDI 弱模型 harness 的核心不是：

> 再想办法把弱模型压成更像学生。

而是：

> 把弱模型本来就不会完整做题这件事当成资产，再用第三人称教学状态层去编译“这轮老师的支持究竟打开了什么局部回应空间”。

也就是：

> 强版本主要防 actor 太强；  
> 弱版本主要描述支持怎么生效。

---

## 10. 理论参考

1. Vygotsky, L. S. — Zone of Proximal Development / `Mind in Society`
2. Wood, Bruner, Ross (1976) — `The Role of Tutoring in Problem Solving`
3. Poehner / Lantolf — Dynamic Assessment
4. Chi & Wylie (2014) — `The ICAP Framework: Linking Cognitive Engagement to Active Learning Outcomes`
