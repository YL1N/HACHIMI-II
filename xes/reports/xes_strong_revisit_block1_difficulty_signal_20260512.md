# XES 强模型 Harness Revisit 第一块：difficulty 信号模块（2026-05-12）

## 1. 这块 revisit 解决什么问题

这份报告只审计一个模块：

> XES 强模型 harness 里，题目 difficulty 信号到底该不该进入 generation path？

这里的 difficulty 信号不是一个单一东西。  
当前代码里实际有两类：

1. `difficulty_anchor_context`
   - 给模型 easy / medium / hard 的同类型参考题；
   - 本质是 few-shot 难度对照。

2. `real_difficulty_band`
   - 直接把当前题的 easy / medium / hard band 写进题目画像；
   - 后续会影响学生-题目交互判断。

所以这块 revisit 不是问“难度有没有用”，而是问：

> 难度信息应该进入默认生成链路吗？

---

## 2. 理论判断

题目难度当然是教育测量里的重要概念。  
IRT / Rasch 这类模型本来就强调：

- 学生能力；
- 题目难度；
- 两者的相对关系。

但我们的任务不是估计一个总体正确率，而是模拟：

> 这个具体学生在这道具体题上的作答。

这就带来一个关键风险：

> 如果把题目总体难度直接塞进 generation path，模型可能会过度依赖“这题整体难不难”，而不是判断“这个学生遇到这道题会怎样”。

从 Evidence-Centered Design 的角度看，题目难度可以是解释证据，但不能替代对学生当前状态的推断。  
从 Assessment Triangle 的角度看，学生模型、任务特征、观察证据要分开，不能让一个总体题目统计信号直接压过学生-题目交互状态。

因此，第一性原则是：

> difficulty 可以用于离线分析和对照，但只有当它提高核心学生模拟指标时，才应该进入默认生成链路。

---

## 3. 工程事实

### 3.1 当前代码里的 difficulty 进入方式

主链入口在：

- `D:\Study\sii\MathStudent\xes\src\student_conditioned_benchmark.py`

原链路中，题目画像构建时会传入：

- `difficulty_anchor_context`
- `real_difficulty_band`

其中 `real_difficulty_band` 会进入：

- `ProblemRequirementProfile.real_difficulty_band`
- `StudentItemInteractionDecision` 的 `difficulty_load`
- `ItemResponseState` 的 difficulty-aware prompt 路径

也就是说，`real_difficulty_band` 不是纯解释字段。  
它会实质影响当前学生-题目的状态判断。

### 3.2 这次新增的控制开关

为了把两类 difficulty 信号拆开，新增了两个开关：

- `--enable_difficulty_anchor_context`
- `--enable_real_difficulty_band`

当前主线默认值已经改成：

- `enable_difficulty_anchor_context = False`
- `enable_real_difficulty_band = False`

也就是默认不传任何 difficulty 信号。

---

## 4. 实验设计

本块实验固定同一批 common-test 样本：

- 学生数：`60`
- 每个学生测试题：`96`
- 总任务数：`5760`
- 并发：`50`
- 模型：`qwen`
- 固定 cohort：`D:\Study\sii\MathStudent\xes\configs\common_test_60x96_20260507.json`

对照版本：

| variant | few-shot 难度对照 | 真实 difficulty band |
|---|---|---|
| `baseline_hachimi_state_step` | 开 | 开 |
| `hachimi_no_difficulty_anchor` | 关 | 开 |
| `hachimi_no_real_difficulty_band` | 开 | 关 |
| `hachimi_no_difficulty_signal` | 关 | 关 |

---

## 5. 结果

| variant | accuracy | consistency | item_P | item_S | student_P | student_S |
|---|---:|---:|---:|---:|---:|---:|
| `baseline_hachimi_state_step` | 0.6939 | 0.6703 | 0.3469 | 0.3990 | 0.6757 | 0.6936 |
| `hachimi_no_difficulty_anchor` | 0.7069 | 0.6767 | 0.3113 | 0.3913 | 0.6757 | 0.6973 |
| `hachimi_no_real_difficulty_band` | 0.7094 | 0.6753 | 0.2662 | 0.3491 | 0.6545 | 0.6955 |
| `hachimi_no_difficulty_signal` | 0.7326 | 0.6937 | 0.2927 | 0.3378 | 0.6958 | 0.7147 |

完整汇总：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md`

---

## 6. 结果解释

### 6.1 两个 difficulty 信号都关，核心指标最好

`hachimi_no_difficulty_signal` 同时取得：

- 最高 `accuracy`；
- 最高 `consistency`；
- 最高 `student_P`；
- 最高 `student_S`。

这说明：

> 对当前 XES 学生模拟目标来说，difficulty 信号不是核心必要模块，反而会干扰学生-题目个体判断。

### 6.2 baseline 的优势只在 item-level

baseline 的 `item_P / item_S` 最高：

- `item_P = 0.3469`
- `item_S = 0.3990`

这说明 difficulty 信号确实帮助模型保留“哪些题整体更难”的结构。

但问题是，我们现在主目标不是只复现题目总体难度排序，而是复现：

> 每个学生在每道题上是否会和真实学生一样对/错。

所以 item-level 好，不足以抵消 consistency 和 student-level 的损失。

### 6.3 只保留 few-shot 对照没有解决问题

`hachimi_no_real_difficulty_band` 保留 few-shot 对照，但关掉真实 band：

- `consistency = 0.6753`
- `item_P = 0.2662`
- `student_P = 0.6545`

这说明 few-shot 难度对照单独存在时，并没有稳定带来收益。  
它可能让模型多了一组参考题，但这些参考题并没有更好地转成学生-题目的个体判断。

### 6.4 真实 difficulty band 对 consistency 也不友好

`hachimi_no_difficulty_anchor` 关掉 few-shot 对照，但保留真实 band：

- `consistency = 0.6767`
- `item_P = 0.3113`
- `student_P = 0.6757`

它比 baseline 的 consistency 高，但仍低于两个都关的版本。

这说明真实 band 对 item-level 有帮助，但仍可能把模型往“总体题目难度判断”拉，而不是往“具体学生状态判断”拉。

---

## 7. 模块必要性结论

| 模块 | 结论 | 原因 |
|---|---|---|
| few-shot 难度对照 | 不进主线 | 单独保留时 student-level 不稳，item-level 也不如 baseline |
| 真实 difficulty band | 不进主线 | 会进入硬判断，伤害 consistency |
| 全部 difficulty 信号 | 从默认 generation path 移除 | 两个都关时 consistency/student_P/student_S 最好 |

最终判断：

> difficulty 信号在当前 XES 强模型 harness 中不是主线必要模块。

它可以保留为：

- 离线分析；
- item-level 解释；
- 消融对照；
- 后续题目难度专项研究。

但它不应该进入当前默认 generation path。

---

## 8. 已执行修改

已经把 XES 强模型主线默认改成不传 difficulty 信号：

- `D:\Study\sii\MathStudent\xes\run_student_conditioned_benchmark.py`
- `D:\Study\sii\MathStudent\xes\src\student_conditioned_benchmark.py`

默认配置现在等价于：

```text
enable_difficulty_anchor_context = False
enable_real_difficulty_band = False
```

保留命令行开关，是为了之后能复现实验：

```powershell
--enable_difficulty_anchor_context
--enable_real_difficulty_band
```

---

## 9. 对后续 revisit 的影响

第一块 difficulty 模块已经完成审计，并从主线移除。

接下来 revisit 应该继续看：

1. `StudentInternalSignals`
   - 它现在主要是软提示，可能是冗余压缩层；
   - 需要跑“去掉 internal signals”的版本。

2. `StudentModel` 字段
   - `math_task_capability_profile` 明显进入硬判断；
   - 自我效能、SRL、control-value 等字段主要进入 LLM 软判断；
   - 需要判断哪些字段只是解释文字。

3. `ProblemRequirementProfile` 字段
   - 操作复杂度、抽象度、作答格式、guessability 等进入硬判断；
   - justification / notes 主要是软提示；
   - 需要做字段级精简。

4. `state-step` vs `state-single`
   - state-step 保 item-level；
   - state-single 可能更保 student-level；
   - 需要决定主线是否继续用多步。

---

## 10. 一句话结论

第一块 revisit 的结论是：

> difficulty 信号能帮助题目层难度结构，但会伤害当前最重要的学生-题目一致性；因此从 XES 强模型默认生成链路中移除。

