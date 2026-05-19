# EEDI strong harness revisit：block9 `ConstraintBundle` 字段级结果报告（2026-05-17）

## 1. 这一轮回答什么问题

block8 已经把 `ErrorBlueprint` 收敛到一个更干净的方向：

> 错误蓝图保留结构层即可，不默认强依赖具体 `wrong_claim_seed` 或具体 `buggy_rule`。

block9 继续往后看一层：

> 当错误结构层进入 `ConstraintBundle` 时，哪些生成约束是必要的，哪些约束反而把学生回复压得太硬？

本轮不是重新证明 strong 比 weak 好，也不是重新比较 EEDI 原始版本。  
本轮只看 strong 主线内部的约束层取舍。

---

## 2. 实验设置

本轮跑的是：

- `40-task smoke`
- `1000-task screening`

没有直接全量 4334。原因是：

- block9 是字段级审计；
- 先用 1000 screening 判断方向；
- 只有明显优于当前候选主线的版本，才值得继续上 4334。

运行脚本：

- `D:\Study\sii\MathStudent\eedi\run_strong_revisit_block9_20260515.ps1`

结果目录：

- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block9_1000_20260515`

汇总文件：

- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block9_1000_20260515\summary.json`
- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block9_1000_20260515\summary.md`

---

## 3. 本轮版本

| version | 含义 |
|---|---|
| `original_baseline_pc_default` | 原始 strong population-calibrated baseline，完整 `ErrorBlueprint` + default constraints |
| `candidate_structure_default` | block8 候选主线：`error_blueprint_mode = structure_only` + default constraints |
| `constraint_no_specific_error_realization` | 不强制具体数学错误一定外显 |
| `constraint_no_local_wrong_claim_anchor` | 不要求回复锚定到局部 wrong-claim |
| `constraint_no_commitment_style` | 去掉强承诺风格约束，回复不再被压成固定确定 / 犹豫风格 |
| `constraint_no_style_constraints` | 大幅移除表层风格约束，只保留长度和必要边界 |
| `constraint_minimal_length_only` | 只保留最小长度、禁止未来信息、禁止 tutor 化等底线约束 |

---

## 4. 1000-task screening 总表

| version | consistency | same_knowledge | same_locus | same_mechanism | error_realization | retries | remaining_violations |
|---|---:|---:|---:|---:|---:|---:|---:|
| `original_baseline_pc_default` | `0.5315` | `0.6528` | `0.5417` | `0.5833` | `0.6429` | `319` | `241` |
| `candidate_structure_default` | `0.5878` | `0.7500` | `0.5882` | `0.5735` | `0.5965` | `433` | `347` |
| `constraint_no_specific_error_realization` | `0.6565` | `0.8033` | `0.6230` | `0.6066` | `0.5648` | `432` | `354` |
| `constraint_no_local_wrong_claim_anchor` | `0.5935` | `0.6957` | `0.6232` | `0.6812` | `0.6273` | `445` | `365` |
| `constraint_no_commitment_style` | `0.5916` | `0.8310` | `0.6901` | `0.6479` | `0.6283` | `500` | `408` |
| `constraint_no_style_constraints` | `0.5870` | `0.6986` | `0.6301` | `0.6986` | `0.6348` | `407` | `337` |
| `constraint_minimal_length_only` | `0.6011` | `0.8065` | `0.6613` | `0.7419` | `0.5439` | `483` | `372` |

---

## 5. 最关键发现

### 5.1 `constraint_no_commitment_style` 是本轮最稳候选

和 `candidate_structure_default` 相比，`constraint_no_commitment_style` 五项核心指标全部上涨：

| metric | candidate | no_commitment_style | delta |
|---|---:|---:|---:|
| `consistency` | `0.5878` | `0.5916` | `+0.0038` |
| `same_knowledge` | `0.7500` | `0.8310` | `+0.0810` |
| `same_locus` | `0.5882` | `0.6901` | `+0.1019` |
| `same_mechanism` | `0.5735` | `0.6479` | `+0.0744` |
| `error_realization` | `0.5965` | `0.6283` | `+0.0318` |

这说明：

> 当前 default constraints 里，对学生“应该多确定 / 多犹豫”的承诺风格控制太硬。

更简单地说：

> 模型不是不需要约束，而是不应该被强行压成某种固定承诺口吻。

所以当前最值得继续推进的 EEDI strong 候选主线是：

> `error_blueprint_mode = structure_only` + `constraint_profile = no_commitment_style`

---

### 5.2 `no_specific_error_realization` 提升 correctness 对齐，但牺牲错误外显

`constraint_no_specific_error_realization` 的 `consistency` 最高：

- `consistency = 0.6565`

但它的 `error_realization` 明显下降：

- `error_realization = 0.5648`

这说明：

> 强制具体错误外显确实会带来“过度犯错”的风险；去掉它后，模型更容易判断这一轮该不该错。

但代价也很清楚：

> 如果完全不要求具体错误外显，模型会更容易把错误藏回模糊回答里。

所以这个版本不适合作为默认最终版。它更适合回答一个诊断问题：

> 当前 consistency 的一部分损失，确实来自“具体错误外显约束”过硬。

---

### 5.3 `no_style_constraints` 能保住 error_realization，但不是整体最优

`constraint_no_style_constraints` 的 `error_realization = 0.6348`，接近原始 baseline 的 `0.6429`，也高于 `candidate_structure_default` 的 `0.5965`。

这说明：

> 表层 style constraints 中确实有一部分在压制错误自然外显。

但它的问题是：

- `consistency = 0.5870`，没有超过候选主线；
- `same_knowledge = 0.6986`，比候选主线下降；
- 它不是五项指标同时变好。

所以它也不适合作为默认主线，但说明后续可以继续把 style constraints 做得更轻。

---

### 5.4 `minimal_length_only` 不能作为最终版

`constraint_minimal_length_only` 的机制类指标很高：

- `same_mechanism = 0.7419`
- `same_locus = 0.6613`

但它的 `error_realization = 0.5439`，是本轮最低。

这说明：

> 只保留最小长度 / 禁止未来信息 / 禁止 tutor 化是不够的。

也就是说，`ConstraintBundle` 不是可以删掉的模块。  
真正的问题不是“要不要约束”，而是：

> 哪些约束要保留，哪些表层控制要放松。

---

## 6. 模块必要性判断

| 约束字段 / 约束组 | 当前判断 | 理由 |
|---|---|---|
| `ConstraintBundle` 整体 | 必须保留 | `minimal_length_only` 的 `error_realization` 明显下降，说明只靠底线约束不够 |
| `must_realize_specific_error` | 条件保留 | 有助于错误外显，但会伤 `consistency` |
| `must_anchor_to_local_wrong_claim` | 建议保留但不要过窄 | 去掉后 `error_realization` 上升，但 `same_knowledge` 下降 |
| `required_commitment_style` | 不应强控 | `no_commitment_style` 五项指标全涨，是本轮最清楚的优化点 |
| `style_constraints` | 需要轻量化 | 全去掉不稳定，但当前默认确实偏重 |
| `max_sentences` / 长度底线 | 必须保留 | 保证回复仍是学生 turn，而不是 tutor 式长解释 |

---

## 7. 是否要上 4334 全量

本轮建议：

> 只把 `constraint_no_commitment_style` 送到 4334 全量。

原因是：

- 它是唯一一个相对 `candidate_structure_default` 五项核心指标全部上涨的版本；
- 它没有像 `no_specific_error_realization` 那样牺牲 `error_realization`；
- 它没有像 `minimal_length_only` 那样让错误外显坍塌；
- 它的改动也最容易解释：不是删状态层，而是放松表层承诺风格控制。

暂不建议上全量的版本：

- `constraint_no_specific_error_realization`
  - consistency 最高，但 error realization 下降明显；
- `constraint_no_style_constraints`
  - error realization 高，但 consistency 没变好；
- `constraint_minimal_length_only`
  - error realization 太低；
- `constraint_no_local_wrong_claim_anchor`
  - 有提升，但不如 `no_commitment_style` 稳。

---

## 8. 当前 EEDI strong 主线建议

结合 block8 和 block9，当前建议把 EEDI strong 候选主线更新为：

> `error_blueprint_mode = structure_only`  
> `constraint_profile = no_commitment_style`

它对应的方法含义是：

1. 保留第三人称状态层；
2. 保留错误结构判断；
3. 不默认强依赖具体 `wrong_claim_seed`；
4. 不默认强依赖具体 `buggy_rule`；
5. 保留生成边界；
6. 但不要强控学生回复的承诺风格。

一句话概括：

> EEDI 的状态层和约束层都不能删，但默认约束不应该把学生回复压成固定的“确定 / 犹豫”口吻；下一版主线应采用结构化错误蓝图 + 放松承诺风格约束。

---

## 9. 下一步

下一步建议很明确：

1. 跑 `constraint_no_commitment_style` 的 4334 全量；
2. 和当前 full4334 strong baseline 比较五项核心指标；
3. 如果全量仍然保持五项不退，才把它写进 EEDI strong 最终源码主线；
4. 暂时不要继续无限拆 `ConstraintBundle`，因为 block9 已经抓到一个明确优化点。
