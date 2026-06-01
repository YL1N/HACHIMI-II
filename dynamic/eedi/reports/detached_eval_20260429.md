# Detached Eval

这份说明对应 `eedi/run_detached_eval.py`。

目标很简单：

- 不再依赖 `external/sim-student-eval` 的运行入口
- 在 `eedi/` 内独立完成 4 个指标
- 保留和官方一致的部分
- 把 “是否犯一样的错误” 改成更贴合“学生错得是不是同一种错”的版本

## 四个指标

### 1. Correctness

这部分复现官方 `sim-corr-errs` 里的 correctness judge。

- 还是同一个 LLM-as-a-judge 任务
- 还是同一个 system prompt
- 还是同一个输入结构：
  `Question + Conversation History + Ground-truth next student turn + Correctness + Candidate next student turn`

输出看：

- `official_correctness_match`
- 汇总里的 `correctness.match_rate`

### 2. Same Error

这部分不再沿用官方那个“数学上是否等价”的 `error-sim` 定义。

现在改成：

- 先判断 `gold` 这一轮是不是可编码的数学错误
- 再判断 `pred` 这一轮是不是可编码的数学错误
- 只有 `gold` 和 `pred` 都确实在犯可编码数学错误时，才进入“是不是同一种错”的比较集合

比较维度是 3 个理论维度：

- `knowledge_type`
- `error_locus`
- `error_mechanism`

主结果看：

- `same_error.same_error_rate`

支持性结果看：

- `same_error.error_realization_rate`
- `same_error.same_knowledge_type_rate`
- `same_error.same_error_locus_rate`
- `same_error.same_error_mechanism_rate`

其中：

- `error_realization_rate`
  表示真实学生这轮有可编码数学错误时，我们的模型有多大比例也真的生成了一个可编码数学错误
- `same_error_rate`
  表示在双方都真的犯错的集合里，三维标签是否同时一致

### 3. Cosine Similarity

这部分复现官方 `sim-text` 的余弦相似度。

- 文本嵌入走 Gitee 的 OpenAI-compatible embedding API
- 仍然对 `gt_turn` 和 `pred_turn` 做逐条点积

输出看：

- 每条记录的 `cosine_similarity`
- 汇总里的 `text_similarity.cosine_similarity_mean`

### 4. Semantic Similarity

这里复现的其实是官方 `sim-text` 里的 `ROUGE-L`。

也就是说：

- 这个项目里说的“语义相似度”，当前具体实现就是官方的 `ROUGE-L`
- 它不是再调用一个额外的 embedding judge
- 真正走 Gitee API 的只有余弦相似度那部分 embedding

输出看：

- 每条记录的 `rougeL`
- 汇总里的
  - `text_similarity.semantic_similarity_mean`
  - `text_similarity.rougeL_mean`

这两个值相同，只是前者是更贴近我们当前表述的别名。

## 运行方式

```powershell
python eedi/run_detached_eval.py ^
  --input_file eedi/outputs/<run_dir>/official_eval_input.csv
```

默认会从 `eedi/configs/run_local.json` 读：

- 本地 judge LLM 配置
- Gitee embedding 配置
- 并发和超时配置

## 输出文件

- `detached_eval_results.jsonl`
- `detached_eval_results.csv`
- `detached_eval_summary.json`
- `detached_eval_summary.md`

## 设计边界

这套 detached eval 只做评测，不进 generation path。

它不会把这些信息带回生成链路：

- 真实下一句学生回复
- correctness 标注
- theory error 标注结果
- 任何评测分数

所以这里没有未来信息泄露到生成阶段的问题。
