# D2 强制状态服从：`full_forced_state`

## 1. 用途

比较：

- `D1 = simple_forced_state`
- `D2 = full_forced_state`

看完整 generation 协议到底是在破坏状态服从，还是在一定程度上帮助状态边界落地。

## 2. 运行目录

- `D1`
  - `outputs/root_cause/D1_simple_forced_state/run_20260421_103243`
- `D2`
  - `outputs/root_cause/D2_full_forced_state/run_20260421_105905`

## 3. 四状态准确率对比

### D1

| 状态 | accuracy |
| --- | --- |
| mastered | 0.6229 |
| partial | 0.5450 |
| guessable | 0.5504 |
| unreachable | 0.4164 |

### D2

| 状态 | accuracy |
| --- | --- |
| mastered | 0.8732 |
| partial | 0.8040 |
| guessable | 0.6607 |
| unreachable | 0.5267 |

## 4. 关键指标

- `D1 strict_state_descending_item_count = 1`
- `D2 strict_state_descending_item_count = 7`
- `D1 same_dominant_answer_all_states_count = 47`
- `D2 same_dominant_answer_all_states_count = 77`
- `D2 failure_rate = 0.00025`
- `D2 retry_count = 28`
- `D2 remaining_violations = 63`

## 5. 结果解读

- `D1` 的整体准确率没有严格递降，但 `D2` 变成了严格递降：`mastered > partial > guessable > unreachable`
- 这说明完整 generation 协议并没有把本来就存在的状态差异进一步吃掉；相反，它至少在整体均值层面把四档重新排开了
- 但这不代表 `D2` 已经好。`unreachable = 0.5267` 仍然太高，说明最低状态依旧明显过强
- `150` 题里只有 `7` 题满足四状态严格递降，说明 item 级状态服从仍然很弱
- 更关键的是，四状态主流答案完全相同的题数从 `47` 升到 `77`，说明完整协议虽然更容易给出“看起来有顺序的整体均值”，却可能进一步压缩了跨状态的答案分化

## 6. 结论

- 不能把当前问题简单归咎为“完整方法协议破坏了状态服从”
- 从 `D1 -> D2` 的对比看，方法层更像是在做两件事：
  - 帮助整体准确率按四档排开
  - 但没有真正解决低状态过强，而且可能让大量题目的跨状态答案更趋同
- 因此当前主因仍然更偏第二层，也就是模型边界本身；方法层不是首要主因，但也没有把题目级状态分化真正做出来

## 7. 反作弊说明

- `D2` 没有把真实标签带进 generation path
- 这里只把状态从“模型推断”改成“外部强制指定”，其余 generation 协议保持完整
- 真实答案仍只用于离线判分
