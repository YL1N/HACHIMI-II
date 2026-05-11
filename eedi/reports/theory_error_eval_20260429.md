# Theory Error Eval

这份说明对应 `eedi/run_theory_error_eval.py`。

目标不是复现“同一个错答实例”，而是用有明确理论来源的三项指标，判断模型错误与真实学生错误在理论维度上是否一致：

- `knowledge_type_match_rate`
- `error_locus_match_rate`
- `error_mechanism_match_rate`

## 理论来源

### 1. Knowledge Type

使用 Anderson & Krathwohl (2001) 的知识维度：

- `factual`
- `conceptual`
- `procedural`
- `metacognitive`

在数学错误分析中的使用参考 Benecke & Kaiser (2023)。

### 2. Error Locus

使用 Newman Error Analysis：

- `reading`
- `comprehension`
- `transformation`
- `process_skills`
- `encoding`

这里按 White (2010) 的综述性定义执行，并要求按 Newman 的层级原则选择“最早发生的 breakdown”。

### 3. Error Mechanism

使用 Radatz (1979) 的五类错误成因：

- `language_difficulty`
- `spatial_information_difficulty`
- `deficient_prerequisites`
- `incorrect_associations`
- `irrelevant_rules`

## 运行方式

```powershell
python eedi/run_theory_error_eval.py ^
  --input_file eedi/outputs/<run_dir>/official_eval_input.csv
```

默认会读取 `eedi/configs/run_local.json` 里的 LLM 配置，并把输出写回 `official_eval_input.csv` 所在目录。

脚本会先过滤到 `gold` 在官方 `correctness` 标注中本来就是 `incorrect` 的样本，再做理论型 error judge。

## 输出文件

- `theory_error_judgments.jsonl`
- `theory_error_results.csv`
- `theory_error_summary.json`
- `theory_error_summary.md`

## 分母定义

三项指标统一使用：

- `gold_has_codable_math_error = true`

也就是：只有当真实学生这一轮包含可用上述理论框架编码的数学错误时，这条样本才进入分母。

如果 `gold` 没有足够证据形成理论编码，则不进入分母。
