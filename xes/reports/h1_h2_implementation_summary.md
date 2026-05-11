# H1/H2 实验实现总结

## 已完成的工作

### 1. 核心代码修改

#### 1.1 Prompt层 (`xes/src/prompts.py`)
- ✅ 新增 `PROBLEM_PROFILE_WITH_DIFFICULTY_ANALYSIS_PROMPT`
  - 包含 easy/medium/hard 的详细定义
  - 提供 9 个 few-shot 示例（每个难度3个）
  - 明确判断标准：认知复杂度、课程标准、先修知识、步骤数
- ✅ 新增 `ITEM_RESPONSE_STATE_WITH_DIFFICULTY_PROMPT`
  - 显式要求模型考虑题目难度和学生水平的匹配
  - 提供难度-状态匹配的示例指导

#### 1.2 数据结构层 (`xes/src/problem_profile.py`)
- ✅ `ProblemRequirementProfile` 新增字段：
  - `perceived_difficulty_for_target_grade: str | None` - H1使用
  - `perceived_difficulty_justification: str | None` - H1使用
  - `real_difficulty_band: str | None` - H2使用
- ✅ `build_problem_requirement_profile` 新增参数：
  - `target_grade: str | None` - 目标年级
  - `enable_difficulty_analysis: bool` - 是否启用难度分析
  - `real_difficulty_band: str | None` - 真实难度band（H2）

#### 1.3 状态推断层 (`xes/src/response_state.py`)
- ✅ `resolve_item_response_state` 新增参数：
  - `use_difficulty_aware_prompt: bool` - 是否使用难度感知prompt
- ✅ 自动检测是否有难度信息，选择合适的prompt
- ✅ 将难度信息传递给LLM进行状态推断

#### 1.4 实验流程层 (`xes/src/root_cause_workflow.py`)
- ✅ 新增 `run_h1_difficulty_analysis()` 函数
  - 完整的H1实验流程
  - 使用模型自主难度分析
  - 输出包含 `perceived_difficulty` 字段
- ✅ 新增 `run_h2_real_difficulty_label()` 函数
  - 完整的H2实验流程
  - 直接注入真实难度band
  - 输出包含 `real_difficulty_band` 和 `real_item_accuracy` 字段

### 2. 运行脚本

#### 2.1 主运行脚本 (`xes/run_h1_h2_experiments.py`)
- ✅ 支持运行 H1、H2 或两者
- ✅ 可配置参数：
  - `--experiment`: h1/h2/both
  - `--max_questions`: 题目数量
  - `--max_personas`: 学生数量
  - `--max_concurrency`: 并发数
  - `--config`: 配置文件路径
  - `--frozen_questions`: 冻结题目集路径
- ✅ 完整的错误处理和进度输出

#### 2.2 快速测试脚本 (`xes/smoke_test_h1_h2.py`)
- ✅ 最小样本快速验证（5题 × 4人）
- ✅ 用于验证代码正确性
- ✅ 在运行完整实验前先跑通

### 3. 文档

#### 3.1 实验计划文档 (`xes/reports/h1_h2_experiment_plan.md`)
- ✅ 实验背景和根因假设
- ✅ H1/H2详细设计说明
- ✅ 运行方式和参数配置
- ✅ 输出结构和评测指标
- ✅ 预期结果和后续分析
- ✅ 注意事项和实验状态跟踪

## 实验设计要点

### H1: 模型自主难度分析
**核心思路**：让模型基于few-shot示例，自己判断题目对目标年级的难度

**优点**：
- 不使用真实标签，符合反作弊原则
- 可解释性强
- 符合第三人称分析方法论

**关键实现**：
1. 在 `ProblemRequirementProfile` 阶段分析难度
2. Few-shot示例覆盖 easy/medium/hard 三档
3. 在 `ItemResponseState` 推断时显式使用难度信息

### H2: 真实难度标签注入
**核心思路**：直接使用真实学生统计计算的难度band

**警告**：
- ⚠️ 使用真实统计进入generation path
- ⚠️ 仅用于诊断，不是有效方法
- ⚠️ 目的是理解模型能力上限

**关键实现**：
1. 从 `item_stats` 计算难度band（hard<0.5, medium 0.5-0.75, easy>0.75）
2. 作为 `real_difficulty_band` 注入 `ProblemRequirementProfile`
3. 在状态推断时当作 `perceived_difficulty` 使用

## 运行指南

### 快速验证（推荐先运行）
```bash
cd xes
python smoke_test_h1_h2.py
```
预计耗时：5-10分钟（5题 × 4人 = 20次预测）

### 完整实验
```bash
cd xes
python run_h1_h2_experiments.py --experiment both
```
预计耗时：数小时（150题 × 80人 = 12000次预测）

### 自定义参数
```bash
cd xes
python run_h1_h2_experiments.py \
  --experiment h1 \
  --max_questions 50 \
  --max_personas 20 \
  --max_concurrency 8
```

## 输出和评测

### 关键指标
1. **题目级相关性**（主要关注）
   - `item_accuracy_pearson_vs_real_students`
   - `item_accuracy_spearman_vs_real_students`

2. **整体准确率**
   - `overall_accuracy`
   - `overall_accuracy_gap_vs_real_students`

3. **四档区分度**
   - `level_mean_accuracy`
   - `level_mean_gap_vs_real_students`

### 输出文件
- `predictions.jsonl`: 所有预测结果
- `failures.jsonl`: 失败记录
- `metrics.json`: 评测指标
- `resolved_config.json`: 运行配置

## 预期分析

### 场景1: H1显著改善
→ 模型有能力理解难度，问题在于缺乏显式提示
→ 可以考虑在最终方法中保留难度分析

### 场景2: H1不明显，H2显著改善
→ 模型的难度判断和真实群体不一致
→ 需要更好的难度校准方法

### 场景3: H1和H2都不明显
→ 难度感知不是主要瓶颈
→ 问题在其他环节

### 场景4: H2也不改善
→ 即使知道真实难度，仍无法对齐
→ 问题在模型根本能力边界或生成协议

## 代码质量保证

### 设计原则遵守
- ✅ 保持第三人称状态层
- ✅ 不破坏现有方法结构
- ✅ H1不违反反作弊原则
- ✅ H2明确标注为诊断性实验

### 向后兼容
- ✅ 所有新增参数都有默认值
- ✅ 不影响现有代码运行
- ✅ 可以独立运行H1/H2实验

### 错误处理
- ✅ 完整的异常捕获
- ✅ 失败记录到 failures.jsonl
- ✅ 不会因个别失败中断整个实验

## 下一步

1. **运行smoke test验证代码**
   ```bash
   cd xes
   python smoke_test_h1_h2.py
   ```

2. **运行完整实验**
   ```bash
   cd xes
   python run_h1_h2_experiments.py --experiment both
   ```

3. **分析结果**
   - 对比 baseline vs H1 vs H2 的题目级相关性
   - 分析难度判断准确性（H1）
   - 检查状态分布变化
   - 错误模式分析

4. **更新实验计划文档**
   - 填写实验状态表
   - 记录输出目录
   - 总结关键发现

## 技术细节

### Few-shot示例设计
- 每个难度档位3个示例
- 覆盖不同题型：计算、应用、推理
- 明确说明为什么是该难度

### 难度band计算（H2）
```python
def _get_difficulty_band(accuracy: float) -> str:
    if accuracy < 0.5:
        return "hard"
    elif accuracy <= 0.75:
        return "medium"
    else:
        return "easy"
```

### Prompt选择逻辑
```python
if use_difficulty_aware_prompt and (
    profile.perceived_difficulty_for_target_grade is not None
    or profile.real_difficulty_band is not None
):
    system_prompt = ITEM_RESPONSE_STATE_WITH_DIFFICULTY_PROMPT
else:
    system_prompt = ITEM_RESPONSE_STATE_PROMPT
```

## 文件清单

### 修改的文件
1. `xes/src/prompts.py` - 新增难度相关prompt
2. `xes/src/problem_profile.py` - 扩展数据结构和构建函数
3. `xes/src/response_state.py` - 支持难度感知状态推断
4. `xes/src/root_cause_workflow.py` - 新增H1/H2实验函数

### 新增的文件
1. `xes/run_h1_h2_experiments.py` - 主运行脚本
2. `xes/smoke_test_h1_h2.py` - 快速测试脚本
3. `xes/reports/h1_h2_experiment_plan.md` - 实验计划文档
4. `xes/reports/h1_h2_implementation_summary.md` - 本文档

## 总结

已完成H1和H2两个对照实验的完整实现，包括：
- ✅ 核心代码修改（4个文件）
- ✅ 运行脚本（2个）
- ✅ 完整文档（2个）
- ✅ 错误处理和日志
- ✅ 向后兼容性保证

代码已准备就绪，可以开始运行实验。建议先运行smoke test验证，然后再运行完整实验。
