# EEDI strong harness revisit：block8 `ErrorBlueprint` 二轮结果报告（2026-05-15）

## 1. 这轮回答什么问题

block7 发现一个核心矛盾：

> 压薄状态层以后，`consistency` 会上升，但 `error_realization` 容易下降。

所以 block8 专门审计 `ErrorBlueprint`：

> 错误蓝图里到底需要保留多具体？  
> `wrong_claim_seed`、`buggy_rule`、`radatz_error_mechanism` 哪个是真正必要字段？

---

## 2. 实验设置

本轮先跑：

1. `40-task smoke`
2. `1000-task screening`

没有直接上 4334 全量。原因是：

- block8 是字段级诊断；
- 需要先看方向；
- 如果 1000 screening 已经能排除某些版本，就不浪费全量成本。

运行脚本：

- `D:\Study\sii\MathStudent\eedi\run_strong_revisit_block8_20260515.ps1:1`

结果目录：

- smoke：`D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block8_smoke_20260515`
- 1000 screening：`D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block8_1000_20260515`

汇总文件：

- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block8_1000_20260515\summary.json:1`
- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block8_1000_20260515\summary.md:1`

---

## 3. 跑了哪些版本

| version | 含义 |
|---|---|
| `baseline_pc_default` | 完整 `ErrorBlueprint` |
| `error_structure_only` | 保留错误结构，压平 `buggy_rule` 和 `wrong_claim_seed` |
| `error_structure_plus_buggy_rule` | 在结构版上加回 `buggy_rule` |
| `error_structure_plus_wrong_claim_seed` | 在结构版上加回 `wrong_claim_seed` |
| `structure_no_mechanism` | 保留错误存在和 Newman locus，压平 Radatz mechanism 与两个 seed |

新增开关位置：

- `D:\Study\sii\MathStudent\eedi\src\revisit_controls.py:111`
- `D:\Study\sii\MathStudent\eedi\run_eedi_experiments.py:162`

---

## 4. 1000-task screening 总表

| version | consistency | same_knowledge | same_locus | same_mechanism | error_realization | retries | remaining_violations |
|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline_pc_default` | `0.5670` | `0.8056` | `0.5417` | `0.6528` | `0.6316` | `330` | `238` |
| `error_structure_only` | `0.6317` | `0.7260` | `0.6301` | `0.6575` | `0.6518` | `429` | `355` |
| `error_structure_plus_buggy_rule` | `0.5755` | `0.7778` | `0.6944` | `0.6806` | `0.6372` | `461` | `375` |
| `error_structure_plus_wrong_claim_seed` | `0.5728` | `0.7812` | `0.7031` | `0.7031` | `0.5664` | `359` | `264` |
| `structure_no_mechanism` | `0.6157` | `0.7857` | `0.6857` | `0.6429` | `0.6306` | `437` | `353` |

---

## 5. 直接结论

### 5.1 `wrong_claim_seed` 不是当前最该保留的字段

`error_structure_plus_wrong_claim_seed` 的结果很清楚：

- `consistency = 0.5728`
- `error_realization = 0.5664`

它不但没有救回 `error_realization`，反而是本轮最低。

这说明：

> 当前 EEDI strong 里，直接保留具体 `wrong_claim_seed` 容易把生成拉向过具体的局部 claim，反而不利于真实错误外显。

更简单地说：

> `wrong_claim_seed` 看起来像“最接近外显错误”的字段，但实际可能太硬、太窄、太容易把回复带偏。

所以它不应该作为默认强保留字段。

---

### 5.2 `buggy_rule` 比 `wrong_claim_seed` 更有保留价值，但也不是无代价

`error_structure_plus_buggy_rule`：

- `same_locus = 0.6944`
- `same_mechanism = 0.6806`
- `error_realization = 0.6372`

它比 `wrong_claim_seed` 稳得多，说明：

> 相比“具体错句种子”，抽象的错误规则更能帮助模型维持错误机制。

但它的 `consistency = 0.5755`，明显低于 `error_structure_only = 0.6317`。

所以结论不是“加回 `buggy_rule` 最好”，而是：

> `buggy_rule` 对错误机制有帮助，但会牺牲一部分 correctness 对齐。

---

### 5.3 `error_structure_only` 在本轮 screening 里最稳

`error_structure_only` 同时拿到：

- 最高 `consistency = 0.6317`
- 最高 `error_realization = 0.6518`

这很重要，因为它说明：

> 至少在 1000-task screening 上，错误蓝图不需要具体 seed，也能更稳地完成当前任务。

这和 block7 的直觉有一点不同。block7 原本怀疑：

> 也许是因为 `wrong_claim_seed` / `buggy_rule` 被压掉，错误才外显不出来。

但 block8 说明：

> 单独加回这两个字段并没有解决问题；真正的问题可能不在 blueprint 字段本身，而在后面的 `ConstraintBundle` 怎么使用这些字段。

---

### 5.4 `radatz_error_mechanism` 不是可以轻易删掉的字段

`structure_no_mechanism`：

- `consistency = 0.6157`
- `same_mechanism = 0.6429`
- `error_realization = 0.6306`

它不算差，但不如 `error_structure_only`。

这说明：

> `radatz_error_mechanism` 不是纯摆设。  
> 它可能不一定需要非常强地进入 surface generation，但在错误结构层保留它仍然有价值。

所以不建议现在把 mechanism 层删掉。

---

## 6. 模块必要性判断

| 字段 | 当前判断 | 理由 |
|---|---|---|
| `error_presence` | 必须保留 | 决定是否应生成具体数学错误 |
| `newman_error_locus` | 必须保留 | 影响错误落点，`structure_no_mechanism` 仍依赖它 |
| `radatz_error_mechanism` | 建议保留 | 删除后不崩，但不如结构版稳 |
| `buggy_rule` | 条件保留 | 有助于机制，但会伤 consistency |
| `wrong_claim_seed` | 不进默认主线 | 本轮显著伤 `error_realization` |

---

## 7. 是否上 4334 全量

本轮不建议把所有 block8 新版本都上 4334。

### 7.1 不建议上全量的版本

- `error_structure_plus_wrong_claim_seed`
  - `error_realization` 明显最低；
  - 没有继续全量价值。

- `error_structure_plus_buggy_rule`
  - 机制指标不错；
  - 但 `consistency` 明显不如 `error_structure_only`；
  - 可以作为分析版本，不适合作为主线候选。

### 7.2 可选上全量的版本

- `structure_no_mechanism`

它的价值不是成为最强版本，而是回答一个理论问题：

> 如果只保留 Newman locus，不保留 Radatz mechanism，全量上是否仍然稳定？

但从 1000 screening 看，它已经不如 `error_structure_only`，所以不是最高优先。

### 7.3 当前最值得保留的候选

当前 block8 最值得继续保留的是：

> `error_structure_only`

不过它在 block2 里已经跑过 4334 全量，因此不需要重复跑。

---

## 8. 对后续 revisit 的影响

block8 的关键结论是：

> 问题不主要在 `ErrorBlueprint` 里缺了哪个具体 seed。  
> 更可能在 `ConstraintBundle` 把 blueprint 翻译成生成边界时太硬或太窄。

所以下一步应该进入：

## block9：`ConstraintBundle` 字段级 revisit

优先拆：

1. `must_realize_specific_error`
2. `must_anchor_to_local_wrong_claim`
3. `required_commitment_style`
4. `style_constraints`
5. `max_sentences`

目标是回答：

> 哪些约束帮助错误外显，哪些约束把回复逼得过硬，从而伤害 consistency？

---

## 9. 当前最终建议

本轮建议更新为：

> EEDI strong 主线里，`ErrorBlueprint` 保留结构层即可；不要默认强依赖 `wrong_claim_seed`；`buggy_rule` 可作为诊断字段保留，但不应强制进入默认生成边界。

更具体地说：

- 默认保留：
  - `error_presence`
  - `newman_error_locus`
  - `radatz_error_mechanism`

- 默认不强依赖：
  - `wrong_claim_seed`

- 暂时作为诊断字段：
  - `buggy_rule`

下一步：

> 进入 `ConstraintBundle` revisit，而不是继续无限细拆 `ErrorBlueprint`。
