# B3 画像扰动：`shuffled_full` vs `full_persona`

## 1. 用途

判断 `full_persona` 里的细节是否真的被模型稳定使用。

如果把同一学业档内部的 persona 细节打乱，但保留每个学生自己的 `grade` 和 `academic_level` 不变，结果仍然几乎不变，就说明当前 full persona 的很多细节并没有被稳定读取。

## 2. 对照设置

- `P2 = full_persona`
  - 运行目录：`outputs/run_20260420_014128`
- `P3 = shuffled_full`
  - 运行目录：`outputs/root_cause/B3_shuffled_full/run_20260420_174733`
- 固定不变：
  - persona 文件：`data/personas_grade3_exact_20x4_seed42.jsonl`
  - 冻结题集：`outputs/run_20260420_014128/selected_questions.json`
  - 配置：`configs/run_local.json`
  - 模型：`qwen`
  - 方法链：`StudentModel -> ProblemRequirementProfile -> ItemResponseState -> ConstraintBundle -> Answer -> ViolationCheck -> Optional Retry`
  - 官方判分：`official_correctness_mode = rules_only`

本次唯一改动：

- `full_persona`：保留当前完整 persona 输入
- `shuffled_full`：保留每个学生自己的
  - `grade`
  - `academic_level`
- 但在同一 `academic_level` 内，把下面这三块整套错位交换：
  - `strong_subjects`
  - `weak_subjects`
  - `learning_profile_text`

说明：

- `P2` 是已冻结主基线，生成成功 `11997/12000`
- `P3` 本次正式 run 为 `11999/12000`
  - 唯一失败是一次 LLM 连接被远端重置
  - 不属于方法逻辑错误

## 3. 关键结果

### 3.1 总体指标

| 指标 | `full_persona` | `shuffled_full` | 判断 |
| --- | ---: | ---: | --- |
| overall accuracy | 0.7015 | 0.7062 | 极小波动 |
| overall accuracy gap vs real | 0.0300 | 0.0347 | `shuffled_full` 略差 |
| overall item Pearson | 0.3356 | 0.3371 | `shuffled_full` 略高 |
| overall item MAE | 0.2512 | 0.2456 | `shuffled_full` 略优 |
| 四档平均分 gap（mean abs gap） | 0.05545 | 0.05545 | 基本完全一样 |
| 单题四档严格单调题数 | 15 | 13 | `shuffled_full` 略差 |
| 跨档主流答案完全相同题数 | 106 | 101 | `shuffled_full` 略优 |

直接看这张表，最重要的不是谁赢一点，而是：

- 没有任何一项出现“shuffle 之后明显崩掉”
- 大多数差异都很小
- 有些指标 `shuffled_full` 甚至还略好一点

这说明 `full_persona` 里的细节并没有形成稳定、必要的有效信号。

### 3.2 四档整体表现

| 档位 | `full_persona` 预测准确率 | `shuffled_full` 预测准确率 | 真实准确率 |
| --- | ---: | ---: | ---: |
| high | 0.8362 | 0.8463 | 0.8515 |
| medium | 0.7760 | 0.7797 | 0.7306 |
| low | 0.5997 | 0.5989 | 0.6206 |
| poor | 0.5943 | 0.6000 | 0.4541 |

四档表现也支持同一个结论：

- `high`、`medium`、`low`、`poor` 的整体形状几乎没变
- 最明显的老问题依旧存在：
  - `poor` 仍然过强
  - `low/poor` 仍然没有真正拉开

如果 full persona 细节真的被稳定使用，`shuffled_full` 不应该还能保持这种几乎不变的分档形状。

### 3.3 分档 gap

| 档位 | `full_persona` gap | `shuffled_full` gap | 判断 |
| --- | ---: | ---: | --- |
| high | 0.0153 | 0.0051 | `shuffled_full` 略好 |
| medium | 0.0454 | 0.0491 | `shuffled_full` 略差 |
| low | 0.0209 | 0.0217 | 几乎一样 |
| poor | 0.1402 | 0.1459 | `shuffled_full` 略差 |

这里也没有出现“大幅恶化”。

特别是：

- `low` gap 几乎没变
- `poor` gap 本来就很差，shuffle 之后仍然很差

这更像是系统主要靠粗粒度信号在工作，而不是在认真读细画像。

## 4. 结论

本实验的正式判断是：

> `P3 = shuffled_full` 与 `P2 = full_persona` 基本等价。  
> 当前 `full_persona` 里的大量细节，没有被模型稳定利用；真正起主要作用的，更像是 `grade + academic_level` 再加上一点很粗的画像风格偏置。

这一步和前面的 `B1/B2` 合起来，信息已经更完整了：

- `B1`：`full_persona` 只比 `level_only` 好一点点
- `B2`：把 persona 收缩成数学相关子集，反而明显更好
- `B3`：把完整 persona 的细节在同档内打乱，结果却几乎不变

所以现在更像是：

- 完整 persona 里确实混了噪声
- 而且其中大量细节本身也没有被稳定读取
- 当前真正起作用的不是“完整人物画像”，而是很粗的层级信号和少量可见偏置

## 5. 对后续实验的含义

`B3` 跑完以后，画像层这边已经得到两个比较强的判断：

- `full_persona` 不是越完整越好
- `full_persona` 里的大量细节也没有被稳定利用

这意味着如果继续只在 persona 文本上打补丁，收益大概率很有限。

按实验计划，下一步应该进入：

- `C1 = 方法消融：direct vs state_single vs state_step`

也就是开始检查问题到底有多少来自方法链本身，而不再继续只盯画像层。

## 6. 反作弊说明

这次实验没有改 generation path，也没有把任何真实标签带入推理链。

- 只改了 persona 细节在同档内的对应关系
- `grade` 和 `academic_level` 保持不变
- 冻结题集保持不变
- 题目真实正确率、真实学生标签仍只用于离线评测
- 没有按题号特判
- 没有按目标方向后处理翻转答案
