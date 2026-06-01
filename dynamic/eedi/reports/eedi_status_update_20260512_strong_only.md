# EEDI 当前状态更新（2026-05-12）

## 1. 当前决策

当前阶段，**暂停继续推进 weak harness**，后续实验与方法改进**只在 strong harness 上进行**。

原因不是工程偏好，而是这次 4334 task 全量对照已经说明：

- weak 版本没有因为“补齐失败样本”而反超 strong；
- strong 版本在核心五项指标里整体更稳；
- weak 版本只在 `same_mechanism` 上局部占优，但不足以支持继续作为主线推进。

因此后续主线收敛为：

> 以 strong harness 为唯一主线，围绕 `consistency` 提升展开后续分析与改造。

---

## 2. 本次对照设置

本次对照使用：

- strong 版本：`strong_population_calibrated_train200k8_structural_only`
- weak 版本：`weak_v31_commitment_first_population_calibrated_train200k8_structural_only`
- 评测范围：EEDI 全量 `4334 tasks`
- 只看五个指标：
  - `consistency`
  - `same_knowledge`
  - `same_locus`
  - `same_mechanism`
  - `error_realization`

另外，为了公平比较：

- strong 运行中有一个坏样本卡死：
  - `dialogue_id = 104006_4779`
  - `turn_idx = 6`
- 该样本在 strong 中未成功生成；
- 因此最终对照时，**weak 侧也同步剃掉同一个样本**；
- 两边最终都按同一批 `4154 eval rows` 做 detached evaluation。

---

## 3. 最新结果

### 3.1 Strong

- `consistency = 0.5773`
- `same_knowledge = 0.7832`
- `same_locus = 0.6713`
- `same_mechanism = 0.6713`
- `error_realization = 0.6034`

结果文件：

- `eedi/outputs/official_test_4334_strong_population_calibrated_train200k8_structural_only_20260511_minus_bad_104006_4779_turn6/detached_eval_5metrics/detached_eval_summary.json`

### 3.2 Weak

- `consistency = 0.5660`
- `same_knowledge = 0.7572`
- `same_locus = 0.6461`
- `same_mechanism = 0.6955`
- `error_realization = 0.5094`

结果文件：

- `eedi/outputs/official_test_4334_weak_qwen2_5_7b_v31_population_calibrated_train200k8_structural_only_20260511_minus_bad_104006_4779_turn6/detached_eval_5metrics/detached_eval_summary.json`

---

## 4. 结论

结论很直接：

- `consistency`：strong 更高
- `same_knowledge`：strong 更高
- `same_locus`：strong 更高
- `same_mechanism`：weak 略高
- `error_realization`：strong 明显更高

所以：

> “weak 目前落后只是因为 failure” 这个假设不成立。

更准确地说：

> weak 的主要问题不是单个坏样本，而是它在“什么时候应当和真实学生一样错、以及怎样把这个错稳定外显出来”这件事上，整体仍弱于 strong。

---

## 5. 后续主线

后续只保留 strong 主线，重点问题变成：

> 为什么 strong 的 `consistency` 只有 `0.5773`，以及如何把它提升到更高水平，同时尽量不伤害 `error_realization`。

后续分析优先看：

1. strong 的错误主要掉在哪些 turn 类型；
2. 是过度判错、过度外显错误，还是在不该错时仍然错；
3. few-shot / population calibration 到底在哪些局部 tutor move 上帮助了 `error_realization`，又在哪些地方伤害了 `consistency`；
4. 后续改动必须仍然遵守第三人称状态层，不退化成结果导向的 prompt patch。

---

## 6. 当前项目状态一句话总结

一句话总结就是：

> weak 线先停，strong 线继续；接下来不再追求“双线并跑”，而是集中精力把 strong 的 `consistency` 往上抬。
