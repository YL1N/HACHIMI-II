# EEDI 论文四指标目标整理
这份表只整理我们当前已经跑通的 4 个指标：
- `Correctness`
- `Errors`
- `Cosine Similarity`
- `ROUGE-L`
这 4 个指标都来自论文 Table 1：
- 论文：`Simulated Students in Tutoring Dialogues: Substance or Illusion?`
- 本地摘录源：[tmp_arxiv_eedi.html](D:/Study/sii/MathStudent/tmp_arxiv_eedi.html)
## 四个指标各自代表什么
### 1. Correctness
它看的是：
- 模拟学生这一轮回答，对前一轮 tutor 提的问题来说，答得对不对。
怎么记分：
- 如果真实学生这一轮是可判定对错的，那么模拟学生和真实学生在“对/错”上是否一致。
- 一致记 `1`，不一致记 `0`。
- 如果这一轮本来就不是数学作答，而是闲聊、确认、寒暄之类，就不计入这个指标。
怎么理解：
- 这个指标只看“答对还是答错”。
- 它不看“错得像不像真实学生”。
- 也不太看“说话风格像不像真实学生”。
### 2. Errors
它看的是：
- 当真实学生这一轮答错时，模拟学生是不是犯了同一种错。
怎么记分：
- 只有真实学生本轮错误时才评。
- 如果模拟学生也是错，而且错法和真实学生本质上一样，记 `1`。
- 否则记 `0`。
怎么理解：
- 这是比 `Correctness` 更细一层的指标。
- `Correctness` 只看“都错了没有”。
- `Errors` 还要看“是不是错在同一个地方”。
### 3. Cosine Similarity
它看的是：
- 模拟学生这句话，和真实学生这句话，在语义向量空间里有多接近。
怎么做：
- 论文用 `Qwen3-Embedding-8B` 把两句话编码成向量。
- 再算两个向量的 cosine similarity。
怎么理解：
- 越高，说明两句话整体语义越接近。
- 它比 `ROUGE-L` 更偏“意思像不像”，不那么依赖字面完全重复。
### 4. ROUGE-L
它看的是：
- 模拟学生这句话和真实学生这句话，在字面表达上重合得多不多。
怎么做：
- 主要看最长公共子序列，也就是词和短语层面的重叠程度。
怎么理解：
- 越高，说明字面说法越接近。
- 它比 `Cosine Similarity` 更偏“表面措辞像不像”。
## 论文 Table 1：各方法四指标数值
| 方法 | Correctness | Errors | Cosine Similarity | ROUGE-L |
| --- | ---: | ---: | ---: | ---: |
| SFT (Llama 3.2 3B) | 0.5557 | 0.0815 | 0.7331 | 0.3058 |
| DPO (Llama 3.2 3B) | 0.5748 | 0.0584 | 0.7345 | 0.3109 |
| SFT (Llama 3.1 8B) | 0.5670 | 0.0661 | 0.7383 | 0.3212 |
| DPO (Llama 3.1 8B) | 0.5761 | 0.0529 | 0.7390 | 0.3212 |
| Zero-Shot (GPT 4.1) | 0.5926 | 0.0220 | 0.5460 | 0.1648 |
| OCEAN (GPT 4.1) | 0.6039 | 0.0308 | 0.5739 | 0.1772 |
| ICL (GPT 4.1) | 0.5991 | 0.0319 | 0.5919 | 0.1939 |
| Reasoning (GPT 5 Mini) | 0.5870 | 0.0088 | 0.5992 | 0.2170 |
| Oracle (GPT 4.1) | 0.6755 | 0.1872 | 0.6032 | 0.2109 |
## 如果把它当“要超越的目标”，应该怎么看
### 先看绝对最高值
四个指标里的表面最高值分别是：
- `Correctness`: `0.6755`，来自 `Oracle`
- `Errors`: `0.1872`，来自 `Oracle`
- `Cosine Similarity`: `0.7390`，来自 `DPO (Llama 3.1 8B)`
- `ROUGE-L`: `0.3212`，来自 `SFT (Llama 3.1 8B)` 和 `DPO (Llama 3.1 8B)` 并列
### 但这里有一个重要问题：不是所有目标都公平
论文自己明确说了：
- `Oracle` 有信息泄漏
- `OCEAN` 也有泄漏，因为它用整段真实对话反推出 persona
- `ICL` 也不是完全干净
所以如果我们要定“公平可超越目标”，最好分两档。
## 建议你用的两档目标
### 档 1：绝对参考上界
这个可以写给老师看，但要明确说明“有泄漏，不是公平对比”。
- `Correctness`: `0.6755` (`Oracle`)
- `Errors`: `0.1872` (`Oracle`)
- `Cosine Similarity`: `0.7390` (`DPO 8B`)
- `ROUGE-L`: `0.3212` (`SFT 8B / DPO 8B`)
### 档 2：更公平的主目标
如果我们强调“不作弊、不泄漏”，那更合理的目标是：
- `Correctness`: `0.5926` (`Zero-Shot`) 或 `0.5870` (`Reasoning`)
- `Errors`: `0.0815` (`SFT 3B`)
- `Cosine Similarity`: `0.7390` (`DPO 8B`)
- `ROUGE-L`: `0.3212` (`SFT 8B / DPO 8B`)
这里面最难的是后两个语言指标，因为论文里真正高分主要来自 fine-tuned 方法，不是 prompting。
## 对我们当前方向最重要的启发
如果一个方法：
- `Correctness` 很高
- `Errors` 也不低
- 但 `Cosine Similarity` 和 `ROUGE-L` 很低
那通常意味着：
- 它在“答对答错”这个粗层面有点像学生
- 但在“真实学生会怎么说”这个层面还不像
这也是 EEDI 论文最核心的结论之一：
- prompting 方法更容易在 correctness 上不难看
- 但语言、行为细节、知识变化这些更细层面的指标，通常还是 fine-tuned 方法更强
## 可以直接拿去汇报的一句话
我们后面如果说“超越论文”，必须先说清楚是超越哪一档目标：
- 如果是超越 `Oracle` 的 `Correctness/Errors`，那只是数值上超过一个带泄漏参考，不代表方法更强。
- 如果是超越 `DPO 8B` 的 `Cosine Similarity/ROUGE-L`，那才更接近真正意义上的困难目标。
