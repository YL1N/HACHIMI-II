# 根因归因实验计划

## 1. 用途

这份文档只做一件事：

- 追踪“效果不好到底是画像不对、当前大模型能力不够、还是方法不对”的归因实验

后续每次运行正式诊断实验，都必须同步更新本文件。

## 2. 状态规则

- 状态字段只允许两种值：`已完成` / `未完成`
- 只有实验真正跑完、结果落盘、并完成结果摘要后，才能改成 `已完成`
- 跑到一半、中断、结果无效，都保持 `未完成`
- 每次更新本文件时，必须同步更新：
  - `当前执行位置`
  - `下一步`
  - 对应实验的 `状态`
  - 对应实验的 `输出目录`
  - 对应实验的 `结果摘要`

## 3. 当前执行位置

- 当前执行位置：`A1 已冻结；B1/B2/B3/C1/D1/D2/E1/F1/G1 已完成；正式根因归因实验全部完成`
- 当前参考基线：
  - `outputs/run_20260420_014128`
  - `configs/run_local.json`
  - `outputs/run_20260420_014128/selected_questions.json`
- 当前已知问题：
  - 低状态学生仍然过强
  - 大量题目跨档主流答案相同
  - item 相关性仍不够高
  - 低档画像内部信号有模板化塌缩
  - `B2` 表明 `math_salient` 明显优于 `full_persona`，当前完整 persona 表示存在无关噪声污染
  - `B3` 表明 `shuffled_full ≈ full_persona`，完整 persona 里的大量细节没有被稳定利用
- 下一步：`全部正式根因归因实验已完成`

## 4. 冻结约定

在本计划的正式诊断实验中，默认冻结以下条件；若后续修改，必须在本文件记录：

- 目标年级：`三年级`
- persona 文件：`data/personas_grade3_exact_20x4_seed42.jsonl`
- 题集基线：`outputs/run_20260420_014128/selected_questions.json`
- 参考配置：`configs/run_local.json`
- 参考模型：`qwen`
- 参考基线 run：`outputs/run_20260420_014128`

说明：

- `R0` 仅表示参考基线已归档，不代表根因实验已经完成
- `A1` 完成后，评测器版本才算正式冻结；后续所有对照实验都以 `A1` 冻结版为准

## 5. 实验总表

| ID | 实验名 | 主要回答的问题 | 状态 | 输出目录 | 结果摘要 |
| --- | --- | --- | --- | --- | --- |
| R0 | 参考基线归档 | 当前已有哪一版主基线可作为归因起点 | 已完成 | `outputs/run_20260420_014128` | 当前平衡版基线已归档，后续所有归因实验以它为参考点 |
| A1 | 评测校准 | 当前判分是否足够可信，是否会冤枉模型 | 已完成 | `outputs/run_20260420_014128` | 基于基线预测结果、答案格式审计和人工确认，当前 `rules_only` 判分已足够可信，可正式冻结 |
| B1 | 画像增益：`level_only` vs `full_persona` | full persona 是否比只给年级和学业水平更有效 | 已完成 | `outputs/root_cause/B1_level_only/run_20260420_123951` | `full_persona` 在 Pearson/MAE/严格单调上仅小幅优于 `level_only`，但不构成明显优势；画像层仍是主要嫌疑之一 |
| B2 | 画像增益：`math_salient` vs `full_persona` | 数学相关字段是否比 full persona 更有效 | 已完成 | `outputs/root_cause/B2_math_salient/run_20260420_142137` | `math_salient` 在 Pearson/MAE、整体 gap、四档 mean gap、严格单调题数上均优于 `full_persona`；说明当前 full persona 存在噪声污染，但 `low/poor` 仍未真正拉开 |
| B3 | 画像扰动：`shuffled_full` 对照 | full persona 里的细节是否真的被模型使用 | 已完成 | `outputs/root_cause/B3_shuffled_full/run_20260420_174733` | `shuffled_full` 与 `full_persona` 基本等价，没有出现明显退化；说明完整 persona 里的大量细节没有被稳定利用，画像层有效信号主要仍是粗粒度的` |
| C1 | 方法消融：`direct` vs `state_single` vs `state_step` | 问题主要在方法链路的哪一段 | 已完成 | `direct=outputs/root_cause/C1_direct/run_20260420_225055; state_single=outputs/root_cause/C1_state_single/run_20260420_225125; state_step=outputs/root_cause/C1_state_step/run_20260420_225213` | direct、state_single、state_step 的对比表明问题不只在是否有状态层，还要看多步协议是否进一步拉低结构指标 |
| D1 | 强制状态服从：`simple_forced_state` | 当前模型能否在最简单条件下服从状态差异 | 已完成 | `outputs/root_cause/D1_simple_forced_state/run_20260421_103243` | 简单强制状态仍无法稳定拉开四档：`guessable≈partial`，仅 `1/150` 题严格递降，说明模型边界本身已是明显主因之一 |
| D2 | 强制状态服从：`full_forced_state` | 当前完整生成协议是否破坏了状态服从 | 已完成 | `outputs/root_cause/D2_full_forced_state/run_20260421_105905` | `D2` 在整体均值上反而能把四档排开，但仍压不住低状态过强，且跨状态主流答案相同题数更高，说明方法层不是首要主因 |
| E1 | 反事实敏感性测试 | persona 某个关键因素变化后，状态和答案是否随之变化 | 已完成 | `outputs/root_cause/E1_counterfactual_sensitivity/run_20260421_120742` | persona 不是整体失效，而是选择性有效：`math_subject_strength/efficacy` 能明显改状态，`srl_fragility/engagement_style` 对状态影响很弱 |
| F1 | 稳定性测试 | 同输入重复运行时，模型是否稳定 | 已完成 | `outputs/root_cause/F1_stability/run_20260421_131620` | 状态层相对稳定，但答案生成高波动：`state_change_rate=0.0438`，`answer_change_rate=0.4938`，说明第二层问题还包含明显的作答不稳定性 |
| G1 | 最终归因报告 | 三层问题谁是主因，谁是次因 | 已完成 | `reports/g1_root_cause_final_report_20260421.md` | 主因是第二层模型边界与作答稳定性，次因是第一层 persona 读取不均衡，第三层方法协议问题排在其后 |

## 6. 各实验设计

### R0 参考基线归档

- 目的：
  - 记录当前主基线
  - 作为后续所有归因实验的比较起点
- 已归档资产：
  - `outputs/run_20260420_014128`
  - `configs/run_local.json`
  - `outputs/run_20260420_014128/metrics.json`
  - `outputs/run_20260420_014128/selected_questions.json`
- 当前主结论：
  - 不是纯随机乱猜
  - 但离“真实学生题目级模拟”还有明显距离
  - 低状态过强、跨档同答案过多，是当前最明显的问题

### A1 评测校准

- 目标：
  - 确认判分器是否足够可信
- 设计：
  - 从当前基线中抽取一批规则判分样本
  - 重点人工复核：
    - 多空题
    - 多答案题
    - 选项题
    - 格式混乱但语义正确的题
  - 统计误判率和误判类型
- 固定条件：
  - 使用当前基线 run 的预测结果
  - 不改 generation
- 关键指标：
  - 误判率
  - 误判类型分布
- 结论规则：
  - 如果误判率高，先修评测，再做后续归因实验
  - 如果误判率低，则冻结评测器版本
- 实际使用资产：
  - `outputs/run_20260420_014128/predictions.jsonl`
  - `outputs/run_20260420_014128/selected_question_answer_format_audit.json`
  - `reports/xes3g5m_answer_format_audit_20260418.md`
- 实际关键结论：
  - 当前冻结题集 `150` 题的答案格式审计中，没有落入“必须靠官方 LLM 复核”的模糊 gold case
  - 结合人工复核结论，当前 `official_correctness_mode = rules_only` 可正式冻结
  - 后续归因实验不再优先怀疑评测器，先看 persona / method / model boundary

### B1 画像增益：`level_only` vs `full_persona`

- 目标：
  - 判断 full persona 是否真的比只给 `grade + academic_level` 更有效
- 设计：
  - 同一模型
  - 同一题集
  - 同一方法
  - 只改 persona 输入
- 条件：
  - `P0 = level_only`
  - `P2 = full_persona`
- 关键指标：
  - overall item Pearson
  - overall item MAE
  - 四档 item Pearson
  - 四档平均分 gap
  - 单题四档严格单调题数
  - 跨档主流答案完全相同的题数
- 结论规则：
  - 若 `P2` 不明显优于 `P0`，则画像层问题较大
- 实际运行配置：
  - `P2 = full_persona`
    - `outputs/run_20260420_014128`
  - `P0 = level_only`
    - `outputs/root_cause/B1_level_only/run_20260420_123951`
  - 冻结题集：
    - `outputs/run_20260420_014128/selected_questions.json`
  - 结果报告：
    - `reports/b1_level_only_vs_full_persona_20260420.md`
- 实际关键结论：
  - `full_persona` 相比 `level_only` 的 overall item Pearson 只高 `0.0014`，overall item MAE 只优 `0.0022`
  - `full_persona` 的严格单调题数更高：`15 > 10`
  - 但 `full_persona` 的跨档主流答案完全相同题数反而更高：`106 > 78`
  - 结论：`full_persona` 有信号，但没有明显优于 `level_only`；画像层仍是主要嫌疑之一，继续做 `B2`

### B2 画像增益：`math_salient` vs `full_persona`

- 目标：
  - 判断 full persona 是否被无关信息污染
- 设计：
  - `P1 = math_salient`
  - `P2 = full_persona`
- 条件：
  - `math_salient` 仅保留和数学最直接相关的画像字段
- 关键指标：
  - 同 `B1`
- 结论规则：
  - 若 `P1 > P2`，说明 full persona 不是越多越好，而是当前表示方式有噪声
- 实际运行配置：
  - `P2 = full_persona`
    - `outputs/run_20260420_014128`
  - `P1 = math_salient`
    - `outputs/root_cause/B2_math_salient/run_20260420_142137`
  - 冻结题集：
    - `outputs/run_20260420_014128/selected_questions.json`
  - 结果报告：
    - `reports/b2_math_salient_vs_full_persona_20260420.md`
- 实际关键结论：
  - `math_salient` 的 overall item Pearson 从 `0.3356` 提升到 `0.3446`，overall item MAE 从 `0.2512` 降到 `0.2433`
  - 整体准确率 gap 从 `0.0300` 降到 `0.0119`，四档平均分 gap 从 `0.0555` 降到 `0.0507`
  - 严格单调题数从 `15` 升到 `24`，跨档主流答案完全相同题数从 `106` 降到 `96`
  - `math_salient` 基本不伤 `high` 档，但明显压低了过强的 `poor` 档；不过 `low/poor` 仍没有真正拉开
  - 结论：当前 persona 不是完全没信号，而是 `full_persona` 的表示方式掺入了会干扰数学作答模拟的无关噪声；下一步继续做 `B3`

### B3 画像扰动：`shuffled_full` 对照

- 目标：
  - 判断 full persona 的细节是否真的被模型使用
- 设计：
  - 保持 `grade` 和 `academic_level` 不变
  - 在同档内部打乱其他 persona 字段
- 条件：
  - `P2 = full_persona`
  - `P3 = shuffled_full`
- 关键指标：
  - 同 `B1`
- 结论规则：
  - 若 `P2 ≈ P3`，说明画像细节几乎没被真正利用
- 实际运行配置：
  - `P2 = full_persona`
    - `outputs/run_20260420_014128`
  - `P3 = shuffled_full`
    - `outputs/root_cause/B3_shuffled_full/run_20260420_174733`
  - 冻结题集：
    - `outputs/run_20260420_014128/selected_questions.json`
  - 结果报告：
    - `reports/b3_shuffled_full_vs_full_persona_20260420.md`
- 实际关键结论：
  - `shuffled_full` 的 overall item Pearson 为 `0.3371`，与 `full_persona` 的 `0.3356` 基本等价；overall item MAE 为 `0.2456`，也只比 `full_persona` 的 `0.2512` 小幅波动
  - 整体准确率 gap 为 `0.0347`，略差于 `full_persona` 的 `0.0300`；但四档平均分 gap 几乎完全一样：`0.05545 ≈ 0.05545`
  - 严格单调题数从 `15` 降到 `13`，跨档主流答案完全相同题数从 `106` 降到 `101`，仍然只是很小波动
  - `poor` 档依然显著过强，`low/poor` 依然没有真正拉开；shuffle 后没有出现明显退化
  - 结论：`shuffled_full ≈ full_persona`，说明完整 persona 里的大量细节没有被模型稳定利用；下一步转入 `C1`

### C1 方法消融：`direct` vs `state_single` vs `state_step`

- 目标：
  - 判断问题主要在方法链路的哪一段
- 设计：
  - 固定同一 persona 条件
  - 只改方法
- 条件：
  - `M0 = persona -> direct answer`
  - `M1 = persona -> state -> single final answer`
  - `M2 = persona -> state -> step-by-step`
- 关键指标：
  - 同 `B1`
  - 额外记录 failure rate
- 结论规则：
  - 若 `M0 >= M1/M2`，说明方法在帮倒忙
  - 若 `M1 > M0` 但 `M2 < M1`，说明 step-by-step 当前实现有问题

<!-- AUTO-C1-DETAILS-START -->
- 实际运行配置：
  - direct run：outputs/root_cause/C1_direct/run_20260420_225055
  - state_single run：outputs/root_cause/C1_state_single/run_20260420_225125
  - state_step run：outputs/root_cause/C1_state_step/run_20260420_225213
  - 固定 persona = full_persona
  - 固定题集 = outputs/run_20260420_014128/selected_questions.json
- 实际关键结论：
  - direct、state_single、state_step 的对比表明问题不只在是否有状态层，还要看多步协议是否进一步拉低结构指标
  - direct item Pearson = 0.3102
  - state_single item Pearson = 0.3195
  - state_step item Pearson = 0.3508
  - direct strict_monotonic = 0
  - state_single strict_monotonic = 24
  - state_step strict_monotonic = 16
<!-- AUTO-C1-DETAILS-END -->

### D1 强制状态服从：`simple_forced_state`

- 目标：
  - 判断当前模型在最简单条件下，能否服从状态差异
- 设计：
  - 跳过 persona 和状态推断
  - 直接喂四种固定状态：
    - `mastered`
    - `partial`
    - `guessable`
    - `unreachable`
- 关键指标：
  - 四状态正确率是否严格下降
  - `guessable/unreachable` 是否仍大量答对
  - 四状态主流答案差异是否明显
- 结论规则：
  - 若简单强制状态都压不住，第二层问题嫌疑很大
- 实际运行配置：
  - `run = outputs/root_cause/D1_simple_forced_state/run_20260421_103243`
  - 固定题集：`outputs/run_20260420_014128/selected_questions.json`
  - forced states：`mastered / partial / guessable / unreachable`
  - `samples_per_state = 20`
- 实际关键结论：
  - 四状态准确率：`mastered=0.6229`，`partial=0.5450`，`guessable=0.5504`，`unreachable=0.4164`
  - 四状态没有严格下降，且 `guessable` 略高于 `partial`
  - `strict_state_descending_item_count = 1`，说明真正能按四档稳定分开的题几乎没有
  - `same_dominant_answer_all_states_count = 47`，说明大量题目在不同状态下主流答案仍然不变
  - 结论：简单强制状态都压不住，第二层问题，也就是当前模型边界本身，已经是明显主因之一；下一步继续看 `D2` 是否还会被完整协议进一步放大

### D2 强制状态服从：`full_forced_state`

- 目标：
  - 判断完整 generation 协议是否破坏了状态服从
- 设计：
  - 保留完整 generation prompt 和 constraint bundle
  - 但状态不再让模型自己推断，而是直接喂固定状态
- 关键指标：
  - 同 `D1`
- 结论规则：
  - 若 `D1` 能分开、`D2` 分不开，问题更偏方法层
- 实际运行配置：
  - `run = outputs/root_cause/D2_full_forced_state/run_20260421_105905`
  - `D1 reference = outputs/root_cause/D1_simple_forced_state/run_20260421_103243`
  - 固定题集：`outputs/run_20260420_014128/selected_questions.json`
  - forced states：`mastered / partial / guessable / unreachable`
  - `samples_per_state = 20`
- 实际关键结论：
  - `D2` 四状态准确率为：`mastered=0.8732`，`partial=0.8040`，`guessable=0.6607`，`unreachable=0.5267`
  - `D1` 整体不满足严格递降，但 `D2` 整体满足严格递降，说明完整协议没有简单破坏状态服从
  - `strict_state_descending_item_count` 从 `1` 升到 `7`，但绝对值仍然很低，题目级状态服从仍然弱
  - `same_dominant_answer_all_states_count` 从 `47` 升到 `77`，说明完整协议可能进一步压缩跨状态答案分化
  - 结论：方法层不是首要主因；当前更大的问题仍是第二层模型边界，尤其最低状态依旧过强

### E1 反事实敏感性测试

- 目标：
  - 判断 persona 的具体关键因素是否真的能改变状态和答案
- 设计：
  - 构造只改一个关键因素的成对 persona
  - 其他尽量保持不变
- 建议对照组：
  - `math strong` vs `math weak`
  - `high efficacy` vs `low efficacy`
  - `low srl_fragility` vs `high srl_fragility`
  - `Constructive` vs `Passive`
- 关键指标：
  - `persona -> state` 的变化幅度
  - `state -> answer` 的变化幅度
- 结论规则：
  - persona 改了但 state 不变：画像或模型读取有问题
  - state 变了但 answer 不变：方法层有问题
- 实际运行配置：
  - `run = outputs/root_cause/E1_counterfactual_sensitivity/run_20260421_120742`
  - factors：`math_subject_strength / efficacy / srl_fragility / engagement_style`
  - `max_questions = 20`
  - `repeats_per_side = 5`
- 实际关键结论：
  - `math_subject_strength` 的 `state_change_rate = 1.0000`，`efficacy = 0.8600`，说明这两类画像信号能明显进入状态层
  - `srl_fragility = 0.1300`，`engagement_style = 0.2200`，说明抽象学习特质对状态层影响很弱
  - 四个因素的平均 `mean_state_change_rate = 0.5525`，平均 `mean_answer_change_rate = 0.5300`
  - persona 不是整体失效，而是“选择性有效”：有些因素能明显改状态，有些几乎进不去状态层
  - 结论：第一层画像问题仍在，但更像次因；第二层模型边界仍更像主因

### F1 稳定性测试

- 目标：
  - 判断同输入重复运行时，模型是否稳定
- 设计：
  - 同一个输入重复跑 `3` 到 `5` 次
- 关键指标：
  - `response_state` 变化率
  - `predicted_answer` 变化率
  - `is_correct` 变化率
- 结论规则：
  - 若同输入高波动，第二层问题更重
  - 若同输入稳定但整体差，问题更偏画像或方法
- 实际运行配置：
  - `run = outputs/root_cause/F1_stability/run_20260421_131620`
  - personas：`8` 个分层抽样真实 persona
  - `max_questions = 20`
  - `repeats = 3`
  - method：`state_step`
- 实际关键结论：
  - `response_state_change_rate = 0.0438`，说明状态层本身相对稳定
  - `predicted_answer_change_rate = 0.4938`，接近一半任务在重复运行时答案会变
  - `is_correct_change_rate = 0.1813`，这种波动会实质影响最终对错
  - 结论：第二层问题不只是能力边界，还包括明显的作答不稳定性；但高波动主要出现在 `state -> answer`，不在 `persona -> state`

### G1 最终归因报告

- 目标：
  - 汇总前面所有实验，给出三层归因结论
- 输出必须明确回答：
  - 第一层：画像问题有多大
  - 第二层：当前这代模型能力边界有多大
  - 第三层：方法问题有多大
  - 三者的主次顺序
- 最终结论格式：
  - `主因`
  - `次因`
  - `可修复项`
  - `当前模型时代限制`
- 实际运行配置：
  - 汇总报告：`reports/g1_root_cause_final_report_20260421.md`
  - 依赖实验：`C1 / D1 / D2 / E1 / F1`
- 实际关键结论：
  - `主因`：第二层模型边界与作答稳定性问题
  - `次因`：第一层 persona 信号读取不均衡
  - `再次因`：第三层方法协议没有把状态差异充分落实到题目级答案分化
  - `可修复项`：收缩 persona、重写抽象特质表达、重点优化 `state -> answer`
  - `当前模型时代限制`：最简单强制状态下仍难稳定服从细粒度学生边界，且最终答案高波动

## 7. 推荐执行顺序

正式执行顺序固定为：

1. `A1 评测校准`
2. `B1 画像增益：level_only vs full_persona`
3. `B2 画像增益：math_salient vs full_persona`
4. `B3 画像扰动：shuffled_full`
5. `C1 方法消融`
6. `D1 simple_forced_state`
7. `D2 full_forced_state`
8. `E1 反事实敏感性测试`
9. `F1 稳定性测试`
10. `G1 最终归因报告`

如果中途发现：

- `A1` 评测不可靠

则后续实验全部暂停，先修评测。

## 8. 每次更新时必须修改的地方

后续每次你让我跑实验时，必须同步修改本文件中的以下内容：

1. `当前执行位置`
2. `下一步`
3. 对应实验在总表中的：
   - `状态`
   - `输出目录`
   - `结果摘要`
4. 如有必要，补充该实验小节中的：
   - 实际运行配置
   - 实际关键结论

## 9. 更新日志

- `2026-04-20`
  - 建立正式根因归因实验计划文档
  - 归档当前参考基线 `R0`
  - 完成 `A1`：确认当前 `rules_only` 判分足够可信并冻结
  - 完成 `B1`：`full_persona` 对 `level_only` 只有很小增益，不构成明显优势
  - 完成 `B2`：`math_salient` 明显优于 `full_persona`，说明当前完整 persona 表示存在无关噪声污染
  - 完成 `B3`：`shuffled_full` 与 `full_persona` 基本等价，说明完整 persona 里的大量细节没有被稳定利用
- `2026-04-21`
  - 完成 `C1`：状态层本身有价值，但多步协议是否继续伤害结构指标还需继续拆分
  - 完成 `D1`：简单强制状态仍无法稳定拉开四档，第二层模型边界问题已被明显暴露
  - 完成 `D2`：完整协议没有简单破坏状态服从，但也没有解决低状态过强和题目级答案趋同
  - 完成 `E1`：persona 信号是选择性有效，不是整体失效；画像问题存在，但更像次因
  - 完成 `F1`：状态层相对稳定，但最终作答层高波动，第二层问题还包含明显的不稳定性
  - 完成 `G1`：正式给出三层归因排序，确认第二层为主因、第一层为次因、第三层排在其后
