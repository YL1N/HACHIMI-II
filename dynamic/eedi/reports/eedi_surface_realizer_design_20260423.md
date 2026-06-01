# EEDI 表层实现层纠偏设计
## 先说明一次错误
上一版 `SurfaceStylePlan` 有明显问题。
它把“学生短答很多”当成了一个显式优化方向，并把长度、短语形态、是否解释等提前写进约束。
这个方向虽然能让输出变短，但属于用当前 EEDI 样本现象反推规则，容易变成数据集特化。
这不符合我们的核心原则：
- 不能根据 EEDI 已知真实学生 case 加规则
- 不能为了 `ROUGE-L` 或 `cos-sim` 去迎合某个数据集的表面分布
- 不能让表层层重新决定对错、错法和核心内容

所以这版已经撤回旧设计。
保留的是“最后需要一个表层实现层”的思想，删除的是“提前预测短答并压缩输出”的实现。

## 新设计是什么
新对象是：
- `SurfaceRealizedTurn`

实现文件：
- [surface_style.py](D:/Study/sii/MathStudent/eedi/src/surface_style.py)

它只做最后一步：
- 输入前面主链已经生成的 `draft_turn`
- 输出更像学生说法的 `realized_turn`

它不能重新决定：
- 学生答对还是答错
- 错在什么地方
- 是否理解了 tutor 的帮助
- 这一轮的数学核心内容

## 现在的主链
现在主链是：

`DialogueContext -> StudentContextProfile -> TutorTurnProfile -> InteractionState -> StateTransitionPrediction -> ConstraintBundle -> DraftStudentTurn -> SurfaceRealizedTurn -> DynamicViolationCheck -> Optional One-Step Retry`

也就是说：
- 前半段继续负责认知轨迹
- `DraftStudentTurn` 负责把认知轨迹变成内容草稿
- `SurfaceRealizedTurn` 只负责把草稿从专家式表达改成学生式表达

## 为什么这比旧版更合理
旧版问题是：
- 在生成前就判断“该短还是该长”
- 容易把具体数学内容压没
- 容易从 EEDI 样本现象里学到数据集特化偏好

新版边界是：
- 先保住认知内容
- 再做语义保持的表层实现
- 表层实现不许改变正确性、错误路径和核心数学内容

## 这层不是作弊后处理
它不是为了贴近某个真实 `gt_turn`。
它看不到真实下一轮学生回复。
它只看到：
- 当前可见对话上下文
- 第三人称学生状态
- 状态转移预测
- 前面生成出的 draft

它的任务不是“模仿 EEDI 某个句子”，而是一般性地避免专家式、导师式、过度成熟式表达。

## 哪些是理论驱动，哪些是数据驱动
理论驱动部分仍然是：
- `StudentContextProfile`
- `InteractionState`
- `StateTransitionPrediction`
- `ConstraintBundle`

表层实现层不是纯教育理论对象。
它更像模型里的 decoder/renderer：
- 不改内部表示
- 只负责把内部表示落成最终话语

这里允许使用“学生表达一般不应像专家解释”这种通用约束。
但不能写成：
- EEDI 学生常怎么说
- 某道题学生常怎么说
- 某些 phrase 应该怎么替换

## 当前代码改动
1. 删除旧的 `SurfaceStylePlan` 预测层。
2. 恢复 `compile_constraints(...)` 只由状态转移预测生成约束。
3. 新增 `realize_student_surface_turn(...)`，在 draft 生成之后执行。
4. 输出记录里新增：
- `draft_turn`
- `surface_realization`

这样后续可以检查：
- 草稿本身是否保持了认知轨迹
- 表层实现是否只改表达，没有改核心内容

## 三点说明
1. 改了哪个环节  
把上一版提前参与约束的 `SurfaceStylePlan` 撤回，改成生成后的语义保持 `SurfaceRealizedTurn`。

2. 理论依据是什么  
认知层仍由教育理论驱动。表层层是输出实现层，类似 decoder/renderer，理论边界是“不改变认知状态，只改变表达实现”。

3. 如何避免 cheating  
不看真实下一轮回复，不写 EEDI case 规则，不根据 EEDI 表面分布强行压短。只把已生成的 draft 从专家式表达转换成学生式表达。
