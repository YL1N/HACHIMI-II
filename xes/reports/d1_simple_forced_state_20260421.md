# D1 强制状态服从：`simple_forced_state`

## 1. 用途

判断模型在最简单条件下，能不能仅凭强制状态本身把四种边界分开。

这里故意不走 persona，也不走状态推断，只做最简诊断：

- 输入：`forced response_state + math item`
- 输出：直接最终答案

## 2. 运行目录

- `outputs\root_cause\D1_simple_forced_state\run_20260421_103243`

## 3. 四状态准确率

| 状态 | accuracy |
| --- | --- |
| mastered | 0.6229 |
| partial | 0.5450 |
| guessable | 0.5504 |
| unreachable | 0.4164 |

## 4. 关键指标

- `strict_state_descending_item_count = 1`
- `same_dominant_answer_all_states_count = 47`
- `failure_rate = 0.0985`

## 5. 结果解读

- 四状态整体准确率没有严格下降：`mastered > guessable > partial > unreachable`
- `guessable` 甚至略高于 `partial`，说明只靠最简单的强制状态词，模型也没有稳定拉开中低状态边界
- `unreachable` 仍有 `0.4164` 的正确率，说明低状态并没有被压到足够弱
- `150` 题里只有 `1` 题满足四状态严格递降，说明问题不是少数边缘题，而是整体状态服从都很弱
- 仍有 `47` 题在四个状态下主流答案完全相同，说明大量题目的答案分化能力不足

## 6. 结论

- `D1` 已经足够说明：第二层问题，也就是当前模型边界本身，是明显主因之一
- 这里还不能直接下结论说“方法层不重要”，因为 `D2` 还要检验完整 generation 协议有没有继续破坏状态服从
- 但至少可以先排除一种乐观假设：不是把 persona 和状态推断都拿掉后，模型就会自然把四档边界分开

## 7. 反作弊说明

- 没有引入真实标签到 generation path
- 这里只喂固定状态，不按题号做任何特判
- 真实答案仍只用于离线判分
