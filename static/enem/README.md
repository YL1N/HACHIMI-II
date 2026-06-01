# ENEM 静态自然科学学生模拟

本目录是 ENEM 2024 的独立静态模拟实现。

它不复用 `static/xes` 的入口，也不 import XES 代码。  
方法层保持同一套元方法：

`history/calibration -> observed profile -> HACHIMI match -> StudentModel -> ProblemProfile -> StudentItemInteraction -> ItemResponseState -> ConstraintBundle -> StudentAnswer -> offline evaluation`

## 当前范围

- 数据集：ENEM 2024 microdata。
- 当前主学科：`CN`，即 Ciências da Natureza，自然科学。
- 题型：A/B/C/D/E 五选一客观题。
- history 定义：同一科内一部分题作为 calibration history。
- test 定义：剩余题作为预测目标。

ENEM 不是长期学习历史数据，所以这里的 history 不是时间序列学习记录，而是同一张考试中的可见校准题。

## 自然科学理论依据

ENEM-CN 字段不是从数学字段改名而来，而是按自然科学教育框架重新实例化：

- ENEM 官方自然科学能力矩阵：`H1-H30` 与 8 个能力区。
- NRC / NGSS 科学学习框架：科学实践、核心概念、跨领域联系。
- PISA science framework：解释现象、解释数据证据、评价科学探究。

因此自然科学学生能力对象使用 `ScienceTaskCapabilityProfile`，而不是 XES 的 `MathTaskCapabilityProfile`。

核心字段包括：

- `scientific_concept_recall`
- `phenomenon_explanation`
- `mechanism_reasoning`
- `data_evidence_interpretation`
- `model_representation_transfer`
- `scientific_inquiry_reasoning`
- `science_technology_society_reasoning`
- `quantitative_science_reasoning`
- `option_elimination`
- `hard_item_persistence`
- `guessing_tendency`
- `confidence_calibration`
- `format_discipline`

## 关键反作弊边界

生成路径禁止使用：

- test 题真实作答。
- test 题真实正确性。
- 官方正确答案。
- ENEM 总分。
- item IRT 难度或真实统计难度。

IRT `NU_PARAM_B` 只允许用于离线均衡切分 history/test，不进入 prompt。

## 运行 smoke test

```powershell
python static\enem\run_enem_static_benchmark.py --dry_run --max_students 4 --max_questions 2 --max_concurrency 2
```

## 运行多模态版本

`--build_page_images` 会先从官方 PDF 生成单题裁剪图清单。  
参数名保留 `page_images` 是为了少改运行入口，但现在传入模型的是每道题自己的裁剪图，不是整页图。

裁剪图是 ENEM 级缓存，不是 run 级临时文件。  
默认保存到：

`static/enem/cache/question_images/CN_1419_dpi150_bbox_column_crop_v1/`

同一套 PDF、学科、基准卷、DPI、裁剪算法版本不变时，后续运行会直接复用这里的图片和 `question_image_manifest.jsonl`。
如果缓存清单存在但题目数、DPI、裁剪版本或图片文件不一致，程序会直接报错，不做静默重建。

```powershell
python static\enem\run_enem_static_benchmark.py `
  --build_page_images `
  --max_students 20 `
  --max_questions 4 `
  --llm_base_url <BASE_URL> `
  --llm_model <MODEL> `
  --llm_api_key <API_KEY> `
  --response_format_json
```

裁剪方式：

- 用 `pdftotext -bbox` 读取 PDF 文字层里的 `QUESTÃO xx` 坐标。
- 常规双栏页面按左栏 / 右栏裁剪。
- 整页宽排页面按 full-width 裁剪，避免像第 135 题这种题干被截断。
- 清单里会记录 `crop_mode`、`crop_box`、`page_number`、`column`、`dpi`，方便审计。

当前审计要求：

- 44 道 CN 公共题必须全部生成裁剪图。
- 每个裁剪框必须包含本题题号。
- 每个裁剪框不能包含其他题题号。
