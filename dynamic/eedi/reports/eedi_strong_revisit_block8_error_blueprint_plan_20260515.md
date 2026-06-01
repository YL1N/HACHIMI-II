# EEDI strong harness revisit：block8 `ErrorBlueprint` 二轮计划（2026-05-15）

## 1. 为什么现在先做 `ErrorBlueprint`

block7 已经把矛盾钉得很清楚：

- `lean_state_stack` 更容易提高 `consistency`
- 但 baseline 更容易保住 `error_realization`

而且这个损失最集中在：

- `codable_math_error`
- `transformation / comprehension / process_skills`
- `incorrect_associations / deficient_prerequisites`
- `conceptual_hint / procedural_hint / answer_elicitation`

这说明当前最值得继续 revisit 的，不是继续泛化地拆状态层，而是：

> `ErrorBlueprint` 到底需要保留多具体，才能把“局部错误”真正说出来。

---

## 2. block8 要回答什么问题

block2 的 `error_structure_only` 已经做过一次：

- 保留 `error_presence`
- 保留 `newman_error_locus`
- 保留 `radatz_error_mechanism`
- 把 `buggy_rule` / `wrong_claim_seed` 压成结构占位

结果是：

- `consistency` 上升
- `error_realization` 下降

所以 block8 要继续问：

> 在 `buggy_rule` 和 `wrong_claim_seed` 里，到底是谁更重要？  
> 以及 `radatz_error_mechanism` 是否也过细了？

---

## 3. 本轮实验版本

### 3.1 基线对照

- `baseline_pc_default`
  - 当前完整 strong 基线

- `error_structure_only`
  - 当前 block2 已跑版本

### 3.2 block8 新版本

- `error_structure_plus_wrong_claim_seed`
  - 保留：
    - `error_presence`
    - `newman_error_locus`
    - `radatz_error_mechanism`
    - `wrong_claim_seed`
  - 压平：
    - `buggy_rule`

- `error_structure_plus_buggy_rule`
  - 保留：
    - `error_presence`
    - `newman_error_locus`
    - `radatz_error_mechanism`
    - `buggy_rule`
  - 压平：
    - `wrong_claim_seed`

- `structure_no_mechanism`
  - 保留：
    - `error_presence`
    - `newman_error_locus`
  - 压平：
    - `radatz_error_mechanism`
    - `buggy_rule`
    - `wrong_claim_seed`

---

## 4. 每个版本到底在测什么

### 4.1 `error_structure_plus_wrong_claim_seed`

它测的是：

> 是不是只要保住“当前轮要说的那个局部错句方向”，就足以把错误外显回来？

如果这个版本把 `error_realization` 拉回去，说明：

> 真正关键的不是程序化 `buggy_rule` 解释，而是当前轮局部错误 claim 本身。

### 4.2 `error_structure_plus_buggy_rule`

它测的是：

> 是不是只要保住错误规则类型，就能支撑局部外显？

如果这个版本恢复效果更强，说明：

> 当前 surface realization 更依赖“错误规则”而不是具体 claim 种子。

### 4.3 `structure_no_mechanism`

它测的是：

> `radatz_error_mechanism` 这层细标签到底有没有真实生成价值，还是只是解释用标签？

如果去掉它几乎不伤分，就说明：

> `radatz_error_mechanism` 当前可能更偏解释字段，不是强生成字段。

---

## 5. 运行方式

这轮建议还是：

1. 先跑 smoke
2. 再跑 `1000-task` screening
3. 最后只把值得保留的版本上 `4334`

### 5.1 smoke

先用极小样本确认新开关没坏：

```powershell
python eedi/run_eedi_experiments.py --config eedi/configs/run_strong_population_calibrated_test1000_20260511.json --max_tasks 40 --output_dir eedi/outputs/smoke_block8_20260515/error_structure_plus_wrong_claim_seed --error_blueprint_mode structure_plus_wrong_claim_seed
```

同样方式跑：

- `structure_plus_buggy_rule`
- `structure_no_mechanism`

### 5.2 1000-task screening

建议继续复用：

- `D:\Study\sii\MathStudent\eedi\configs\run_strong_population_calibrated_test1000_20260511.json:1`

版本矩阵：

- `baseline_pc_default`
- `error_structure_only`
- `error_structure_plus_wrong_claim_seed`
- `error_structure_plus_buggy_rule`
- `structure_no_mechanism`

### 5.3 全量 4334

只有当某个新版本满足下面条件，才值得上全量：

1. `consistency` 不显著差于 `error_structure_only`
2. `error_realization` 明显高于 `error_structure_only`
3. generation failure 没有显著变多

---

## 6. 判定规则

block8 不追“哪项单分最高”，而是追这三个问题：

### 6.1 谁最能救回 `error_realization`

重点比较：

- `error_structure_only`
- `error_structure_plus_wrong_claim_seed`
- `error_structure_plus_buggy_rule`

如果只加一个字段就能明显救回 `error_realization`，那它就是 `ErrorBlueprint` 的真核心字段。

### 6.2 谁更不伤 `consistency`

如果某个版本虽然把错误说回来了，但 `consistency` 掉回 baseline 以下太多，它也不适合作为精简主线。

### 6.3 `radatz_error_mechanism` 是否必要

如果 `structure_no_mechanism` 变化很小，就说明：

> 机制标签层当前不是强必要字段。

---

## 7. 当前新增的代码支持

为了做 block8，这轮已经补好了新的 `error_blueprint_mode`：

- `full`
- `structure_only`
- `structure_plus_wrong_claim_seed`
- `structure_plus_buggy_rule`
- `structure_no_mechanism`

对应代码：

- `D:\Study\sii\MathStudent\eedi\src\revisit_controls.py:111`
- `D:\Study\sii\MathStudent\eedi\run_eedi_experiments.py:162`

---

## 8. block8 跑完后，下一步是什么

如果 block8 能明确找出：

- `wrong_claim_seed` 才是真核心
或
- `buggy_rule` 才是真核心

那 block9 就直接转去做：

> `ConstraintBundle` 字段级 revisit

因为到那时，问题就会变成：

> 既然 ErrorBlueprint 已经知道该保留什么，为什么它还是不能稳定外显？  
> 那么问题很可能出在约束编译层，而不是 blueprint 本身。

---

## 9. 当前建议

当前建议非常明确：

1. 先不要继续拆 `StudentContextProfile`
2. 先不要继续泛化拆 `TutorTurnProfile`
3. 直接进入 `ErrorBlueprint` 二轮实验

因为这是当前最短路径：

> 它最直接对应 block7 里已经看到的核心矛盾：`consistency` 上升了，但局部错误没有被稳定说出来。
