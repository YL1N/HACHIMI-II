# EEDI 强弱版本对比报告（2026-05-12）

## 1. 这份报告回答什么问题

这份报告只回答一个很具体的问题：

> 在同一套 EEDI 全量 4334 task 设置下，当前的 strong harness 和 weak harness，到底谁更好，差在哪里，后续主线应该放在哪边？

这里的“更好”不再看 embedding 一类表面相似度，而只看五个核心指标：

- `consistency`
- `same_knowledge`
- `same_locus`
- `same_mechanism`
- `error_realization`

---

## 2. 对比对象

### 2.1 Strong 版本

- 版本名：`strong_population_calibrated_train200k8_structural_only`
- 配置文件：`D:\Study\sii\MathStudent\eedi\configs\run_strong_population_calibrated_full4334_20260511.json:1`
- 核心特征：
  - 单强模型主链路
  - 引入 `population calibration`
  - 使用 `train200` 校准样本
  - `top_k = 8`
  - 结构化校准，`structural_only`
  - 并发 `50`
  - 带 `retry_until_success`
  - 额外加了 `max_retry_attempts = 200`

### 2.2 Weak 版本

- 版本名：`weak_v31_commitment_first_population_calibrated_train200k8_structural_only`
- 配置文件：`D:\Study\sii\MathStudent\eedi\configs\run_weak_v31_population_calibrated_full4334_20260511.json:1`
- 核心特征：
  - `v31`
  - `ablation_mode = commitment_first`
  - 强模型做编排 / 判断
  - `qwen2.5-7b-instruct` 做学生表面作答
  - 同样引入 `population calibration`
  - 同样使用 `train200`
  - 同样 `top_k = 8`
  - 并发 `50`

---

## 3. 本次对比怎么做的

### 3.1 评测范围

- generation 目标任务数：`4334`
- detached eval 最终比较行数：`4154`
- correctness 参与统计样本：`2304`
- theory error 参与统计样本：`907`

### 3.2 为什么最后是 4154 行

strong 在全量运行时，有一个样本始终返回截断 JSON：

- `dialogue_id = 104006_4779`
- `turn_idx = 6`

因此：

- strong 原始 generation 只成功落盘了 `4333` 条；
- weak 原始 generation 成功落盘了 `4334` 条；
- 为了公平比较，最终把 weak 里同一个样本也剃掉；
- 所以最终两边都在**同一批 4154 eval rows**上比较。

相关文件：

- strong 剃样本说明：`D:\Study\sii\MathStudent\eedi\outputs\official_test_4334_strong_population_calibrated_train200k8_structural_only_20260511_minus_bad_104006_4779_turn6\minus_bad_summary.json:1`
- weak 剃样本说明：`D:\Study\sii\MathStudent\eedi\outputs\official_test_4334_weak_qwen2_5_7b_v31_population_calibrated_train200k8_structural_only_20260511_minus_bad_104006_4779_turn6\minus_bad_summary.json:1`

### 3.3 为什么这次不看 embedding

这次按当前项目决策，**只看五个教育解释性指标**，不再看 embedding / cosine / rouge 一类文本表面相似度。

原因是：

- 我们关心的是“是否和真实学生一样判断对错、一样落在同类错误机制上”；
- 而不是“字面像不像”。

---

## 4. 运行事实

### 4.1 Strong 运行事实

- 原始生成条数：`4333`
- 重试总次数：`9263`
- 失败文件：无单独 failure 落盘
- 卡住原因：最后 1 条反复返回截断 JSON

### 4.2 Weak 运行事实

- 原始生成条数：`4334`
- 重试总次数：`575`
- `progress.json` 显示全量完成
- failure 数：`0`

这说明 strong 这次工程稳定性比 weak 差，但这不等于 weak 的模拟质量更好。  
稳定性和模拟质量需要分开看。

---

## 5. 核心结果

## 5.1 Strong

- `consistency = 0.5773`
- `same_knowledge = 0.7832`
- `same_locus = 0.6713`
- `same_mechanism = 0.6713`
- `error_realization = 0.6034`

结果文件：

- `D:\Study\sii\MathStudent\eedi\outputs\official_test_4334_strong_population_calibrated_train200k8_structural_only_20260511_minus_bad_104006_4779_turn6\detached_eval_5metrics\detached_eval_summary.json:1`

## 5.2 Weak

- `consistency = 0.5660`
- `same_knowledge = 0.7572`
- `same_locus = 0.6461`
- `same_mechanism = 0.6955`
- `error_realization = 0.5094`

结果文件：

- `D:\Study\sii\MathStudent\eedi\outputs\official_test_4334_weak_qwen2_5_7b_v31_population_calibrated_train200k8_structural_only_20260511_minus_bad_104006_4779_turn6\detached_eval_5metrics\detached_eval_summary.json:1`

---

## 6. 直接对比

### 6.1 指标胜负

- `consistency`：strong 更高（`0.5773 > 0.5660`）
- `same_knowledge`：strong 更高（`0.7832 > 0.7572`）
- `same_locus`：strong 更高（`0.6713 > 0.6461`）
- `same_mechanism`：weak 更高（`0.6955 > 0.6713`）
- `error_realization`：strong 更高（`0.6034 > 0.5094`）

### 6.2 一句话总结

一句话就是：

> weak 只在 `same_mechanism` 上占优；其余四项，尤其 `consistency` 和 `error_realization`，都是 strong 更强。

---

## 7. 这意味着什么

## 7.1 “weak 只是被 failure 拖累” 这个解释不成立

这次专门把 strong 卡住的坏样本从 weak 里也剃掉以后，结果仍然没有反转。

所以不能再把 weak 的落后解释成：

- 只是某几个 failure；
- 只是重试不够；
- 只是一次偶然运行事故。

更合理的解释是：

> weak 在“当前轮到底应不应该和真实学生一样错，以及这个错怎样稳定外显”这件事上，本体能力仍弱于 strong。

## 7.2 weak 的主要问题不只是“不稳定”，而是“错误落点不够稳”

从指标组合看，weak 的特征更像：

- 某些时候机制标签能对上；
- 但更容易在是否应该错、是否真把错说出来上漂移；
- 所以 `consistency` 和 `error_realization` 拉不上去。

换句话说，weak 不是完全没学到错误结构，而是：

> 它还没有把“第三人称状态判断”稳定转成“当前轮应当出现什么局部错误外显”。

## 7.3 strong 的主要优势

strong 当前的优势主要在三层：

- 更容易和真实学生在“这一轮对还是错”上对齐；
- 更容易把错误真正落到外显回复里；
- 在知识类型和错误 locus 上也更稳。

这说明 strong 主链路虽然还有明显上升空间，但它的**方法骨架目前更可靠**。

---

## 8. 为什么 weak 只在 same_mechanism 上略高

这个现象值得注意，但不能过度解读。

它更可能说明：

- weak 在某些已经决定“要错”的样本里，
- 由于表层作答更短、更局部、更不成熟，
- 有时反而更容易落进和真实学生相同的错误机制标签。

但这并不代表 weak 整体更好，因为：

- 如果它连“该不该错”都没对齐，
- 或者没有把错稳定说出来，
- 那单独一个 `same_mechanism` 变高，并不能支撑总目标。

我们的目标不是“偶尔在一部分错题上标签看起来像”，而是：

> 稳定地在正确的 turn 上，以合理的外显方式，复现真实学生的局部错误。

---

## 9. 结论

本次 strong vs weak 全量对照的结论非常明确：

> 当前阶段，strong 是更值得继续推进的主线，weak 不适合作为后续主线继续投入。

更具体地说：

- weak 没有实现对 strong 的整体反超；
- strong 在五项核心指标中赢了四项；
- 且 strong 赢下的恰好是更关键的两项：`consistency` 和 `error_realization`。

因此项目决策更新为：

> **后续只推进 strong harness，weak harness 暂时冻结。**

---

## 10. 后续工作建议

接下来不应该再把精力花在“继续追 weak 反超”上，而应该集中到 strong 的真正短板：

- 当前 strong 的 `consistency` 只有 `0.5773`；
- 这说明它虽然比 weak 强，但离目标仍明显不够。

后续最该做的是：

1. 分解 strong 的 `consistency` 错误来源；
2. 分析是过度犯错、还是不该犯错时仍犯错；
3. 分析 few-shot / population calibration 到底在哪类 tutor move 上帮了 `error_realization`，又在哪类场景伤了 `consistency`；
4. 在不破坏第三人称状态层的前提下，只对 strong 主链做改进。

---

## 11. 当前最终决策

当前最终决策一句话概括：

> weak 线暂停，strong 线继续；后续所有主实验、主分析、主改造，都以 strong harness 为唯一主线。
