# EEDI 弱模型 Harness v4 报告（2026-05-09）

## 1. 这次 v4 改了什么

v4 只改一件核心事情：

> 不再让弱模型自己同时决定“这一轮具体要说什么数学内容”以及“怎么把它说出来”，而是先由上游强编译层做第三人称局部规划，再让弱模型只负责表层实现。

也就是从：

- 强模型给状态
- 弱模型自己临场想局部数学主张
- 弱模型自己生成 student turn

改成：

- 强模型给状态
- 强模型再给一个 **局部可说内容计划**
- 弱模型只在这个局部计划边界内，把话说出来

这一步的理论动机不是工程补丁，而是：

- 支架理论：先给到当前最近发展区内可用的局部支点；
- 认知学徒制：把“局部解题焦点”先外显，再让学习者完成表达；
- 动态评估：先判断当前轮学生能接住什么，再看他如何实现。

---

## 2. 新增对象

v4 新增了两层：

### 2.1 `MediatedTurnPlanState`

它不是最终回复，而是当前轮的第三人称局部计划，主要包含：

- 这一轮回应空间是什么
- 这一轮是否应该形成 claim
- claim 是支持一致、错误一致，还是无 claim
- 当前轮允许保留的局部说法核心
- 是否可以提到 tutor 刚给的支持

### 2.2 `TeachingSupportPacketV4`

它把上面的局部计划翻译成弱模型可执行的受限 packet，主要包含：

- 本轮允许的句数
- 必须保留的局部 claim kernel
- 必须保留的局部 reason kernel
- 允许动作 / 禁止动作
- 支持使用规则

因此 v4 的核心边界是：

> 第三人称层先决定“这一轮局部上能说什么”，弱模型只负责“把它实现成一句学生话”。

---

## 3. 本次正式运行

- 运行目录：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_v4_commitment_first_20260509`
- 模型：`qwen2.5-7b-instruct`
- 架构版本：`v4`
- 模式：`commitment_first`
- 并发：`50`

运行结果：

- 成功写出预测：`874`
- 失败样本：`126`
- 合计：`1000`

detached eval：

- 输入：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_v4_commitment_first_20260509\official_eval_input.csv`
- 输出：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_v4_commitment_first_20260509\detached_eval_1000`

---

## 4. 指标结果

统一指标名如下：

- `consistency`
- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

对比结果：

| 版本 | consistency | same_knowledge | same_locus | same_mechanism | error_realization |
| --- | ---: | ---: | ---: | ---: | ---: |
| 强版 | 0.6679 | 0.7949 | 0.5897 | 0.5897 | 0.3514 |
| 弱版 v3.1 | 0.5857 | 0.8615 | 0.6308 | 0.6154 | 0.5909 |
| 弱版 v3.2 | 0.5835 | 0.6774 | 0.5806 | 0.6774 | 0.5487 |
| 弱版 v4 | 0.5238 | 0.6863 | 0.6078 | 0.5098 | 0.5368 |

v4 detached eval 统计口径补充：

- `n_rows = 837`
- `correctness.n_eligible_rows = 441`
- `same_error.n_both_officially_incorrect_rows = 103`

---

## 5. 怎么理解这次结果

### 5.1 v4 没有达成目标

如果按你当前目标：

- `consistency >= 0.70`
- `same_knowledge >= 0.55`
- `same_locus >= 0.55`
- `same_mechanism >= 0.55`

那么 v4 只有：

- `same_knowledge` 达标
- `same_locus` 达标
- `consistency` 明显不达标
- `same_mechanism` 反而掉到强版以下

所以：

> 当前这版 v4 还不能作为正式替代强版 harness。

### 5.2 但 v4 的核心想法不一定错

20 条 probe 时，v4 一度出现过：

- `consistency = 0.7143`

这说明：

> “强编译层先给局部可说内容，弱模型只做表层实现” 这个方向本身可能是对的。

真正把全量拖下去的，很大概率不是 v4 的核心思想，而是 **当前实现把协议卡得太死**。

---

## 6. 失败结构诊断

`126` 条失败里，主要是这几类：

1. `71` 条：`pred_turn does not preserve wrong_claim_seed`
2. `36` 条：`pred_turn exceeds max_sentences=1 with sentence_count=2`
3. `4` 条：`pred_turn does not preserve support_consistent_claim_seed`
4. `4` 条：`uptake_rationale must be a non-empty list`
5. `3` 条：`pred_turn invents a math answer in a no_claim turn`

这说明当前全量掉点主要不是“模型完全不会”，而是：

- 错误 claim 保留规则过硬；
- 单句限制过硬；
- 少量上游 JSON / schema 仍有不稳。

其中最关键的是前两项。

### 6.1 `wrong_claim_seed` 过严

当前实现要求：

> 如果本轮是错误一致 claim，弱模型最终说出来的话必须保留预先计划的错误 kernel。

问题在于弱模型表层实现时经常会：

- 换一种近义说法；
- 略写一步；
- 只保留数字不保留原句；
- 保留错的方向，但没有逐 token 对齐。

于是很多本来可能“语义上还算同一路错误”的样本，被协议直接打成失败。

### 6.2 `max_sentences=1` 过严

对于：

- `clarification_request`
- `brief_acknowledgment`

当前很多 turn 被限制成只能 1 句。

但弱模型很自然会输出：

- 先一句回应
- 再一句短补充

这并不一定意味着它越界了，只是语言实现稍微展开了一点。现在这类样本也被直接判死。

---

## 7. 当前判断

基于这次全量结果，我的判断是：

### 7.1 结论一：当前 v4 结果不能直接用

因为它的 `consistency` 从 v3.1 / v3.2 继续掉到了 `0.5238`，这个量级不能接受。

### 7.2 结论二：v4 值得保留，但必须做 v4.1 修正

应该保留的是：

- 强编译层先做第三人称局部计划
- 弱模型只做受限表层实现

不应该保留的是：

- 过硬的 token 级 claim seed 保留校验
- 对社交短回应过紧的单句限制

### 7.3 结论三：当前最稳的正式基线仍然是强版

如果现在就要给老师或下游一个可交付版本：

> 仍然应该把强版 harness 作为正式主基线。

原因很直接：

- `consistency` 最高且更稳；
- `same_locus`、`same_mechanism` 也都不差；
- 唯一明显短板主要是 `error_realization`。

---

## 8. 下一步应该怎么改

下一步不应该再大改架构，而应该做 **v4.1 协议松绑版**：

1. 把 `wrong_claim_seed` 从硬 token 保留，改成更稳的局部语义保留；
2. 对 `clarification_request` / `brief_acknowledgment` 放宽句数限制；
3. 保留 `no_claim` 约束，但不要把正常的短数学提及误杀成“invent answer”；
4. 修掉少量 schema 不稳点，再先做小 probe；
5. 只有 probe 重新站回 `consistency 0.65+`，才值得再跑 1000。

一句话总结：

> v4 的方向可能对，但这次全量失败主要败在“协议过硬”，不是败在“弱模型局部规划外包给强编译层”这个思想本身。
