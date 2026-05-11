# B2 画像增益：`math_salient` vs `full_persona`

## 1. 用途

判断当前 `full_persona` 是否被无关信息污染；如果只保留数学相关画像信息，是否会比完整 persona 更有效。

## 2. 对照设置

- `P2 = full_persona`
  - 运行目录：`outputs/run_20260420_014128`
- `P1 = math_salient`
  - 运行目录：`outputs/root_cause/B2_math_salient/run_20260420_142137`
- 固定不变：
  - persona 文件：`data/personas_grade3_exact_20x4_seed42.jsonl`
  - 冻结题集：`outputs/run_20260420_014128/selected_questions.json`
  - 配置：`configs/run_local.json`
  - 模型：`qwen`
  - 方法链：`StudentModel -> ProblemRequirementProfile -> ItemResponseState -> ConstraintBundle -> Answer -> ViolationCheck -> Optional Retry`
  - 官方判分：`official_correctness_mode = rules_only`

本次唯一改动：

- `full_persona`：保留当前完整 persona 输入
- `math_salient`：仍保留
  - `grade`
  - `academic_level`
  - `strong_subjects`
  - `weak_subjects`
  - `learning_profile_text` 中与数学学习、做题、自信、注意力、焦虑、任务坚持等直接相关的子句
- `math_salient` 的筛选是确定性关键词子句筛选
  - 不引入新 LLM
  - 不改方法链
  - 不引入真实标签

说明：

- `P2` 是已冻结主基线，生成成功 `11997/12000`
- `P1` 本次正式 run 为 `12000/12000` 全部成功

## 3. 关键结果

### 3.1 总体指标

| 指标 | `full_persona` | `math_salient` | 判断 |
| --- | ---: | ---: | --- |
| overall accuracy | 0.7015 | 0.6834 | `math_salient` 更接近真实整体准确率 `0.6715` |
| overall accuracy gap vs real | 0.0300 | 0.0119 | `math_salient` 明显更好 |
| overall item Pearson | 0.3356 | 0.3446 | `math_salient` 更好，提升 `0.0091` |
| overall item MAE | 0.2512 | 0.2433 | `math_salient` 更好，下降 `0.0079` |
| 四档平均分 gap（mean abs gap） | 0.0555 | 0.0507 | `math_salient` 更好 |
| 单题四档严格单调题数 | 15 | 24 | `math_salient` 明显更好 |
| 跨档主流答案完全相同题数 | 106 | 96 | `math_salient` 更好，但仍偏高 |

### 3.2 四档整体表现

| 档位 | `full_persona` 预测准确率 | `math_salient` 预测准确率 | 真实准确率 |
| --- | ---: | ---: | ---: |
| high | 0.8362 | 0.8360 | 0.8515 |
| medium | 0.7760 | 0.7720 | 0.7306 |
| low | 0.5997 | 0.5730 | 0.6206 |
| poor | 0.5943 | 0.5527 | 0.4541 |

直接观察：

- `high` 基本没变：`0.8362 -> 0.8360`
- `medium` 略降，但仍然偏高
- `low` 被压下来了，但这一步反而比 `full_persona` 离真实值更远
- `poor` 被明显压下来了：`0.5943 -> 0.5527`
  - 仍然偏强
  - 但比 `full_persona` 更接近真实 `0.4541`

这说明：

- `math_salient` 的主要收益，不是把四档全部一起做强
- 而是主要修正了 `full_persona` 对弱学生，尤其 `poor` 档的系统性抬高
- 但 `low/poor` 仍没有真正拉开，塌缩问题还在

### 3.3 结构诊断

| 指标 | `full_persona` | `math_salient` | 判断 |
| --- | ---: | ---: | --- |
| 严格单调题数 | 15 | 24 | `math_salient` 更好 |
| 严格单调占比 | 0.1000 | 0.1600 | `math_salient` 更好 |
| 跨档同主流答案题数 | 106 | 96 | `math_salient` 更好 |
| 跨档同主流答案占比 | 0.7067 | 0.6400 | `math_salient` 更好 |

但也要直接说明：

- `96 / 150` 题仍然跨档主流答案完全相同
- `24 / 150` 题才满足严格单调
- 所以 `math_salient` 只是明显改善，不是已经解决

## 4. 结论

本实验的正式判断是：

> `P1 = math_salient` 明显优于 `P2 = full_persona`。  
> 当前问题不是 persona 越多越好，而是 `full_persona` 的表示里混入了会干扰数学作答模拟的无关噪声。

这个结论比 `B1` 更强，因为两步连起来看，信息结构已经很清楚：

- `B1` 说明：把 persona 细节全砍掉，并不会明显更好
- `B2` 说明：把 persona 缩到“数学相关”的子集，反而比完整 persona 更好

所以当前更像是：

- persona 里不是完全没信号
- 但 `full_persona` 把有用信号和无关噪声混在一起了
- 结果是弱学生被整体抬高，跨档答案塌缩也更严重

## 5. 对后续实验的含义

`B2` 已经把“画像层是否有问题”这件事往前推进了一步：

- 画像层确实有问题
- 问题更像“表示被污染”，而不是“完全没有 persona 信号”

但 `B2` 还不能回答另一件事：

- 当前 `full_persona` 里剩下的细节，到底有没有被模型真正读取
- 还是只是以噪声形式存在

所以下一步必须做：

- `B3 = shuffled_full 对照`

如果 `shuffled_full ≈ full_persona`，就说明 `full_persona` 的大量细节其实根本没被稳定利用。

## 6. 反作弊说明

这次实验没有改 generation path，也没有把任何真实标签带入推理链。

- 只改了 persona 可见信息的保留范围
- `math_salient` 是对原始 persona 文本做确定性子句筛选
- 冻结题集保持不变
- 题目真实正确率、真实学生标签仍只用于离线评测
- 没有按题号特判
- 没有按目标方向后处理翻转答案
