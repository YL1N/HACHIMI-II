# EEDI 当前 4 指标小结
## 这次做了什么
我们已经把 EEDI 的默认文本相似度评测固定为走在线 embedding 服务，而不是在本地加载 `Qwen3-Embedding-8B`。

当前默认配置是：
- embedding endpoint: `https://ai.gitee.com/v1`
- embedding model: `Qwen3-Embedding-8B`
- token: 优先从环境变量 `EMBEDDING_API_KEY` 读取

这样做的原因很直接：
- 论文里的 `cos-sim` 本来就是用 `Qwen3-Embedding-8B`
- 办公本本地加载 8B embedding 太慢
- 改成远程 `/v1/embeddings` 不改变指标定义，只改变计算位置

## 我们当前结果
本次结果来自：
- [official_eval_summary.md](D:/Study/sii/MathStudent/eedi/outputs/run_20260423_111159/official_eval_summary.md)

样本规模：
- `92` 个 turn

当前 4 个指标：
- `Correctness = 0.6863`
- `Errors = 0.3043`
- `Cosine Similarity = 0.1590`
- `ROUGE-L = 0.1594`

需要注意：
- `Correctness` 实际只评了 `51` 条
- `Errors` 实际只评了 `23` 条
- `Cosine Similarity` 和 `ROUGE-L` 评了全部 `92` 条

## 和 EEDI 论文 Table 1 的对比
论文里和我们当前最可比的是 prompting 方法：

`OCEAN (GPT 4.1)`
- Correctness: `0.6039`
- Errors: `0.0308`
- Cosine Similarity: `0.5739`
- ROUGE-L: `0.1772`

`Reasoning (GPT 5 Mini)`
- Correctness: `0.5870`
- Errors: `0.0088`
- Cosine Similarity: `0.5992`
- ROUGE-L: `0.2170`

`Oracle (GPT 4.1)`
- Correctness: `0.6755`
- Errors: `0.1872`
- Cosine Similarity: `0.6032`
- ROUGE-L: `0.2109`

我们的当前结果：
- Correctness 比论文这些 prompting 方法都高，甚至略高于 `Oracle`
- Errors 也高于论文里的 prompting 方法和 `Oracle`
- 但 `Cosine Similarity` 和 `ROUGE-L` 明显远低于论文

## 这说明什么
这说明我们当前方法已经能在“答对答错”这个粗层面上对上不少，但在“说得像不像真实学生”这个层面还差得很远。

更直白地说：
- 我们现在比较像是在猜学生这轮会不会答对
- 但还不像真实学生会怎么说、会用什么表达、会保留多少不完整和口语化痕迹

这和论文主结论是一致的：
- prompting 方法更容易在 correctness 上看起来不差
- 但在更细的行为和语言层面，通常不如专门训练过的方法

## 现在能下的结论
目前我们还不能说“超过论文”或者“已经达到论文水平”，原因有四个：
- 我们现在只跑了 `92` 条，不是论文完整测试集
- judge 配置和论文不完全一致
- 我们现在只对齐了 `4/7` 个指标
- 当前结果更像一次小切片诊断，不是正式最终成绩

## 三点说明
1. 改了哪个环节  
改的是 `sim-text` 的 embedding 计算路径，固定成远程 `gitee` embedding 服务。

2. 理论依据是什么  
论文的 `cos-sim` 本来就基于 `Qwen3-Embedding-8B`。远程调用同模型的 embedding 接口，不改变指标本身。

3. 如何避免 cheating  
只改评测计算方式，不改生成链，不把任何评测结果回灌到 student generation。
