# F1 稳定性测试

## 1. 用途

检查同一个输入重复运行时：

- `response_state` 稳不稳定
- `predicted_answer` 稳不稳定
- `is_correct` 稳不稳定

如果状态很稳但答案乱跳，说明问题更多在后半段 generation。

## 2. 运行目录

- `outputs/root_cause/F1_stability/run_20260421_131620`

## 3. 整体指标

- `response_state_change_rate = 0.0438`
- `predicted_answer_change_rate = 0.4938`
- `is_correct_change_rate = 0.1813`
- `fully_stable_rate = 0.4750`
- `failure_rate = 0.0000`

## 4. 分层结果

| level | state_change_rate | answer_change_rate | correctness_change_rate |
| --- | --- | --- | --- |
| poor | 0.0500 | 0.4250 | 0.1250 |
| low | 0.0750 | 0.5500 | 0.1000 |
| medium | 0.0250 | 0.5000 | 0.2250 |
| high | 0.0250 | 0.5000 | 0.2750 |

## 5. 结果解读

- `response_state_change_rate` 很低，只有 `0.0438`，说明状态层本身相对稳定
- 但 `predicted_answer_change_rate` 高达 `0.4938`，几乎一半任务在重复运行时答案会变
- `is_correct_change_rate = 0.1813` 也不低，说明这种波动不是表面措辞变化，而是真会影响最终对错
- 因此当前随机性主要不在“persona -> state”这段，而在“state -> answer”这段

## 6. 结论

- 第二层问题不只是“模型边界不够”，还包括明显的 generation 不稳定性
- 但从分解结果看，不稳定主要集中在答案生成阶段，而不是状态判定阶段
- 所以 `F1` 的意义不是推翻前面结论，而是进一步细化第二层问题：
  - 状态层相对稳定
  - 最终作答层高波动
- 这也解释了为什么有些实验里整体均值能排开，但题目级结构和主流答案分化仍然很差

## 7. 反作弊说明

- 重复运行使用的是同一输入，不做任何按目标结果修正
- 真实答案仍只用于离线判分
