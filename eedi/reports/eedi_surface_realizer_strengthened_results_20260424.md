# EEDI 学生化表达层强化实验结果
这次实验是在上一轮纠偏基础上继续推进。
目标不是把回复压短，而是：

> 在不改数学内容、不改对错、不改错误路径的前提下，把输出更明确地落成学生当下会说的话。

运行目录：
- 小测试 20 条：[surface_realizer_strengthened_probe_20260424_20t](D:/Study/sii/MathStudent/eedi/outputs/surface_realizer_strengthened_probe_20260424_20t)
- 正式 92 条：[surface_realizer_strengthened_full10d_20260424](D:/Study/sii/MathStudent/eedi/outputs/surface_realizer_strengthened_full10d_20260424)

## 一、小测试 20 条
结果：
- `Correctness = 0.7273`
- `Errors = 0.1667`
- `Cosine Similarity = 0.1644`
- `ROUGE-L = 0.1594`

对比上一轮 20 条弱版表层层：
- `Correctness`：`0.6364 -> 0.7273`
- `Errors`：`0.0000 -> 0.1667`
- `Cosine Similarity`：`0.1527 -> 0.1644`
- `ROUGE-L`：`0.1364 -> 0.1594`

结论：
- 这说明强化后的版本不是单纯“更像学生说话一点”，而是四个指标一起往上走。
- 所以这个方向值得继续放大验证。

## 二、正式 92 条结果
结果：
- `Correctness = 0.6667`
- `Errors = 0.3913`
- `Cosine Similarity = 0.1632`
- `ROUGE-L = 0.1421`

和旧版 92 条结果对比：
- `Correctness`：`0.6863 -> 0.6667`
- `Errors`：`0.3043 -> 0.3913`
- `Cosine Similarity`：`0.1590 -> 0.1632`
- `ROUGE-L`：`0.1594 -> 0.1421`

## 三、怎么理解这组结果
这组结果不是“全面变好”，而是出现了清楚的结构性变化。

好的部分：
- `Errors` 明显上升，说明当学生本来就在错时，我们现在更能保留并说出相近的错误路径。
- `Cosine Similarity` 小幅上升，说明整体语义更接近真实学生。
- 从样例看，的确有一部分输出从“整洁解释句”变成了更像学生当下会说的话。

不够好的部分：
- `Correctness` 有小幅下降。
- `ROUGE-L` 下降，说明虽然更像学生说话了，但字面表达并没有更贴近真实学生原句。

所以现在最合理的结论是：

> 这次强化后，系统更像在保留学生错误路径和即时口吻，但还没有稳定做到“既像学生说话，又同时尽量贴近真实学生的具体表述”。

## 四、是否真的改到了风格，而不是乱改内容
有证据表明这次不是乱改。

正式 92 条里，有 `30` 条 `pred_turn` 和 `draft_turn` 不同，其中 `24` 条改写没有触发违规。
典型变化包括：
- `I’m still not totally sure, but maybe both of them are right?`
  变成
  `I’m not sure, but maybe both are right?`
- `uh, maybe 15? since 3 times 5 is 15 and they don't share any factors`
  变成
  `uh, maybe 15? 'cause 3 times 5 is 15 and they don't have common factors`
- `so like, for 3 and 5 it worked because 3 times 5 is 15, which is the lcm... but i'm not sure if that means it's always true or not.`
  变成
  `so like, 3 times 5 is 15, and that's the lcm... but does that mean it always works?`

这些改动的共同点是：
- 内容没换
- 对错没翻
- 错误路径没丢
- 但说法更像学生边想边说，而不是像写出来的解释句

## 五、当前判断
这条路是对的，但还没收敛。

如果只问“要不要继续保留并发展这个方向”，答案是要。
如果问“现在这个版本是不是已经可以当最终版大跑”，答案还不是。

原因很简单：
- 它已经证明末端学生化表达层可以带来真实收益
- 但收益还不均衡
- 目前还没同时兼顾好 `Cosine / ROUGE / Correctness`

## 六、下一步最该做什么
下一步不该回到数据集迎合，也不该回到“更短一点”。

最该做的是两件事：
1. 继续压低 draft 里的解释腔，让 draft 从源头上更少像分析句。
2. 给表层层增加“语义保持检查”，确保学生化改写更大胆，但不误改数学内容和对错状态。

## 七、这次改了哪个环节、理论依据、如何避免作弊
1. 改了哪个环节
改的是 `transition.py`、`constraint_bundle.py`、`prompts.py`、`surface_style.py`、`generation.py`，核心是强化学生化表达边界。
2. 理论依据是什么
仍然是第三人称状态层先定认知边界，再由表达层在该边界内落成学生发言；表达成熟度仍然受 `response_maturity_cap` 约束。
3. 如何避免作弊
没有使用真实下一句，没有使用 EEDI 常见短语模板，没有按题号和轮次特判，也没有把官方评测结果送回 generation path。
