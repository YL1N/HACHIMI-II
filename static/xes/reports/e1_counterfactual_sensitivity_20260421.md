# E1 反事实敏感性测试

## 1. 用途

检查：当 persona 里只改一个关键因素时，

- 状态会不会跟着变
- 答案会不会跟着变
- 正确率会不会跟着变

如果 persona 改了但状态几乎不变，说明画像信号没有被稳定吃进状态层。

## 2. 运行目录

- `outputs/root_cause/E1_counterfactual_sensitivity/run_20260421_120742`

## 3. 各因素结果

| factor | state_change_rate | answer_change_rate | correctness_change_rate | state_improve_rate | positive_acc | negative_acc |
| --- | --- | --- | --- | --- | --- | --- |
| math_subject_strength | 1.0000 | 0.5500 | 0.2100 | 1.0000 | 0.5100 | 0.3400 |
| efficacy | 0.8600 | 0.6500 | 0.2600 | 0.8600 | 0.4900 | 0.3500 |
| srl_fragility | 0.1300 | 0.4700 | 0.2200 | 0.1300 | 0.5600 | 0.4000 |
| engagement_style | 0.2200 | 0.4500 | 0.1400 | 0.2200 | 0.5200 | 0.4600 |

## 4. 整体指标

- `mean_state_change_rate = 0.5525`
- `mean_answer_change_rate = 0.5300`
- `mean_correctness_change_rate = 0.2075`
- `failure_rate = 0.0000`

## 5. 结果解读

- persona 并不是完全没被读到。`math_subject_strength` 和 `efficacy` 都能明显推动状态变化，其中数学强弱这一项几乎每次都会改状态
- 但画像信号读取非常不均衡。`srl_fragility` 和 `engagement_style` 对状态的影响很弱，`state_change_rate` 只有 `0.13` 和 `0.22`
- 有意思的是，后两者虽然不太改状态，却仍然会较频繁地改答案和正确率。这说明一部分 persona 影响可能绕过了状态层，或者状态层对这类抽象特质表达得不够好
- 因此第一层问题不能说不存在，但更准确的说法是：画像信号是“选择性有效”，不是“整体失效”

## 6. 结论

- 第一层画像问题仍然存在，但它更像“哪些 persona 因素能被稳定读到、哪些读不到”的不均衡问题
- `math_subject_strength` 和 `efficacy` 已经证明 persona 可以进入状态层，所以“persona 完全无效”不是主结论
- `srl_fragility` 和 `engagement_style` 进入状态层的能力明显不足，这解释了为什么完整 persona 会显得很多细节没有被稳定利用
- 到目前为止，更像是：第一层是次因，第二层模型边界仍是主因

## 7. 反作弊说明

- 所有反事实 persona 都是手工构造的对照组，没有把真实标签带进 generation path
- 真实答案仍只用于离线判分
