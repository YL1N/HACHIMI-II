# C1 方法消融：`direct` vs `state_single` vs `state_step`

## 1. 用途

判断当前问题主要出在方法链的哪一段。

这一步固定：

- persona：`full_persona`
- 题集：`outputs/run_20260420_014128/selected_questions.json`
- 模型：`qwen`
- 判分：`rules_only`

只改方法：

- `direct = persona -> direct answer`
- `state_single = persona -> state -> one final step`
- `state_step = persona -> state -> bounded multi-step + violation check + optional retry`

## 2. 运行目录

- `direct`
  - `D:\Study\sii\MathStudent\outputs\root_cause\C1_direct\run_20260420_225055`
- `state_single`
  - `D:\Study\sii\MathStudent\outputs\root_cause\C1_state_single\run_20260420_225125`
- `state_step`
  - `D:\Study\sii\MathStudent\outputs\root_cause\C1_state_step\run_20260420_225213`

## 3. 关键结果

| 方法 | overall acc | overall gap | item Pearson | item MAE | mean level gap | strict monotonic | same dominant | failure rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct | 0.6694 | 0.0021 | 0.3102 | 0.3552 | 0.1261 | 0 | 130 | 0.0000 |
| state_single | 0.6615 | 0.0100 | 0.3195 | 0.2725 | 0.0616 | 24 | 99 | 0.0000 |
| state_step | 0.7023 | 0.0307 | 0.3508 | 0.2477 | 0.0557 | 16 | 103 | 0.0003 |

## 4. 判断

- 题目级相关性最好的方法是：`state_step`
- 四档结构性最好的方法是：`state_single`
- `direct` 的最大问题不是平均分，而是四档结构明显塌缩：它的 `strict_monotonic_item_count` 很低，且跨档主流答案相同题数很高
- 如果 `state_single` 或 `state_step` 在 item Pearson、严格单调、跨档答案分化上明显优于 `direct`，就说明状态层不是摆设，而是在纠正直接作答带来的结构塌缩
- 如果 `state_step` 反而不如 `state_single`，则问题更像出在多步协议本身，而不是“有没有状态层”

## 5. 结论

本实验的核心是比较三种链路谁更能保住：

- 题目级相关性
- 四档分层结构
- 跨档答案分化

因此正式结论应优先看这些结构指标，而不是只看整体准确率是否贴均值。

## 6. 反作弊说明

- 三个条件都没有把真实标签带入 generation path
- 没有按题号特判
- 没有按目标 accuracy 后处理翻答案
- 只改方法链，不改题集、不改 persona、不改评测器
