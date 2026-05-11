# XES / EEDI consistency 近似同值诊断（2026-05-08）

## 1. 结论先说

当前看到的：

- `XES overall_consistency ≈ 0.6767`
- `EEDI correctness match rate ≈ 0.6679`

这两个数**看起来接近**，但目前证据不支持：

> “它们都差不多是因为都有最后一步必须收口的机制。”

更合理的判断是：

1. 这两个指标**不是同一个指标**；
2. 两边都存在“最后一步必须收口”的协议约束，但它更像**共同的结构背景**，不是单独主因；
3. 真正更像主因的，是：
   - 二元匹配型指标本身的统计性质；
   - 模型整体偏保守、偏局部合法、偏不冒进；
   - 类别/边际分布带来的基线效应。

一句话总结：

> 最后一步强制收口可能有影响，但更像“共同收缩力”；目前没有证据说明它直接把两边都推到了 0.67 左右。

---

## 2. 两边的 0.67 其实不是一回事

### 2.1 XES

`overall_consistency` 的定义是：

> 先对每个学生计算逐题 `real == pred` 的比例，再对所有学生取平均。

本次 `common_test_60x96` 强模型结果：

- `overall_consistency = 0.6767`

对应代码：

- `D:\Study\sii\MathStudent\xes\src\student_conditioned_benchmark.py:1349`
- `D:\Study\sii\MathStudent\xes\src\student_conditioned_benchmark.py:1403`

### 2.2 EEDI

`0.6679` 对应的是 detached eval 里的 `Correctness match rate`：

> 只在官方标了 `correct/incorrect` 的 turn 上，判断候选 student turn 的 correctness 标签是否与真实 turn 匹配。

本次 `official_test_1000_updated_20260429`：

- `n_eligible_rows = 524`
- `match_count = 350`
- `match_rate = 0.6679`

对应代码：

- `D:\Study\sii\MathStudent\eedi\src\detached_eval.py:385`
- `D:\Study\sii\MathStudent\eedi\src\detached_eval.py:387`

所以这里首先要澄清：

> `XES 0.6767` 和 `EEDI 0.6679` 不是同一评测对象下的同一种 consistency。

---

## 3. 两边都确实有“最后一步必须收口”的机制

### 3.1 XES

XES 明确有：

- 如果 `remaining_step_budget = 1`
- 那么 `next_action MUST be final_answer`

对应位置：

- `D:\Study\sii\MathStudent\xes\src\prompts.py:789`
- `D:\Study\sii\MathStudent\xes\src\generation.py:232`

### 3.2 EEDI

EEDI 明确有：

- 如果到了 final allowed step
- 那么 `step_kind must be exactly finalize_turn`

对应位置：

- `D:\Study\sii\MathStudent\eedi\src\prompts.py:214`
- `D:\Study\sii\MathStudent\eedi\src\generation.py:446`

所以两边确实共享一个结构事实：

> 步数不是开放的，最后一步必须交付最终产物。

但“共享这个机制”不等于“相近指标就是它造成的”。

---

## 4. EEDI 的证据：1 步收口不是高分来源，反而更差

### 4.1 EEDI 全量 step budget 分布

从：

- `D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_updated_20260429\predictions.jsonl`

统计得到：

- `max_step_budget = 1`：`501`
- `max_step_budget = 2`：`406`
- `max_step_budget = 3`：`72`
- `max_step_budget = 4`：`21`

### 4.2 只看 correctness eligible rows（524 条）

按 `max_step_budget` 分组后的 correctness match rate：

| budget | n | match_rate |
|---|---:|---:|
| 1 | 180 | 0.5611 |
| 2 | 293 | 0.7338 |
| 3 | 45 | 0.6667 |
| 4 | 6 | 0.6667 |

尤其关键的是：

- `budget = 1`：`0.5611`
- `budget > 1`：`0.7238`

这说明：

> 在 EEDI 里，最强的“最后一步马上 finalize”样本，不是把 overall 结果拉高的来源，反而是表现更差的一组。

因此不能说：

> “EEDI 的 0.6679 主要是被最后一步强制 finalize 推出来的。”

---

## 5. XES 的证据：1 步预算样本也明显更差

### 5.1 XES 强模型总体

从：

- `D:\Study\sii\MathStudent\xes\outputs\common_test_60x96\strong_hachimi\run_20260507_171156\predictions.jsonl`

统计得到：

- 总样本：`5760`
- 整体 agreement：`0.6767`
- 真实正确率：`0.8306`
- 预测正确率：`0.7007`

### 5.2 按 `constraint_bundle.max_thinking_steps` 分组

| max_thinking_steps | n | agreement | real_acc | pred_acc |
|---|---:|---:|---:|---:|
| 1 | 3580 | 0.5598 | 0.7771 | 0.5575 |
| 2 | 1630 | 0.8485 | 0.9067 | 0.9245 |
| 4 | 550 | 0.9291 | 0.9527 | 0.9691 |

这也很关键：

> 在 XES 里，`max_thinking_steps = 1` 的样本同样不是高 consistency 来源，而是显著更差的一组。

### 5.3 按实际使用步数 `thinking_steps_n` 分组

| thinking_steps_n | n | agreement | real_acc | pred_acc |
|---|---:|---:|---:|---:|
| 1 | 4171 | 0.6058 | 0.7996 | 0.6111 |
| 2 | 1470 | 0.8571 | 0.9102 | 0.9306 |
| 3 | 111 | 0.9369 | 0.9369 | 1.0000 |
| 4 | 8 | 0.8750 | 0.8750 | 1.0000 |

这里也说明：

> 真正 agreement 高的，不是被一步强行收口的样本，而是本来就更容易、允许更多步骤、真实正确率也更高的样本。

---

## 6. 因此：为什么两个结果还会都在 0.67 左右

目前更像有三类原因。

### 6.1 原因一：两边都是二元匹配型指标，天然容易被边际分布影响

XES 本质上看的是：

- 每条记录上 `real == pred`

EEDI correctness 本质上看的是：

- 每条 eligible turn 上 `correct/incorrect` 是否匹配

这类指标有一个共同特点：

> 很容易受真实标签比例、预测标签比例影响。

### 6.2 原因二：两边都有“保守、局部合法、不冒进”的生成倾向

XES 里：

- 受 `ItemResponseState`
- `ConstraintBundle`
- 最终答案协议

EEDI 里：

- 受 `StudentTurnState`
- `ConstraintBundle`
- `finalize_turn` 协议

共同效果是：

> 系统更倾向于给出局部合法、贴当前状态、不过分成熟的输出。

这会让模型不太容易“乱飞”，但也会让很多结果收缩在中间区域。

### 6.3 原因三：两边都离一个简单保守基线不算太远

#### XES

- observed agreement：`0.6767`
- 按真实/预测边际分布算出的 chance baseline：`0.6327`
- 只高出：`0.0441`

#### EEDI

- observed match：`0.6679`
- 多数类基线：`0.6279`
- 只高出：`0.0401`

这说明：

> 两边这个 0.67 都不是“离朴素保守基线特别远”的结果。

换句话说，它们数值接近，更可能是：

- 指标类型接近；
- 系统风格都偏保守；
- 边际分布也把结果压在了一个相似区间。

而不是：

- 单独由“最后一步必须收口”造成。

---

## 7. 目前最稳妥的判断

当前最稳妥的判断是：

> “最后一步必须收口”机制可能有影响，但更像共同背景约束，不是这两个 0.67 的直接主因。

更准确的说法应是：

> XES 和 EEDI 都采用了受限单步/终步协议，这会让输出更保守、更局部合法；再叠加二元匹配指标和标签边际分布，最终更容易出现相近的中段一致率。

---

## 8. 如果后面要更严谨地证伪 / 证实

建议做三件事。

### 8.1 对 EEDI 做 budget 分桶正式汇报

至少汇报：

- 各 `max_step_budget` 的 `correctness match rate`
- `same_error_rate`
- `pred_correct / pred_incorrect / pred_na` 分布
- `cosine / rouge`

### 8.2 对 XES 做步数分桶正式汇报

至少汇报：

- 各 `max_thinking_steps` 的 `agreement`
- `acc`
- 真实正确率
- 预测正确率
- 四档学生上的同样分桶

### 8.3 补一个去边际分布影响的指标

建议至少补：

- Cohen's kappa
- balanced accuracy
- per-class recall

因为单看 match / consistency 很容易把“类别比例造成的相近”误读成“机制相同造成的相近”。

---

## 9. 最后一句话

如果要对老师说人话，可以直接说：

> 现在 XES 和 EEDI 都大概在 0.67 左右，不代表它们被同一个“最后一步强制收口”机制卡住了。我们已经查过，真正一步收口的样本在两边都反而更差。更像是这两个系统都偏保守、评测又都是二元匹配型，所以数值自然挤在了一个相近区间。
