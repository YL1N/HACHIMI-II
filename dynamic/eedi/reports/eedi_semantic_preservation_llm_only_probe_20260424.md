# EEDI 纯 LLM 语义保持检查小测试
这次把语义保持检查从“规则 + LLM 混合”改成了“纯 LLM 裁判”。

原因很直接：
- 死规则虽然可审计，但跨题型、跨数据集迁移时很容易变成隐藏特判
- 我们后续是要部署到真实环境里，和教师模型交互 EEDI 之外的数学题
- 所以这层更适合做成通用语义裁判，而不是一堆细碎规则

运行目录：
- [semantic_preservation_llm_only_probe_20260424_20t](D:/Study/sii/MathStudent/eedi/outputs/semantic_preservation_llm_only_probe_20260424_20t)

## 结果
- `Correctness = 0.8182`
- `Errors = 0.1667`
- `Cosine Similarity = 0.1589`
- `ROUGE-L = 0.1517`

## 和前两版对比
### 1. 只有强化学生化表达层
- `Correctness = 0.7273`
- `Errors = 0.1667`
- `Cosine Similarity = 0.1644`
- `ROUGE-L = 0.1594`

### 2. 规则 + LLM 混合语义保持
- `Correctness = 0.7273`
- `Errors = 0.0000`
- `Cosine Similarity = 0.1643`
- `ROUGE-L = 0.1805`

### 3. 纯 LLM 语义保持
- `Correctness = 0.8182`
- `Errors = 0.1667`
- `Cosine Similarity = 0.1589`
- `ROUGE-L = 0.1517`

## 怎么理解
纯 LLM 版的特点是：
- 更宽松
- 不会像规则版那样强行回退很多改写
- 更适合作为通用架构的一部分

从这次 20 条看：
- `fallback = 0`
- `draft_turn != pred_turn` 的有 `9` 条

这说明它确实保留了学生化表达层的改写空间。

同时它把：
- `Correctness` 提回到了 `0.8182`
- `Errors` 也保持在 `0.1667`

但代价是：
- `Cosine Similarity` 和 `ROUGE-L` 没有混合版高

所以当前最合理的结论是：

> 如果目标是部署鲁棒性和跨任务迁移，纯 LLM 语义保持更适合作为主线。
> 如果目标只是当前这批样本上更强地卡住改写，混合版更硬，但迁移风险更高。

## 当前建议
站在你刚刚强调的“以后要部署到真实环境、面对 EEDI 之外题目”的要求上，
我建议主线保留纯 LLM 语义保持版本。

理由：
1. 它更符合通用架构，而不是数据集特化规则堆叠。
2. 它在这次小测试里没有伤到 `Correctness/Errors`。
3. 它仍然能作为“学生化表达不能乱改义”的通用保险丝。

## 下一步
如果继续推进，我建议：
1. 先用纯 LLM 语义保持版本做 92 条正式评测。
2. 如果正式结果稳定，再把它固定成当前主线。
