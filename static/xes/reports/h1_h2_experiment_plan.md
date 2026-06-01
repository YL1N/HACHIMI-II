# H1/H2 题目难度感知实验计划

## 1. 实验背景

当前效果不佳的主要问题：**题目级别正确率和真实学生不对齐**。

### 根因假设

学生画像侧的学生年级和学生水平，模型可能有大概的认识，但是对于**题目的难度感知不足**：
- 当前只是有一个学生建模，然后让大模型按照学生状态去回答发过来的题目
- 大模型只知道学生努力去做题，没有明确意识题目难度
- 基于它的可用性预训练目标，倾向于把题目做出来

### 实验目的

测试两种对照方案，剖析模型对题目难度的感知能力：
1. **H1**: 让模型自己分析难度（few-shot引导）
2. **H2**: 直接传入真实难度标签（诊断性实验）

**重要说明**：这是根因分析实验，目的是剖析模型能力边界，不是最终方法。

## 2. 实验设计

### H1: 模型自主难度分析

**方案描述**：
- 在 `ProblemRequirementProfile` 阶段，让模型分析题目对目标年级的难度
- 使用 few-shot 示例引导模型理解 easy/medium/hard 的含义
- 在 `ItemResponseState` 推断时，显式使用这个难度判断

**关键修改**：
1. 新增 `PROBLEM_PROFILE_WITH_DIFFICULTY_ANALYSIS_PROMPT`
   - 包含 easy/medium/hard 的定义和 few-shot 示例
   - 要求模型输出 `perceived_difficulty_for_target_grade` 和理由
2. 新增 `ITEM_RESPONSE_STATE_WITH_DIFFICULTY_PROMPT`
   - 显式提示模型考虑题目难度和学生水平的匹配
3. `ProblemRequirementProfile` 新增字段：
   - `perceived_difficulty_for_target_grade: str | None`
   - `perceived_difficulty_justification: str | None`

**优点**：
- ✅ 不违反反作弊原则（没有使用真实标签）
- ✅ 符合当前方法论（第三人称分析）
- ✅ 可解释性强

**缺点**：
- ⚠️ 增加一次LLM调用
- ⚠️ 模型的难度判断可能和真实学生群体不一致

### H2: 真实难度标签注入

**方案描述**：
- 直接使用真实学生作答统计计算题目难度band（hard/medium/easy）
- 将难度band作为题目固有属性传入 `ProblemRequirementProfile`
- 在 `ItemResponseState` 推断时使用这个真实难度信息

**关键修改**：
1. `ProblemRequirementProfile` 新增字段：
   - `real_difficulty_band: str | None`
2. 从 `item_stats` 计算难度band：
   - hard: accuracy < 0.5
   - medium: 0.5 <= accuracy <= 0.75
   - easy: accuracy > 0.75
3. 在 `resolve_item_response_state` 时，将 `real_difficulty_band` 作为 `perceived_difficulty_for_target_grade` 使用

**警告**：
- ❌ 这使用了真实学生统计进入generation path
- ❌ 这是诊断性实验，**不是**有效的最终方法
- ✅ 但可以帮助我们理解：如果模型知道真实难度，能否改善题目级相关性

## 3. 实验配置

### 固定参数
- 目标年级：三年级
- 题目集：`DEFAULT_FROZEN_QUESTION_SET_PATH`
- 配置文件：`configs/run_local.json`
- 模型：qwen（从配置文件读取）

### 可调参数
- `max_questions`: 150（默认）
- `max_personas`: 80（默认）
- `max_concurrency`: 16（默认）
- `response_persona`: "first"
- `max_thinking_steps`: 12

### 难度band阈值（H2）
- `hard_max_accuracy`: 0.5
- `medium_max_accuracy`: 0.75

## 4. 运行方式

### 运行H1实验
```bash
cd xes
python run_h1_h2_experiments.py --experiment h1
```

### 运行H2实验
```bash
cd xes
python run_h1_h2_experiments.py --experiment h2
```

### 同时运行两个实验
```bash
cd xes
python run_h1_h2_experiments.py --experiment both
```

### 自定义参数
```bash
cd xes
python run_h1_h2_experiments.py \
  --experiment both \
  --max_questions 100 \
  --max_personas 40 \
  --max_concurrency 8
```

## 5. 输出结构

### H1输出目录
```
xes/outputs/root_cause/H1_difficulty_analysis/run_YYYYMMDD_HHMMSS/
├── predictions.jsonl          # 预测结果
├── failures.jsonl             # 失败记录
├── metrics.json               # 评测指标
└── resolved_config.json       # 运行配置
```

### H2输出目录
```
xes/outputs/root_cause/H2_real_difficulty_label/run_YYYYMMDD_HHMMSS/
├── predictions.jsonl          # 预测结果
├── failures.jsonl             # 失败记录
├── metrics.json               # 评测指标
└── resolved_config.json       # 运行配置
```

### predictions.jsonl字段

**H1特有字段**：
- `perceived_difficulty`: 模型分析的难度（easy/medium/hard）
- `perceived_difficulty_justification`: 难度判断理由

**H2特有字段**：
- `real_difficulty_band`: 真实难度band（easy/medium/hard）
- `real_item_accuracy`: 真实题目正确率

**共同字段**：
- `student_id`: 学生ID
- `question_id`: 题目ID
- `predicted_answer`: 预测答案
- `student_response`: 学生回复
- `response_state`: 推断的作答状态
- `is_correct`: 是否正确
- `gold_answers`: 标准答案

## 6. 评测指标

关注以下关键指标：

### 题目级相关性
- `item_accuracy_pearson_vs_real_students`: 题目级正确率Pearson相关系数
- `item_accuracy_spearman_vs_real_students`: 题目级正确率Spearman相关系数

### 整体准确率
- `overall_accuracy`: 整体正确率
- `overall_accuracy_gap_vs_real_students`: 与真实学生的整体准确率差距

### 四档区分度
- `level_mean_accuracy`: 各档位平均正确率
- `level_mean_gap_vs_real_students`: 各档位与真实学生的差距

## 7. 预期结果

### 如果H1显著改善
说明：
- 模型有能力理解题目难度
- 问题在于缺乏显式的难度提示
- 可以考虑在最终方法中保留难度分析环节

### 如果H1改善不明显，但H2显著改善
说明：
- 模型的难度判断和真实学生群体不一致
- 问题在于模型对"三年级难度"的理解偏差
- 需要更好的难度校准方法

### 如果H1和H2都改善不明显
说明：
- 题目难度感知不是主要瓶颈
- 问题可能在其他环节（学生建模、状态推断、生成约束等）

### 如果H2也不改善
说明：
- 即使知道真实难度，模型仍然无法对齐题目级正确率
- 问题可能在于模型的根本能力边界或生成协议

## 8. 后续分析

实验完成后，需要对比分析：

1. **Baseline vs H1 vs H2**
   - 题目级Pearson相关性变化
   - 整体准确率变化
   - 四档区分度变化

2. **难度判断准确性（H1）**
   - 模型判断的难度 vs 真实难度band
   - 哪些题目的难度判断偏差最大

3. **状态分布变化**
   - H1/H2中，不同难度题目的response_state分布
   - 是否出现了更合理的难度-状态匹配

4. **错误模式分析**
   - 哪些题目在H1/H2中仍然预测错误
   - 错误是否集中在特定难度band

## 9. 注意事项

1. **H2是诊断性实验**
   - 不能作为最终方法
   - 目的是理解模型能力上限
   - 结果仅用于根因分析

2. **运行时间估算**
   - H1需要额外的难度分析LLM调用
   - 预计比baseline慢约20-30%
   - 150题 × 80人 = 12000次预测，预计需要数小时

3. **失败处理**
   - 如果某些题目/学生组合失败，会记录在failures.jsonl
   - 不会中断整个实验
   - 最终指标基于成功的预测

4. **并发控制**
   - `max_concurrency`控制并发LLM调用数
   - 根据API限流调整
   - 建议不超过16

## 10. 实验状态

| ID | 实验名 | 状态 | 输出目录 | 结果摘要 |
| --- | --- | --- | --- | --- |
| H1 | 模型自主难度分析 | 未完成 | - | - |
| H2 | 真实难度标签注入 | 未完成 | - | - |

## 11. 更新日志

- 2026-04-24: 创建H1/H2实验计划和实现
