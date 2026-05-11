# B1 画像增益：`level_only` vs `full_persona`

## 1. 用途

判断当前 `full_persona` 是否真的明显优于只保留 `grade + academic_level` 的 `level_only`。

## 2. 对照设置

- `P2 = full_persona`
  - 运行目录：`outputs/run_20260420_014128`
- `P0 = level_only`
  - 运行目录：`outputs/root_cause/B1_level_only/run_20260420_123951`
- 固定不变：
  - persona 文件：`data/personas_grade3_exact_20x4_seed42.jsonl`
  - 冻结题集：`outputs/run_20260420_014128/selected_questions.json`
  - 配置：`configs/run_local.json`
  - 模型：`qwen`
  - 方法链：`StudentModel -> ProblemRequirementProfile -> ItemResponseState -> ConstraintBundle -> Answer -> ViolationCheck -> Optional Retry`
  - 官方判分：`official_correctness_mode = rules_only`

本次唯一改动：

- `full_persona`：使用当前运行链里的完整 persona 输入方式
- `level_only`：只保留 `grade` 和 `academic_level`
  - `strong_subjects = []`
  - `weak_subjects = []`
  - `learning_profile_text = ""`

说明：

- `P2` 是已冻结主基线，存在 `3/12000` 的生成失败，失败率 `0.025%`
- `P0` 本次正式 run 为 `12000/12000` 全部成功

## 3. 关键结果

### 3.1 总体指标

| 指标 | `full_persona` | `level_only` | 判断 |
| --- | ---: | ---: | --- |
| overall accuracy | 0.7015 | 0.6287 | `full_persona` 更高，但这不是本实验主指标 |
| overall item Pearson | 0.3356 | 0.3342 | `full_persona` 仅高 `0.0014`，差异极小 |
| overall item MAE | 0.2512 | 0.2534 | `full_persona` 仅优 `0.0022`，差异极小 |
| 四档平均分 gap（mean abs gap） | 0.0555 | 0.0553 | 几乎一样 |
| 单题四档严格单调题数 | 15 | 10 | `full_persona` 更好 |
| 跨档主流答案完全相同题数 | 106 | 78 | `full_persona` 更差，跨档同答更严重 |

### 3.2 四档整体表现

| 档位 | `full_persona` 预测准确率 | `level_only` 预测准确率 | 真实准确率 |
| --- | ---: | ---: | ---: |
| high | 0.8362 | 0.7997 | 0.8515 |
| medium | 0.7760 | 0.7357 | 0.7306 |
| low | 0.5997 | 0.4907 | 0.6206 |
| poor | 0.5943 | 0.4887 | 0.4541 |

直接观察：

- 两个条件下，`low` 和 `poor` 都仍然明显塌在一起
- `full_persona` 把 `low/poor` 一起抬高了，尤其 `poor` 仍偏强
- `level_only` 把 `low/poor` 一起压低了，但两档之间仍几乎没分开

### 3.3 分档 gap

| 档位 | `full_persona` gap | `level_only` gap | 判断 |
| --- | ---: | ---: | --- |
| high | 0.0153 | 0.0518 | `full_persona` 更好 |
| medium | 0.0454 | 0.0051 | `level_only` 更好 |
| low | 0.0209 | 0.1299 | `full_persona` 明显更好 |
| poor | 0.1402 | 0.0345 | `level_only` 明显更好 |

这说明：

- `full_persona` 与 `level_only` 并不是单边碾压关系
- `full_persona` 主要改善了 `low`
- `level_only` 主要改善了 `poor`
- 但两者都没有解决 `low/poor` 分不开的问题

### 3.4 四档 item Pearson

| 档位 | `full_persona` | `level_only` | 判断 |
| --- | ---: | ---: | --- |
| high | 0.3462 | 0.3760 | `level_only` 略高 |
| medium | 0.3383 | 0.2967 | `full_persona` 更好 |
| low | 0.2696 | 0.2499 | `full_persona` 更好 |
| poor | 0.3019 | 0.3186 | `level_only` 略高 |

这一项同样是混合结果，没有形成“full persona 全面更好”的证据。

## 4. 结论

结论按计划规则给：

- `full_persona` 相比 `level_only` 不是没有增益
  - 它在 overall item Pearson、overall item MAE、严格单调题数上都更好
- 但这个增益非常小
  - Pearson 只高 `0.0014`
  - MAE 只优 `0.0022`
  - 远远达不到“明显优于”的程度
- 同时，`full_persona` 反而让“跨档主流答案完全相同”的题更多
  - `106 > 78`
  - 说明它没有解决当前最显眼的跨档同答塌缩问题

因此，本实验的正式判断是：

> `P2 = full_persona` 没有明显优于 `P0 = level_only`。  
> 画像层不是完全没信号，但当前画像表示方式带来的收益非常有限，仍然是主要嫌疑之一。

## 5. 对后续实验的含义

这一步不能回答“到底是 persona 细节没被用上，还是 persona 里混入了噪声”。

所以下一步必须做：

- `B2 = math_salient vs full_persona`

如果 `math_salient > full_persona`，就更像是当前 `full_persona` 被无关信息污染了。

## 6. 反作弊说明

这次实验没有改 generation path，也没有把任何真实标签带入推理链。

- 只改了 persona 输入可见字段
- 题集使用冻结版 `selected_questions.json`
- 题目真实正确率、真实学生标签仍只用于离线评测
- 没有按题号特判
- 没有后处理翻转答案
