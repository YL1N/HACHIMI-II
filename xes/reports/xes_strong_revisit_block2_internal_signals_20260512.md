# XES 强模型 Harness Revisit 第二块：StudentInternalSignals（2026-05-12）

## 1. 这块 revisit 解决什么问题

这份报告审计的是：

> `StudentInternalSignals` 这一层是否有必要保留？

它原本的作用是把完整 `StudentModel` 压缩成几个更短的内部信号：

- `efficacy_signal`
- `srl_fragility_signal`
- `control_signal`
- `value_signal`
- `directness_signal`

设计动机是：

> 让后续状态判断不用每次重新读完整学生画像，而是看到一组压缩后的心理/行为信号。

这听起来合理，但需要验证：

- 它是否真的提升核心指标；
- 它是否只是多了一层软提示；
- 它是否会把学生差异压平。

---

## 2. 理论判断

从教育理论看，自我效能、SRL、控制感、价值感、回答风格这些变量都可能影响学生作答。

但在当前 XES 任务里，我们模拟的是静态单题作答，不是长程学习过程。  
因此这些心理变量是否必要，要看它们是否能改善：

- 逐学生逐题对错一致性；
- 学生层级强弱差异；
- 题目层级难度结构。

第一性原则是：

> 如果一个中间层只把已有学生画像重新压缩一遍，但没有明显提升指标，就不应作为主线必要模块。

---

## 3. 工程事实

当前代码里，`StudentInternalSignals` 主要进入两个位置：

1. `ItemResponseState`
   - 作为 `implementation_derived_signals` 传给 LLM；
   - 影响学生当前作答状态的软判断。

2. `Student Answer`
   - 作为 `implementation_derived_signals` 传给答案生成；
   - 影响最终回答风格。

但它没有进入硬规则：

- 不参与 `StudentItemInteractionDecision` 的 margin 计算；
- 不改变 `ConstraintBundle` 的硬约束；
- 不参与 correctness 评测。

所以它更像是：

> 一个软提示层，而不是硬状态层。

这正是本轮要审计的原因。

---

## 4. 实验设计

本轮固定新的 XES 强模型主线：

> `hachimi_no_difficulty_signal`

也就是：

- 保留 Hachimi；
- 保留第三人称状态层；
- 不传 few-shot 难度对照；
- 不传真实 difficulty band；
- 只改变 `StudentInternalSignals`。

实验设置：

- 学生数：`60`
- 每个学生测试题：`96`
- 总任务数：`5760`
- 并发：`50`
- 模型：`qwen`
- 固定 cohort：`D:\Study\sii\MathStudent\xes\configs\common_test_60x96_20260507.json`

对照版本：

| variant | internal signals |
|---|---|
| `hachimi_no_difficulty_signal` | 保留全部 5 个 signals |
| `hachimi_no_difficulty_signal_no_internal_signals` | 完全不传 signals |
| `hachimi_no_difficulty_signal_minimal_signals` | 只传 `srl_fragility_signal` 和 `directness_signal` |

---

## 5. 结果

| variant | accuracy | consistency | item_P | item_S | student_P | student_S |
|---|---:|---:|---:|---:|---:|---:|
| `hachimi_no_difficulty_signal` | 0.7382 | 0.6913 | 0.2635 | 0.3416 | 0.6701 | 0.6843 |
| `hachimi_no_difficulty_signal_no_internal_signals` | 0.7309 | 0.6847 | 0.2560 | 0.3261 | 0.7017 | 0.7276 |
| `hachimi_no_difficulty_signal_minimal_signals` | 0.7286 | 0.6870 | 0.2617 | 0.3372 | 0.6722 | 0.6987 |

完整汇总：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md`

---

## 6. 结果解释

### 6.1 全量 signals 对 consistency 有小幅帮助

保留全部 signals 时：

- `consistency = 0.6913`

完全去掉 signals 时：

- `consistency = 0.6847`

差值是：

- `+0.0066`

这个提升存在，但不大。  
它没有达到第一轮筛查里 `0.02` 的明显贡献阈值。

所以不能说：

> `StudentInternalSignals` 是强必要模块。

更准确是：

> 它对 consistency 有轻微帮助，但不是不可替代。

### 6.2 去掉 signals 后，student-level 明显更好

完全去掉 signals 后：

- `student_P` 从 `0.6701` 升到 `0.7017`
- `student_S` 从 `0.6843` 升到 `0.7276`

这说明 signals 可能在压缩学生画像时损失了学生之间的差异。

直白说：

> 把学生压成 5 个 low / medium / high 信号，可能让学生更像彼此，从而伤害 student-level alignment。

### 6.3 minimal signals 没有带来清晰优势

只保留 `srl_fragility_signal` 和 `directness_signal` 后：

- `consistency = 0.6870`
- `student_P = 0.6722`
- `student_S = 0.6987`

它比 no-signals 的 consistency 稍高，但 student-level 明显不如 no-signals。  
它也没有超过 full-signals 的 consistency。

所以 minimal signals 不是一个明显更好的折中方案。

---

## 7. 模块必要性结论

| 模块 | 结论 | 原因 |
|---|---|---|
| `StudentInternalSignals` 全量层 | 条件必要 / 可简化 | consistency 小幅提升，但 student-level 下降 |
| no-signals 路线 | 强候选 | student_P/student_S 明显最高，consistency 只小幅下降 |
| minimal-signals 路线 | 暂不推荐 | 没有形成清晰优势 |

当前判断：

> `StudentInternalSignals` 不是主线强必要模块。

它最多是一个轻量辅助模块。  
如果目标优先是 `overall_consistency`，可以暂时保留。  
如果目标优先是学生差异建模，则应该去掉。

---

## 8. 当前主线建议

现在有两个合理选择。

### 8.1 consistency 优先

保留 full `StudentInternalSignals`：

- `consistency = 0.6913`
- `student_P = 0.6701`
- `student_S = 0.6843`

优点是 consistency 最高。

### 8.2 student-level 优先

去掉 `StudentInternalSignals`：

- `consistency = 0.6847`
- `student_P = 0.7017`
- `student_S = 0.7276`

优点是学生强弱差异保留最好。

### 8.3 当前推荐

当前还不建议立刻把 `StudentInternalSignals` 从主线删除。  
原因是：

- `overall_consistency` 仍是第一优先级；
- full signals 在 consistency 上仍是最高；
- 差距虽小，但方向明确。

但报告中应该把它从“必要模块”降级为：

> 可疑辅助模块，后续需要结合 `StudentModel` 字段级审计继续判断。

---

## 9. 后续动作

下一步不应该继续只围绕 signals 做组合。  
更合理的是进入 `StudentModel` 字段级审计：

1. 区分硬字段和软字段；
2. 保留进入硬判断的 `math_task_capability_profile`；
3. 审计自我效能、SRL、control-value、engagement、response directness 是否真有贡献；
4. 看是否可以直接用 `StudentModel` 替代 `StudentInternalSignals`。

---

## 10. 一句话结论

第二块 revisit 的结论是：

> `StudentInternalSignals` 对 consistency 有小幅帮助，但会削弱 student-level 对齐；它不是强必要模块，只能暂时作为可疑辅助层保留。

