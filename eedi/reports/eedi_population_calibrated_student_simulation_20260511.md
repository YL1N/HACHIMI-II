# EEDI 群体校准型学生模拟设计稿（2026-05-11）

## 1. 这份文档回答什么问题

这份文档回答的是：

> 我们能不能在不作弊、不泄露未来信息的前提下，用少量真实学生数据做 few-shot / exemplar 校准，让学生模拟更贴近这个学生群体真实的错误模式？

本文的结论是：

> 可以，而且这不应该被理解成一个 prompt 小技巧，而应该被理解成一个正式的方法层：**群体校准层（population calibration layer）**。

它的作用不是直接告诉模型“这一轮该怎么答”，而是：

- 用少量真实学生样本校准这个学生群体的常见错误原型；
- 让第三人称状态判断更懂“这个群体通常怎么错”；
- 再让生成层在这个边界内自然地产生当前轮学生回复。

一句话：

> 不是“拿几个例子喂给模型”，而是“用少量群体证据校准学生模拟器的误差先验”。

---

## 2. 为什么这件事理论上站得住

## 2.1 Assessment Triangle：要分清学生模型、观察证据、解释过程

Assessment Triangle 的核心不是“看模型像不像学生”，而是把三件事分开：

- 学生当前具有什么知识与能力；
- 当前任务能观察到什么证据；
- 如何从证据推回对学生状态的解释。

放到这里，few-shot / exemplar 的合理位置不是“直接控制下一句回答”，而是：

- 补充这个数据集学生群体常见的错误证据原型；
- 帮助第三人称判断更稳定地区分：
  - 这类学生常见卡在哪类知识上；
  - 常见错在解题链的哪个环节；
  - 常见以什么机制出错；
  - 常见怎样把错误外显成一句话。

这说明 exemplar 应该服务于**推断层**，而不是偷渡到**答案层**。

参考：

- National Research Council, *Knowing What Students Know*  
  <https://www.nationalacademies.org/read/10019/chapter/4>

## 2.2 Evidence-Centered Design：先定义要推断什么，再决定需要什么证据

ECD 的核心是：

1. 先定义要做什么推断；
2. 再定义哪些证据支持这个推断；
3. 再设计任务与表示方式。

对我们来说，要推断的不是：

- 这个模型裸奔时会不会自己做对题；

而是：

> 在当前 tutor 支持、当前对话位置、当前学生群体背景下，学生这一轮最可能表现出怎样的局部理解、局部错误和局部回应。

因此 exemplar 的合理用途是提供“**群体层面的证据原型**”，例如：

- 这种 tutor move 下，这个群体学生更常给出局部猜测还是局部澄清；
- 这类题目对象上，这个群体学生更常出现哪类 locus / mechanism；
- 哪些错误更容易只是模糊困惑，哪些更容易被说成一个可编码数学错误。

参考：

- Mislevy, Almond, Lukas, *A Brief Introduction to Evidence-Centered Design*  
  <https://cresst.org/wp-content/uploads/R632.pdf>

## 2.3 Dynamic Assessment / ZPD：看的是“在帮助下能到哪里”

动态评估和 ZPD 关注的不是学生“独立完美作答”，而是：

> 在当前帮助下，这个学生现在最多能推进到哪里。

这和我们现在做 EEDI turn-level student simulation 是直接对齐的。

因此，校准层不该回答：

- 这一轮应该答对还是答错；

而该回答：

- 这个群体在类似支持下，常见的可达边界是什么；
- 常见的半理解、半卡住、半猜到位于哪里；
- 常见错误是停留在困惑层，还是会外显成一句具体错误 claim。

参考：

- Dynamic Assessment review  
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC7375920/>

## 2.4 Scaffolding：支持应该降低当前步的认知负担，而不是替学生写答案

Scaffolding 的意思不是 tutor 或 harness 替学生把题做掉，而是：

- 招募注意；
- 缩小当前局部任务；
- 保持学生在当前步上可工作；
- 随着理解增长逐步撤掉支架。

这意味着群体校准层应该帮助我们判断：

- 这个群体学生在这种支架下通常会如何“局部推进”；
- 哪些错误会在支架下持续，哪些错误会被局部扰动；

而不应该直接输出：

- “本轮正确答案是什么”
- “本轮具体错误句子是什么”

参考：

- Wood, Bruner, Ross, *The Role of Tutoring in Problem Solving*  
  <https://doi.org/10.1111/j.1469-7610.1976.tb00381.x>

## 2.5 Productive Failure：允许学生在有限支持下暴露不成熟理解

如果学生模拟的目标是真实，而不是“看起来不那么强”，那么允许局部错误、局部不成熟、局部猜测，本身就是合理的。

Productive Failure 这条理论给我们的启发是：

- 不要过早把学生修正成成熟答案；
- 允许学生在适度支持下暴露不完整但有信息量的局部理解；
- 这种外显对后续教学与评测都有价值。

所以群体校准层不是用来“压模型”，而是用来帮助模型更稳定地落在这个群体真实的局部不成熟区间里。

参考：

- Sinha & Kapur, *Productive Failure in Preparatory Problem Solving*  
  <https://journals.sagepub.com/doi/pdf/10.3102/00346543211019105>

---

## 3. 方法定位：这不是作弊，也不是传统意义上的 few-shot prompt hack

我们把这个方法正式命名为：

> **Population-Calibrated Student Simulation**  
> 中文：**群体校准型学生模拟**

它和普通 few-shot prompt 的区别在于：

- 普通 few-shot 常常直接给模型“类似输入 -> 类似输出”；
- 群体校准型学生模拟给的是“类似群体在类似局部情境中常见的错误原型与行为原型”。

因此它不是：

- 直接教模型这一轮怎么答；
- 直接给模型当前题目的正确/错误答案；
- 用 prompt 偷偷编码 test 偏好。

它是：

- 用少量校准样本学习群体先验；
- 在生成前先更新第三人称状态判断；
- 再让模型只在当前边界内回答。

---

## 4. 适用场景：不是纯零数据，而是低资源冷启动

我们不再把场景理解成“完全零数据”。

更准确地说，应该分成两种 setting：

### 4.1 Zero-shot cold start

- 完全没有本地真实学生数据；
- 只能依赖通用理论和大模型先验；
- 这是当前 strong harness / weak harness 的基本形态。

### 4.2 Low-resource calibrated cold start

- 有很少量真实学生数据；
- 例如 50–100 个真实学生的少量对话；
- 不足以训练一个新模型；
- 但足以建立一个群体误差先验库。

本文主张：

> 真正有应用价值的路线，应该是从 zero-shot cold start 平滑升级到 low-resource calibrated cold start。

也就是说：

- 不要求大规模训练；
- 只要求极少量启动数据；
- 就能让模拟更贴近特定学生群体。

---

## 5. 硬边界：什么可以做，什么绝对不能做

## 5.1 允许做的事

- 用独立校准集里的少量真实学生样本构建 exemplar bank；
- 基于当前轮之前可见的信息检索相似 exemplar；
- 用 exemplar 帮助第三人称层判断当前学生群体更常见的错误模式；
- 用 exemplar 帮助 surface 层对齐这群学生常见的表达风格。

## 5.2 不允许做的事

- 用当前 test 样本的未来学生回复做 exemplar；
- 用当前样本之后的任何对话做校准；
- 用官方评测标签直接当生成输入；
- 按 `question_id` 写专门模板；
- 按目标指标反向调输出；
- 让 exemplar 直接告诉模型“这一轮应该答 A / 应该错在 B”。

## 5.3 最重要的一条

> exemplar 只能提供**群体先验**，不能提供**当前样本真值**。

---

## 6. 群体校准层应该放在哪里

我们仍然保留当前项目的硬约束：

> 必须先做第三人称状态判断，再生成当前 student turn。

所以新的主链不是：

`历史 -> few-shot -> 直接 student turn`

而应该是：

`可见历史 -> 群体校准层 -> 第三人称状态判断 -> 约束编译 -> 当前 student turn`

更完整地写：

`Visible History -> Population Calibration Layer -> StudentModel / DialogueContext / TutorTurnProfile / StudentTurnState -> ConstraintBundle -> StudentTurn`

因此，群体校准层不是替代第三人称层，而是增强第三人称层。

---

## 7. 群体校准层的两种形式

## 7.1 结构校准（structural calibration）

这是主方法，优先级最高。

它服务于“第三人称判断”。

输入：

- 当前轮之前可见历史；
- 当前 tutor turn；
- 当前题目对象与 subject；
- 当前学生的已有画像或局部状态。

输出：

- 这类群体在类似局部情境下常见的：
  - knowledge error type 倾向；
  - locus 倾向；
  - mechanism 倾向；
  - error realization 强度；
  - 响应空间偏好。

它不输出：

- 本轮具体答案；
- 本轮具体错误句子。

一句话：

> 结构校准负责告诉系统“这群学生通常怎么错”，而不是“这一轮具体说哪句话”。

## 7.2 表面校准（surface calibration）

这是次要层，用于语言外观对齐。

它服务于“表面实现”。

它可以校准：

- 句子长度；
- 承诺强度；
- 常见犹豫方式；
- 常见求助方式；
- 常见直接猜测方式；
- 常见自我修正方式。

它不能校准：

- 具体数学内容真值；
- 具体错误方向。

一句话：

> 表面校准只管“怎么说”，不管“说什么数学内容”。

---

## 8. exemplar bank 应该长什么样

一个 exemplar 不应该只是“输入-输出对”。

它应该是一个结构化案例：

- 当前时点前可见历史摘要；
- 当前 tutor move 类型；
- 当前 tutor 所问的局部对象；
- 真实学生下一句；
- 离线标注或离线解释：
  - same_knowledge 对应的知识错误类型；
  - same_locus 对应的位置；
  - same_mechanism 对应的机制；
  - 是否形成显式错误 realization；
- 表面风格特征：
  - 是否直接猜；
  - 是否请求澄清；
  - 是否局部自我修正；
  - 是否强承诺或弱承诺。

也就是说，exemplar bank 不是一个回答库，而是一个：

> **群体局部行为案例库**

---

## 9. 检索应该依据什么，不能依据什么

## 9.1 可以用的检索键

- subject / topic
- tutor move type
- elicited object type
- 当前局部任务类型
- 学生当前承诺状态
- 学生当前是否在求助 / 澄清 / 猜测 / 修正
- 当前 dialogue stage

## 9.2 最好不要直接用的键

- 精确 `question_id`
- 精确 `intervention_id`
- 当前题目唯一模板文本

原因很简单：

- 太容易变成数据集内模板投机；
- 太容易带来泄漏；
- 太容易让方法退化成“按题背答案”。

所以检索应以**局部结构相似**为主，而不是以**题目身份相似**为主。

---

## 10. 强版和弱版该怎么接

## 10.1 强模型 harness

对 strong harness，群体校准层最适合放在：

- `StudentModel`
- `DialogueContextState`
- `TutorTurnProfile`
- `StudentTurnState`
- `ErrorRealization` 判定前

原因：

- 强模型本来就负责第三人称状态编译；
- 它的短板更可能是“不够懂这个数据集学生群体的特定错法”；
- 所以结构校准能直接补这一层。

预期收益：

- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

尤其 strong 版本当前 `error_realization` 相对短板，理论上最该先补这一项。

## 10.2 v31 弱模型 harness

对 weak harness，不建议把大量 exemplar 直接塞给弱 actor。

更合理的接法是：

- 先让强模型在编译阶段读取 exemplars；
- 把群体先验吸收到第三人称判断和约束包里；
- 再把压缩后的边界交给弱模型 actor。

原因：

- 弱模型 few-shot 不应该退化成“把几个真实学生例子直接贴给 actor 抄”；
- 弱模型当前最有价值的是指令遵循与受限实现，不是自己做群体归纳；
- 因此 few-shot 应该先进入 `StudentContextProfile -> StudentPrior -> 第三人称状态判断 -> 约束编译`；
- actor 侧只看到压缩后的群体先验摘要与 caution，而不看到原始 exemplar 文本。

这次代码落地也按这个原则实现：

- 强版：`population_calibration_summary` 直接进入状态推断链；
- 弱版：`population_calibration_summary` 进入 `build_student_context_profile(...)`、`build_student_prior(...)`，并继续进入弱版编译链与分析用 `strong_error_blueprint`；
- 没有把 exemplar 原文直接塞进弱 actor prompt。

- 7B actor 的长上下文 few-shot 容易被噪声带偏；
- 弱模型更适合“在明确边界内回答”，不适合“自己读很多案例再抽象”；
- 这也更符合当前 weak harness 的角色分工。

一句话：

> 群体校准优先增强编译器，不要优先喂给演员。

---

## 11. 推荐 pipeline

这里给出正式 pipeline。

### Step 1：划出独立校准集

- 从真实学生对话中拿一小部分作 calibration split；
- 不与正式 test 样本重叠；
- 不让 test 未来信息泄漏回去。

推荐量级：

- 50–100 个真实学生；
- 每个学生若干 turn；
- 总量足以覆盖几类常见错误原型即可。

### Step 2：离线构建 exemplar bank

对 calibration split 中的案例做结构化处理：

- tutor move 类型
- local object 类型
- response family
- knowledge / locus / mechanism
- 是否 error realization
- 表面风格特征

这一层可以使用离线人工标注、规则、或强模型离线解释，但不能把 test 真值带入在线生成。

### Step 3：在线检索群体相似案例

对当前样本，用当前时点可见信息检索 top-k exemplars。

检索目标不是找“最像当前题”的例子，而是找：

- 在当前局部教学情境下，
- 这个群体常见的局部错误和局部响应方式。

### Step 4：生成 population calibration summary

把 top-k exemplars 压缩成一个群体先验摘要，例如：

- 这类情境下，这个群体更常见哪类 knowledge error；
- 更常见卡在 locus 的哪个位置；
- 更常见以何种 mechanism 出错；
- 更常以模糊困惑出现，还是更常外显成明确错误 claim；
- 更常澄清、猜测、直接答，还是局部修正。

### Step 5：用群体先验增强第三人称状态判断

把 `population calibration summary` 作为输入之一，增强：

- `StudentModel`
- `DialogueContextState`
- `TutorTurnProfile`
- `StudentTurnState`
- `ConstraintBundle`

但这里必须强调：

- summary 只能影响先验判断；
- 不能直接决定本轮具体答案内容。

### Step 6：生成当前 student turn

在增强后的约束包下生成当前轮学生回复。

如果是 weak harness：

- 由强模型读 exemplars；
- 由弱模型只读编译后的边界。

### Step 7：离线评测

还是用现有统一指标：

- `consistency`
- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

---

## 12. 这件事最可能改善哪些指标

如果方法做对了，理论上最可能先提升的是：

- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

原因：

- 群体校准层本质上就是在校准“这群学生惯常怎样犯错”。

`consistency` 也可能提升，但不保证自动提升。

因为 `consistency` 取决于两件事：

1. 有没有更准确地落在该对/该错的整体方向上；
2. 有没有因为 exemplar 过强而被带成“过度犯错”。

因此，群体校准层对 `consistency` 的收益要靠实验验证，不能先验保证。

---

## 13. 三个最危险的漏洞

## 13.1 漏洞一：答案泄漏

如果 exemplar 检索太贴题、太贴 question identity，就可能退化成：

- 其实是在给当前题找近似答案。

修复方式：

- 检索以局部结构为主，不以题号为主；
- exemplar 必须来自独立校准集；
- 不允许读取当前 test 样本未来信息。

## 13.2 漏洞二：只学到表面风格，没学到错误结构

如果 few-shot 只让模型学会：

- “这类学生喜欢说 maybe”
- “这类学生爱说 I think”

那只会改善风格，不会改善结构。

修复方式：

- exemplar 必须有结构层字段；
- 检索与压缩必须优先围绕 knowledge / locus / mechanism；
- 表面层只能是第二层。

## 13.3 漏洞三：过度推错

如果模型把 exemplar 理解成“这类学生这里就应该错”，
就可能出现：

- `same_*` 上升；
- 但 `consistency` 下降。

修复方式：

- exemplar 只作为群体先验，不是本轮脚本；
- 第三人称层必须仍然考虑当前 tutor 支持和当前局部可达性；
- 不能让 exemplar 覆盖当前轮真实局部支架作用。

---

## 14. 推荐实验设计

建议至少做下面四组：

### A. 当前 strong harness

作为当前强版基线。

### B. strong harness + structural calibration

只给强模型的第三人称编译层加入结构校准。

### C. 当前 v31 weak harness

作为当前弱版最好基线之一。

### D. v31 weak harness + compiler-side structural calibration

只让编译器读 exemplars，不让弱 actor 直接读大量 exemplars。

如果 D 有收益，再加：

### E. v31 weak harness + compiler-side structural calibration + light surface calibration

只在最后表面生成时加极轻量风格对齐。

---

## 15. 我对这个方向的最终判断

我的判断是：

> 这是值得做的，而且比继续硬磨 prompt 更像一个真正的方法升级。

它成立的前提是：

- 仍然保留第三人称状态层；
- few-shot 被提升成“群体校准层”；
- exemplar 只提供群体先验，不提供当前样本真值；
- 检索与压缩都严格受“当前时点可见信息”约束；
- 结构层优先于表面层；
- 编译器优先于演员。

换句话说：

> 我们不是在让模型背答案，  
> 而是在让模型学会“这个学生群体通常怎样理解不完整、怎样局部犯错、怎样把错误说出来”。

这和当前项目目标是对齐的，也和“少量真实学生启动应用”的实际产品场景是对齐的。

---

## 16. 下一步建议

下一步最合理的不是马上全量改代码，而是：

1. 先定义 exemplar schema；
2. 先定义 calibration split；
3. 先做 strong + structural calibration 小样本实验；
4. 再做 v31 + compiler-side structural calibration；
5. 先看五个核心指标是否一起变化。

如果这一步有效，再把它做成正式的 `eedi` 模块。

---

## 参考资料

- National Research Council. *Knowing What Students Know: The Science and Design of Educational Assessment*  
  <https://www.nationalacademies.org/read/10019/chapter/4>

- Mislevy, Almond, Lukas. *A Brief Introduction to Evidence-Centered Design*  
  <https://cresst.org/wp-content/uploads/R632.pdf>

- Dynamic Assessment review  
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC7375920/>

- Wood, Bruner, Ross. *The Role of Tutoring in Problem Solving*  
  <https://doi.org/10.1111/j.1469-7610.1976.tb00381.x>

- Sinha & Kapur. *Productive Failure in Preparatory Problem Solving*  
  <https://journals.sagepub.com/doi/pdf/10.3102/00346543211019105>
