# EEDI 无评测劫持审计

这份说明对应当前 `eedi/` 主链，目标是回答两个层次的问题：

> 1. 现在的 generation pipeline 有没有把评测信息、未来信息或官方标注偷偷带进生成链？
> 2. 在已经知道评测看什么的前提下，方法里有没有“专门朝评测点补强”的成分？

结论先写在前面：

- 第一层结论：当前 generation 主链没有直接读取官方 `correctness / acts / kcs / persona` 标注，没有读取真实下一轮学生回复，也没有读取官方评测 prompt、judge 输出或任何分数。
- 第二层结论：如果把“明知评测看什么，就专门往这些点加强”也算 hacking，那么当前链路里有些模块是安全的方法层，有些模块则已经带有明显的评测导向风险，不能笼统地说“完全没有 hacking”。
- 本次又进一步把 `gt_turn` 从 generation task 对象里拆走，减少误用空间。

## 1. 当前 generation path 实际吃到什么

现在 `_execute_turn_prediction_task(...)` 的生成主链是：

`DialogueContext -> StudentContextProfile -> TutorTurnProfile -> InteractionState -> StateTransitionPrediction -> ErrorBlueprint -> ConstraintBundle -> GeneratedStudentTurn`

它只基于：

- 当前题目文本
- 当前学科标签
- 当前轮之前的对话历史
- 上面这些信息推出来的第三人称状态对象

## 2. 明确不进 generation path 的东西

下面这些东西不应该进入生成链，而且当前代码里也没有进入：

- 真实下一轮学生回复
- 官方 `correctness`
- 官方 `acts`
- 官方 `eedi_kcs`
- 官方 `ocean_persona / freeform_persona`
- 官方评测 prompt
- 官方 judge 输出
- 任何自动评测分数

## 3. 这次额外收紧的一点

之前 `TurnPredictionTask` 本身还带着 `ground_truth_student_turn`。

虽然生成函数并没有使用它，但审计上不够干净，因为 gold 和 generation task 还挂在同一个对象上。

这次改成：

- `TurnPredictionTask` 只保留 generation 必需字段
- `ground_truth_student_turn` 单独存进 `ground_truth_by_key`
- 只有生成完成之后，写记录时才把 `gt_turn` 拼回去

所以现在 generation 函数连“顺手误用 gold”的入口都没有了。

## 4. 官方标注在什么地方才出现

官方 annotated EEDI 数据只在生成完成后才会进入：

- `export_official_eval_csv(...)`
- detached eval / official eval

也就是说：

- 先生成
- 后导出评测输入
- 再跑评测

评测分支和生成分支是时序分离的，不是边生成边看标注。

## 5. 关于 ErrorBlueprint 会不会变成“对着指标写方法”

这里要区分两件事：

### 不是 hacking 的部分

`ErrorBlueprint` 用的是：

- Newman 的 error locus
- Radatz 的 error mechanism
- Brown & Burton 的 buggy-rule / mal-rule 思路

这些是独立于 EEDI 和独立于官方评测的理论对象。

如果 generation 明确建模“学生这次错在什么环节、由什么错误规则驱动”，这属于：

- 方法本身更清楚
- 不是偷看 gold
- 不是按题号特判
- 不是为某个 benchmark phrase 做 prompt patch

### 仍需警惕的部分

如果后面开始根据 detached eval 分数不断手搓 prompt，只为了把：

- `same_error_rate`
- `same_error_locus_rate`

这些数值推高，那就会滑向“对着指标调方法”。

所以后续纪律应该是：

- 可以改对象层和状态层
- 可以改理论化约束
- 不要根据个别 case 拼 prompt 补丁
- 不要为了某个指标去硬控输出表面形状

## 6. 当前审计结论

在当前代码状态下，我认为：

- **没有发现直接的评测信息泄露到 generation path**
- **没有发现真实未来学生回复进入 generation prompt**
- **没有发现官方标注进入 generation prompt**
- **没有发现按题号/数据集模板的特判**

但仍然需要保持一个研究纪律：

- 以后不要根据 detached eval 的 case 反向手调 prompt 去贴评测
- 如果要继续改进，应优先改第三人称对象层，而不是补丁式表面控制

## 7. 按更严格定义重新分类

如果按“只要明知评测点，就专门加强这些点，也算 hacking”的标准来审计，当前模块可以分成三类。

### A. 相对干净的方法层

这些模块主要是在做第三人称建模，本身不依赖评测定义，也不是在追某个分数：

- `DialogueContext`
- `StudentContextProfile`
- `TutorTurnProfile`
- `InteractionState`
- `StateTransitionPrediction`
- `ErrorBlueprint`
- `ConstraintBundle`

原因是：

- 它们回答的是“学生当前处在什么状态、老师这轮在干什么、学生下一步大概会怎样回应”。
- `ErrorBlueprint` 虽然会影响后面的 error 结果，但它依赖的是 Newman / Radatz / Brown & Burton 这类独立理论对象，不是官方评测字段。
- 这部分更像是在把“学生此刻怎样想、怎样错”显式对象化。

### B. 边界可疑层

这些东西出发点不一定错，但已经明显受到评测诊断结果驱动：

- 不确定性偏置修正
- 动态违例检查
- 一次局部重试

原因是：

- 它们不是直接建模“学生是谁”，而是在纠偏“模型不要总把错说成犹豫、不要突然成熟化”。
- 这和真实学生建模目标是对齐的，但也是在回应我们已经观察到的评测失分模式。
- 所以它们还算可以辩护，但必须克制，不能演变成“针对某个指标样式做表面修补”。

### C. 评测导向风险最高的层

这部分虽然没有泄露 gold，但已经很接近“守住评测看的语义点”：

- `surface_style.py`
- `semantic_preservation.py`
- `SURFACE_REALIZER_SYSTEM_PROMPT`
- `SEMANTIC_PRESERVATION_REVIEW_SYSTEM_PROMPT`

原因很直接：

- 它们显式要求“保留 correctness / incorrectness / error path / uncertainty / turn function”。
- 这已经不是在先建模学生，再自然生成，而是在生成后再检查“别把评测会看的东西改坏”。
- 从研究方法上说，这更像一个输出后处理保护层，而不是学生状态层本身。

所以如果按你这个更严格定义：

- 我不能说当前 pipeline 已经完全没有 hacking。
- 更准确的说法是：**没有信息泄露型 hacking，但存在评测导向强化的风险，其中风险最高的是 surface realization 和 semantic preservation 这层。**

## 8. 接下来如果要进一步去 hacking，优先顺序应该是什么

如果目标是让方法更站得住，而不是更会贴评测，我建议优先做这三件事：

1. 保留第三人称对象层，继续只改 `InteractionState / StateTransition / ErrorBlueprint / ConstraintBundle` 这种方法对象。
2. 缩减或移除 `surface_style + semantic_preservation` 这类“生成后再守语义点”的模块，避免它们继续承担指标保护职能。
3. 后续开发尽量采用盲一点的流程：先按理论改对象，再批量评测，不根据单个 case 反复手搓 prompt。

一句话总结：

> 在你这个更严格定义下，真正危险的不是 future leakage，而是“知道评测看 correctness / error / wording 之后，专门在这些点上加保护层”。
