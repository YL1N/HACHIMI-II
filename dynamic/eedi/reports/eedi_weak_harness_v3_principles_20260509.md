# EEDI 弱模型 Harness v3 方法原则（2026-05-09）

## 1. 这份文档要回答什么

这份文档只回答一个问题：

> 既然弱模型本来就不会做题，但指令遵循和表面生成能力还可以，那么 EEDI 里的 weak harness 到底应该怎么设计？

我们的结论是：

> weak harness 的职责不是压制弱模型能力，而是在不泄露答案、不直接控制结果的前提下，给弱模型提供完成当前学生回合所需的外部支持。

也就是：

> harness 不是刹车片，而是支架系统。

---

## 2. 为什么“弱模型不会做题”反而是一个优点

以前容易把弱模型理解成：

- 太弱；
- 太容易乱答；
- 所以需要 harness 把它管住。

但从学生模拟这个任务本身看，这个理解并不对。

真实学生在教学对话里，本来也不是：

- 心里已经有完整正确解法；
- 只是故意装不会。

很多真实学生的状态更像是：

- 数学上本来就没有完整掌握；
- 但能听懂老师现在在问什么；
- 能按当前帮助做出一个局部回应；
- 会表现出犹豫、试探、局部错误、求助、确认、修正。

弱模型天然接近的是这后一种。

所以它“不会做题”不是纯缺陷，而是一个可以利用的先验：

> 它本来就不具备完整求解能力，因此不需要我们额外去把它压弱；真正需要补的是它对当前回合任务的把握、状态边界和可达区判断。

---

## 3. 这件事的理论依据

## 3.1 Assessment Triangle

Assessment Triangle 的核心是把三件事分开：

- 学生当前具备什么能力；
- 当前任务要求学生表现什么；
- 观察到这个表现后如何解释学生状态。

放到这里，对应就是：

- 不能只看弱模型“会不会做题”；
- 要先判断这个学生在当前轮的状态；
- 再判断 tutor 这一轮到底在要什么；
- 最后才生成当前 student turn。

这意味着 weak harness 不能退化成：

- 历史对话 -> 直接让弱模型回一句。

而必须保留：

- 第三人称状态层；
- 当前轮任务层；
- 约束后的表面生成层。

参考：

- National Academies, *Knowing What Students Know*  
  https://nap.nationalacademies.org/read/10019/chapter/4

## 3.2 Evidence-Centered Design

ECD 的基本思想不是“让输出更像”，而是：

1. 先决定你要判断什么；
2. 再决定需要什么证据；
3. 再决定任务该怎样设计。

这里真正要判断的不是：

- 弱模型裸奔时能不能自己解出数学题。

而是：

> 在当前教师帮助和当前对话位置下，它能不能做出一个与学生状态一致的当前回合回应。

所以 harness 的重点不该是补完整解题能力，而该是补：

- 当前轮要做什么；
- 当前轮最多能做到什么；
- 当前轮允许怎样的数学承诺；
- 当前轮如果出错，错误应该落在哪个结构位置。

参考：

- ETS, *A Brief Introduction to Evidence-Centered Design*  
  https://www.ets.org/research/policy_research_reports/publications/report/2003/hsgs.html

## 3.3 Dynamic Assessment / ZPD

动态评估和 ZPD 关心的不是“独立完成”本身，而是：

> 学生在帮助下当前能到哪里。

这对 weak harness 很关键。

因为 weak harness 的作用本来就不是替学生做题，而是：

- 给足当前轮需要的外部支持；
- 看这个学生在支持下能不能往前迈一步；
- 如果还迈不过去，就自然地卡住。

因此 weak harness 要优先判定的是：

- 这一轮在当前 tutor 支持下，学生是独立可达、提示可达、只能部分可达，还是本轮不可达。

而不是先判：

- 这一轮到底应该答对还是答错。

参考：

- Dynamic assessment 综述  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC7375920/

---

## 4. v3 的核心定位

v3 的核心定位一句话说就是：

> 强模型负责第三人称状态编译，弱模型负责把这个状态实现成一句自然学生话。

注意，这里不是：

- 强模型先写好学生答案；
- 弱模型再复述。

也不是：

- 弱模型自己独立做完整数学推理；
- harness 只负责格式控制。

而是中间态：

- 强模型负责把“当前轮学生能到哪、该怎么回应、能不能形成明确数学判断”判清楚；
- 弱模型只在这个边界里完成当前回合表面生成。

---

## 5. 强模型和弱模型分别负责什么

## 5.1 强模型负责什么

强模型只负责第三人称判断，不负责替学生把这轮答案写好。

它负责：

1. 编译稳定学生状态；
2. 编译当前对话状态；
3. 判断 tutor 当前轮需求；
4. 判断这轮学生在当前帮助下的可达区；
5. 判断这轮是否自然允许出现明确数学 claim；
6. 如果会错，给出错误的结构窗口，而不是具体错误句子。

## 5.2 弱模型负责什么

弱模型只负责一件事：

> 把上面的状态和边界，变成一句自然学生话。

它的优势不是数学强，而是：

- 会按指令走；
- 会按当前上下文回应；
- 会说得简短；
- 天然不成熟；
- 天然不完整；
- 容易出现真实学生式的局部犹豫和局部不稳定。

这些东西恰恰是学生模拟里有价值的部分。

---

## 6. v3 里最重要的设计原则

## 6.1 不补完整解题能力，只补当前轮外部支持

weak harness 不是为了让弱模型变成强数学模型。

它应该补的是：

- 当前轮任务定义；
- 当前轮状态摘要；
- 当前轮可达边界；
- 当前轮输出协议；
- 当前轮允许的数学承诺强度。

它不应该补的是：

- 完整标准解法；
- 当前轮具体正确答案；
- 当前轮具体错误答案；
- 未来对话信息；
- 官方评测标签。

## 6.2 先保证回合方向对，再保证错误类型对

从指标上说，优先级应该是：

1. `consistency`
2. `same_knowledge`
3. `same_locus`
4. `same_mechanism`
5. `error_realization`

原因很简单：

- 如果这轮整体方向都不对，那么后面的错误结构对齐就没有意义；
- `error_realization` 也不能盲目拉高，否则就会出现“过度把错误做实”的问题。

## 6.3 harness 是支架，不是作弊通道

支架允许做的事是：

- 帮弱模型理解当前 tutor 在要什么；
- 帮弱模型定位当前自己处在哪个局部状态；
- 帮弱模型知道这轮最多能说多成熟的话；
- 帮弱模型知道是否自然有机会形成具体数学判断。

支架不允许做的事是：

- 把答案直接告诉它；
- 把具体错误直接告诉它；
- 写死“这一轮必须答对/答错”；
- 把真实未来信息带进生成链。

---

## 7. v3 的对象层

## 7.1 `StudentLongState`

表示学生的稳定特征。

包括：

- 数学基础大概在哪；
- 常见障碍；
- 容易怎么求助；
- 容易试答还是容易回避；
- 容易过早承诺还是容易犹豫。

它回答的问题是：

> 这个学生平时大体是什么样的人。

## 7.2 `DialogueContextState`

表示到当前轮为止，局部对话状态是什么。

包括：

- tutor 已经说到哪；
- 哪些中间关系已经公开；
- 学生上一轮是卡住、半懂、局部会了，还是正在修正。

它回答的问题是：

> 现在到底对话推进到了哪里。

## 7.3 `TutorTurnDemand`

表示 tutor 当前这一轮到底在要什么。

例如：

- 要确认；
- 要选项；
- 要局部尝试；
- 要解释；
- 要修正前错；
- 要求助澄清。

它回答的问题是：

> 这一轮 student turn 的功能任务是什么。

## 7.4 `TurnReachabilityState`

表示这轮在当前支持下能到哪。

建议四档：

- `independent_reachable`
- `hint_reachable`
- `partially_reachable`
- `not_reachable_this_turn`

它回答的问题是：

> 这一轮学生在当前帮助下，最多能往前迈到哪一步。

## 7.5 `MathClaimAffordanceState`

表示这一轮是否自然允许形成明确数学 claim。

建议四档：

- `no_claim`
- `tentative_claim`
- `local_claim`
- `committed_claim`

它回答的问题是：

> 这轮该不该只表达困惑，还是已经自然到了可以说出一个数学判断的地步。

## 7.6 `ErrorRealizationWindow`

表示如果这轮会错，错误允许以什么结构出现。

它只描述：

- 是否允许 codable math error；
- 如果允许，错误更像哪类 `knowledge_type`；
- 更像卡在哪个 `error_locus`；
- 更像哪种 `error_mechanism`；
- 错误表达强度是含糊、局部明确，还是明确承诺。

它不描述：

- 具体错误句子；
- 具体错误答案。

## 7.7 `ConstraintBundle`

这是弱模型真正看到的执行边界。

至少包括：

- 当前 `response_act`
- 当前 `reachability_band`
- 当前 `claim_affordance`
- 当前 `allowed_commitment_level`
- 当前 `max_sentences`
- 当前 `math_content_budget`
- 当前 `error_window`
- 当前 `forbidden_moves`

---

## 8. v3 的主流程

## Step 1：编译稳定学生状态

输入：

- 历史对话；
- 题目背景。

输出：

- `StudentLongState`

目的：

- 不是预测这一轮答案；
- 而是总结这个学生通常的交互边界和学习边界。

## Step 2：编译当前对话局部状态

输入：

- 当前轮之前全部可见历史。

输出：

- `DialogueContextState`

目的：

- 判清楚这轮不是从零开始，而是延续前文。

## Step 3：识别 tutor 当前轮需求

输入：

- 当前 tutor turn；
- 当前局部上下文。

输出：

- `TutorTurnDemand`

目的：

- 判断当前 student turn 的功能任务是什么。

## Step 4：判定当前轮可达区

输入：

- `StudentLongState`
- `DialogueContextState`
- `TutorTurnDemand`

输出：

- `TurnReachabilityState`

目的：

- 优先为 `consistency` 服务。

## Step 5：判定当前轮是否自然允许形成数学 claim

输入：

- 前面三个状态。

输出：

- `MathClaimAffordanceState`

目的：

- 决定这一轮该不该只说“我不懂”；
- 还是可以说“是不是乘”；
- 还是可以做一个明确局部判断。

## Step 6：生成错误窗口

输入：

- `TurnReachabilityState`
- `MathClaimAffordanceState`
- 历史已经暴露的障碍

输出：

- `ErrorRealizationWindow`

目的：

- 控制三个 `same` 指标；
- 避免硬控一句具体错误答案。

## Step 7：编译约束包

输入：

- 前面所有状态。

输出：

- `ConstraintBundle`

目的：

- 把第三人称状态翻译成弱模型可执行边界。

## Step 8：弱模型生成当前轮 student turn

输入：

- 当前可见历史；
- 当前 tutor turn；
- `ConstraintBundle`

输出：

- 当前 student turn

目的：

- 只生成这一轮，不生成未来；
- 只做表面实现，不补完整解法；
- 保留自然的不成熟与局部不稳定。

## Step 9：后验评估

输入：

- 生成出的 student turn

输出：

- detached eval / theory eval 的分析结果

目的：

- 只评估，不反向改写生成结果。

---

## 9. 哪些东西可以进弱模型 prompt

可以进：

- 当前可见历史；
- 当前 tutor 话语；
- 当前轮 `response_act`；
- 当前轮 `reachability_band`；
- 当前轮 `claim_affordance`；
- 当前轮 `allowed_commitment_level`；
- 当前轮 `max_sentences`；
- 当前轮 `forbidden_moves`；
- 简短学生风格摘要。

这些东西本质上都是：

- 当前时点本来就可用的信息；
- 或者对这些信息的第三人称结构化解释。

---

## 10. 哪些东西绝不能进弱模型 prompt

绝不能进：

- 真实下一轮学生回复；
- 当前轮之后的未来对话；
- 官方 correctness 标签；
- 官方错误标签；
- detached eval 结果；
- 强模型提前写好的具体答案；
- 强模型提前写好的具体错误句；
- “这一轮应该答对”；
- “这一轮应该答错”；
- “尽量更像真实学生”这类结果导向指令。

原因是：

> 这些东西一旦进入生成链，weak harness 就会从“支架系统”退化成“结果控制系统”。

---

## 11. 这套设计对当前目标意味着什么

当前目标是：

- `consistency ≥ 0.70`
- `same_knowledge ≥ 0.55`
- `same_locus ≥ 0.55`
- `same_mechanism ≥ 0.55`

那就说明 v3 的优化顺序必须是：

## 第一优先：把当前轮整体方向判稳

重点对象：

- `TutorTurnDemand`
- `TurnReachabilityState`
- `ConstraintBundle.response_act`

这主要服务：

- `consistency`

## 第二优先：把错误结构窗口判稳

重点对象：

- `ErrorRealizationWindow.knowledge_type`
- `ErrorRealizationWindow.error_locus`
- `ErrorRealizationWindow.error_mechanism`

这主要服务：

- `same_knowledge`
- `same_locus`
- `same_mechanism`

## 第三优先：抑制过度错误实现

重点对象：

- `MathClaimAffordanceState`

这主要服务：

- 防止 `error_realization` 过高同时拖垮 `consistency`

---

## 12. v3 不是在做什么

v3 不是：

- 把弱模型包装成一个会做题的强模型；
- 用 prompt 把正确答案悄悄喂进去；
- 用强模型写好的错误脚本让弱模型照演；
- 为了 detached eval 指标去反向控制当前轮输出。

v3 真正在做的是：

> 利用弱模型“不会完整做题、但能按上下文完成局部回应”的天然特征，再用 harness 提供当前轮所需的外部支持，让它更自然地表现出学生式回应。

---

## 13. 一句话总结

弱模型 harness 的核心不该是：

> 如何压住弱模型别太聪明。

而该是：

> 如何在不作弊的前提下，把当前轮所需的状态、任务、可达区和回应边界整理清楚，再让弱模型自然地把这一轮学生话说出来。

也就是：

> 弱模型本来不会做题，这不是要被消灭的缺点；  
> harness 的作用是补它完成当前学生回合所需的外部支持，而不是替它把题做完。
