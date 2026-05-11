# XES 数学能力锚点式 harness 改动说明

## 这次改了什么

这次不是继续加 prompt 补丁，而是把 `response-anchored persona` 往前推进了一步：

1. 先从 XES support set 的真实学生首答记录里，直接计算结构化数学能力锚点。
2. 再把这个能力锚点写入 persona 文件。
3. `StudentModel` 构建时，优先采用这个能力锚点来生成 `math_task_capability_profile`。
4. 后续 `student × item` 交互判断继续基于这个结构化能力对象工作。

## 现在能力锚点里有什么

当前只保留 support data 可以直接观测或近似观测的维度：

- 计算流畅性
- 应用题迁移
- 多步稳定性
- 几何直觉
- 规律/组合/计数识别
- 选择题排除
- 填空精度
- 困难题坚持性
- 猜测倾向

这些维度来自：

- 模块标签
- 题目是否有选项
- support set 上的 easy / medium / hard 划分
- 真实学生首答对错

## 理论依据

这一步的理论角色不是“教育心理学上完整的学生能力模型”，而是一个任务相关的 `task-specific capability boundary`。

它服务于本项目的第三人称状态链：

`StudentModel -> StudentItemInteractionDecision -> ItemResponseState -> ConstraintBundle -> Answer`

也就是说，它的目标不是解释一切，而是给“这类学生遇到这类题，大概率能不能够到、会在哪些边界上失手”提供一个可审计的结构化先验。

## 为什么这比原来更稳

原来 `math_task_capability_profile` 主要靠 LLM 根据 general persona + 少量 anchor summary 去推。

问题是：

- general persona 太泛
- anchor summary 太短
- LLM 很容易把能力边界脑补得过强或过弱

现在改成：

- 先离线从 support data 直接算能力锚点
- 再要求 LLM 只能在这个边界内做解释

这样可以减少：

- 能力漂移
- 同类 persona 之间无意义随机差异
- 题目级正确率相关性被纯文本自由发挥冲掉

## 反作弊边界

这次改动没有把评测卷真实标签带进生成链。

严格边界如下：

- 只用 support set 非评测题目的真实作答
- 不用当前评测卷真实正确率
- 不用当前评测卷真实学生答案
- 不用题目 ID 特判
- 不在运行时硬控目标正确率

所以这一步属于 harness / context 侧增强，不属于把评测答案偷偷塞进 prompt。

## 当前局限

这还是第一版。

目前仍有三个限制：

1. `confidence_calibration` 和细粒度 `error_family` 还不能从 XES 静态首答日志里可靠恢复。
2. 多步稳定性、困难题坚持性还是代理指标，不是直接观测。
3. 现在 persona 的结构化能力锚点是按小邻域聚合，不是按单个最优匹配学生一一绑定。

## 下一步

下一步应该做两件事：

1. 用新 anchored persona 先跑小规模主实验 smoke，确认 item-level correlation 有没有正向变化。
2. 如果有，再继续把 `student_item_interaction_decision` 从当前规则版推进到更细的可解释判定版。
