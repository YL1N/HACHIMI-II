# Hachimi 学生画像与 XES 数据交接

更新时间：2026-04-16（Asia/Shanghai）

## 1. 交接范围

本文档只覆盖两部分：

1. 当前项目里 `hachimi` 学生画像文件的存放、字段和使用方式。
2. 当前项目里 `XES3G5M` 静态数据的读取、过滤、冻结与运行入口。

不包含动态数据流程、不包含方法优劣评估、不包含新方案设计。

---

## 2. Hachimi 学生画像文件交接

### 2.1 文件位置与角色

- 主画像文件：`merged_students_10k.jsonl`（10,000 行）
- 兜底画像文件：`merged_students_250k.jsonl`（250,000 行）

在当前实现中：

- 画像仅作为条件输入（conditioning input）。
- 画像不作为评估真值（ground truth）。

对应配置见 `run_experiments.py` 的 `CONFIG["paths"]`：

- `personas = merged_students_10k.jsonl`
- `personas_fallback = merged_students_250k.jsonl`

### 2.2 原始 JSONL 记录字段（顶层）

当前文件顶层字段为：

- `id`
- `姓名`
- `年龄`
- `性别`
- `年级`
- `发展阶段`
- `代理名`
- `擅长科目`
- `薄弱科目`
- `学术水平`
- `人格`
- `价值观`
- `社交关系`
- `创造力`
- `心理健康`
- `_采样约束`

### 2.3 代码实际消费逻辑（run_experiments.py）

入口函数：

- `load_personas(...)`
- `normalize_persona_fields(...)`
- `ensure_static_persona_coverage(...)`

实际处理规则：

1. 逐行读取 JSONL。
2. 从 `年级` 解析 `grade_ordinal`，并映射到 `grade_stage`（`primary/middle/high`）。
3. 从 `学术水平` 解析：
   - 三档：`academic_level`（`high/medium/low`）
   - 四档：`academic_level_tier4`（`high/medium/low/poor`）
4. 保留并截断的画像文本侧字段主要包括：`人格/价值观/社交关系/心理健康`。
5. 过滤掉无法得到 `grade_stage` 或 `academic_level` 的画像行。
6. 如果静态分组覆盖不足（`stage x academic_level` 缺组），从 `merged_students_250k.jsonl` 补齐。

### 2.4 画像衍生产物（当前仓库已存在）

- `evaluation_sets/persona_cohorts_grade123_30x4.csv`（360 行）
- `evaluation_sets/persona_cohorts_grade123_20x4.csv`（240 行）
- `evaluation_sets/persona_cohorts_grade123_4x4.csv`（48 行）

这些文件是按 `grade(1/2/3) x tier4(high/medium/low/poor)` 采样后的静态评测画像分组。

---

## 3. XES 数据使用交接

### 3.1 原始输入文件

当前代码读取的 XES 源路径为：

- 题目元数据：`XES3G5M/metadata/questions.json`
- 训练作答序列：`XES3G5M/question_level/train_valid_sequences_quelevel.csv`
- 测试作答序列：`XES3G5M/question_level/test_quelevel.csv`

### 3.2 题目与作答解析流程（静态）

核心函数：

- `load_static_question_table()`
- `iter_static_response_events(split)`
- `compute_static_item_stats(split)`
- `prepare_static_dataset(split)`

关键规则：

1. 题目侧从 `questions.json` 读取：
   - `problem_id/question_text/options/answer/kc_routes/type`
2. 通过图片标记、图示词等规则构建 `has_image_marker` 与 `can_direct_text_to_llm`。
3. 作答侧从 question-level CSV 展开 `questions/responses/timestamps/selectmasks`。
4. 丢弃无效事件（如 `-1`、空值、非 0/1 响应）。
5. 统计题目真实正确率与作答量，并计算学生能力分层统计。
6. 仅保留可直接文本建模的题目（文本完整、有答案、可直接给 LLM、目标题型）。

### 3.3 当前项目中的两种静态使用模式

#### 模式 A：即时冻结（非固定评测）

- 调 `prepare_static_dataset(split)` 生成当前 split 的可用题集。
- 调 `freeze_static_dataset(...)` 输出到：
  - `processed/static_xes3g5m_text_ready_<split>_freeze.parquet`
  - `processed/static_xes3g5m_text_ready_<split>_freeze_manifest.json`

#### 模式 B：固定 1000 题基准（当前主用）

- 固定题集文件：`evaluation_sets/xes_test_1000.parquet`（1000 行）
- 采样分区：
  - `main_800`
  - `boundary_100`
  - `tail_100`

运行时，`load_fixed_question_set_with_tier4_stats(...)` 会：

1. 读取 `xes_test_1000.parquet`。
2. 基于当前 `split` 从原始作答日志重新计算 4 档学生统计（`high/medium/low/poor`）。
3. 丢弃题集里旧版本分档列后再合并，避免混用旧分档统计。

### 3.4 运行入口（仅静态）

当前脚本入口：`run_experiments.py`

固定基准常用参数：

```powershell
python run_experiments.py `
  --method our_state_conditioned_method `
  --max_static_samples 1 `
  --max_dynamic_samples 0 `
  --split test `
  --use_fixed_static_benchmark `
  --static_personas_per_group 30
```

说明：

- `--use_fixed_static_benchmark` 打开后，题集走 `evaluation_sets/xes_test_1000.parquet`。
- 同时会使用 `grade123 x tier4` 的画像 cohort 组合做整套静态评测。

---

## 4. 当前交接最小清单

如果新项目只做迁移，最低需要带走：

1. `merged_students_10k.jsonl`
2. `merged_students_250k.jsonl`（可选但建议保留，防覆盖不足）
3. `XES3G5M/metadata/questions.json`
4. `XES3G5M/question_level/train_valid_sequences_quelevel.csv`
5. `XES3G5M/question_level/test_quelevel.csv`
6. `evaluation_sets/xes_test_1000.parquet`
7. `evaluation_sets/persona_cohorts_grade123_30x4.csv`（若复用固定大盘）

