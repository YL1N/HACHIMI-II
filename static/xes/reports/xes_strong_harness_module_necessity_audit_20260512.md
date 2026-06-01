# XES 强模型 Harness 模块必要性审计报告（2026-05-12）

## 1. 这轮实验回答什么问题

这轮实验不是为了继续证明 XES 强模型 harness 有效。

它要回答的是：

> 当前强模型 harness 里的模块，哪些真的必要，哪些只是看起来合理，哪些可以简化？

本轮只看 XES 强模型 harness。  
弱模型 harness 不再作为主线推进。

---

## 2. 实验设置

所有实验使用同一批样本：

- 学生数：`60`
- 每个学生测试题：`96`
- 总预测任务：`5760`
- 历史题数：`30`
- 固定 cohort：`D:\Study\sii\MathStudent\xes\configs\common_test_60x96_20260507.json`
- 并发：`50`
- 模型：`qwen`
- 输出目录：`D:\Study\sii\MathStudent\xes\outputs\xes_strong_ablation_60x96_20260512`

这样可以保证不同版本之间主要差异来自 harness 模块，而不是样本变化。

---

## 3. 本轮跑了哪些版本

### 3.1 单模块消融

| variant | 含义 |
|---|---|
| `baseline_hachimi_state_step` | 当前主线 |
| `history_only_state_step` | 去掉 Hachimi，只用 XES 历史 |
| `hachimi_direct` | 去掉状态链，直接生成 |
| `hachimi_state_single` | 状态链保留，但多步生成改成单步 |
| `hachimi_no_difficulty_anchor` | 去掉 difficulty anchor |
| `hachimi_third_person_response` | 最终回答改成第三人称 |

### 3.2 组合消融

| variant | 含义 |
|---|---|
| `history_only_direct` | 无 Hachimi + 直接生成 |
| `history_only_state_single` | 无 Hachimi + 单步状态生成 |
| `history_only_no_difficulty_anchor` | 无 Hachimi + 无 difficulty anchor |
| `hachimi_direct_no_difficulty_anchor` | 有 Hachimi + 直接生成 + 无 difficulty anchor |
| `hachimi_state_single_no_difficulty_anchor` | 有 Hachimi + 单步状态生成 + 无 difficulty anchor |
| `history_only_direct_no_difficulty_anchor` | 无 Hachimi + 直接生成 + 无 difficulty anchor |
| `hachimi_no_real_difficulty_band` | 保留 few-shot 难度对照，但不直接传真实难度 band |
| `hachimi_no_difficulty_signal` | few-shot 难度对照和真实难度 band 都不传 |

---

## 4. 核心结果

| variant | acc | consistency | item_P | item_S | student_P | student_S | failure_rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline_hachimi_state_step` | 0.6939 | 0.6703 | 0.3469 | 0.3990 | 0.6757 | 0.6936 | 0.0000 |
| `history_only_state_step` | 0.7054 | 0.6752 | 0.2912 | 0.3746 | 0.6606 | 0.6661 | 0.0002 |
| `hachimi_direct` | 0.6089 | 0.5988 | 0.2028 | 0.2286 | 0.3716 | 0.4115 | 0.0000 |
| `hachimi_state_single` | 0.6851 | 0.6653 | 0.3041 | 0.3522 | 0.6898 | 0.6999 | 0.0000 |
| `hachimi_no_difficulty_anchor` | 0.7069 | 0.6767 | 0.3113 | 0.3913 | 0.6757 | 0.6973 | 0.0000 |
| `hachimi_third_person_response` | 0.5634 | 0.5852 | 0.3162 | 0.3684 | 0.6764 | 0.6934 | 0.0000 |
| `history_only_direct` | 0.6094 | 0.6017 | 0.2310 | 0.2728 | 0.2463 | 0.1974 | 0.0000 |
| `history_only_state_single` | 0.6925 | 0.6717 | 0.2726 | 0.3128 | 0.7087 | 0.7152 | 0.0000 |
| `history_only_no_difficulty_anchor` | 0.6976 | 0.6740 | 0.3079 | 0.3620 | 0.6742 | 0.7017 | 0.0000 |
| `hachimi_direct_no_difficulty_anchor` | 0.6167 | 0.6062 | 0.2209 | 0.2528 | 0.5049 | 0.4950 | 0.0000 |
| `hachimi_state_single_no_difficulty_anchor` | 0.6799 | 0.6524 | 0.2716 | 0.2942 | 0.6756 | 0.6952 | 0.0000 |
| `history_only_direct_no_difficulty_anchor` | 0.6127 | 0.6023 | 0.2135 | 0.2539 | 0.4783 | 0.4701 | 0.0000 |
| `hachimi_no_real_difficulty_band` | 0.7094 | 0.6753 | 0.2662 | 0.3491 | 0.6545 | 0.6955 | 0.0000 |
| `hachimi_no_difficulty_signal` | 0.7326 | 0.6937 | 0.2927 | 0.3378 | 0.6958 | 0.7147 | 0.0000 |

汇总文件：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md`

---

## 5. 第一结论：第三人称状态层必须保留

这是本轮最明确的结论。

只要把状态链改成 direct，指标都会明显掉：

| 对比 | consistency 变化 | item_P 变化 | student_P 变化 |
|---|---:|---:|---:|
| baseline → `hachimi_direct` | -0.0715 | -0.1442 | -0.3041 |
| baseline → `history_only_direct` | -0.0686 | -0.1159 | -0.4294 |
| baseline → `hachimi_direct_no_difficulty_anchor` | -0.0641 | -0.1260 | -0.1707 |
| baseline → `history_only_direct_no_difficulty_anchor` | -0.0681 | -0.1335 | -0.1973 |

这说明：

> 不能退回“历史/画像 -> 直接答案”的路线。

第三人称状态层不是装饰。  
它是让强模型不直接过度解题、还能保留学生差异的核心结构。

结论：

- `StudentItemInteractionDecision`
- `ItemResponseState`
- `ConstraintBundle`

这组状态层模块必须保留。

---

## 6. 第二结论：Hachimi 不是无条件必要

去掉 Hachimi 后：

| 对比 | consistency | item_P | student_P |
|---|---:|---:|---:|
| baseline | 0.6703 | 0.3469 | 0.6757 |
| `history_only_state_step` | 0.6752 | 0.2912 | 0.6606 |
| `history_only_state_single` | 0.6717 | 0.2726 | 0.7087 |
| `history_only_no_difficulty_anchor` | 0.6740 | 0.3079 | 0.6742 |

去掉 Hachimi 后，`consistency` 没有下降，甚至略升。  
但 `item_P / item_S` 明显下降。

这说明 Hachimi 的主要贡献不是“让逐题对错更一致”，而更像是：

> 帮系统保留一些题目层面的结构判断。

但它对学生层级指标不是稳定正贡献：

- `history_only_state_step` 的 `student_P/S` 低于 baseline；
- `history_only_state_single` 的 `student_P/S` 反而高于 baseline。

结论：

> Hachimi 是条件必要模块，不是无条件必要模块。

后续不应该默认说“必须有 Hachimi”。  
更准确的说法是：

> 如果目标重视 item-level alignment，Hachimi 可能有用；如果只看 consistency 和 student-level alignment，XES 历史本身可能已经足够。

---

## 7. 第三结论：difficulty 信号需要拆开看

这里必须先修正一个说法。

之前的 `hachimi_no_difficulty_anchor` 只关掉了 `difficulty_anchor_context`，也就是 few-shot 难度对照上下文。  
它没有关掉 `real_difficulty_band`。

所以当前 XES 里其实有两种 difficulty 信号：

1. `difficulty_anchor_context`
   - 给模型 easy / medium / hard 的同类型参考题；
   - 属于 few-shot / 对照锚点。

2. `real_difficulty_band`
   - 直接把当前题的 easy / medium / hard band 写进 `ProblemRequirementProfile`；
   - 后续 `StudentItemInteractionDecision` 会直接用它计算 `difficulty_load`。

补充实验把这两件事拆开了：

| 对比 | consistency | item_P | item_S | student_P | student_S |
|---|---:|---:|---:|---:|---:|
| baseline：两个都开 | 0.6703 | 0.3469 | 0.3990 | 0.6757 | 0.6936 |
| `hachimi_no_difficulty_anchor`：只关 few-shot 对照，保留真实 band | 0.6767 | 0.3113 | 0.3913 | 0.6757 | 0.6973 |
| `hachimi_no_real_difficulty_band`：保留 few-shot 对照，关真实 band | 0.6753 | 0.2662 | 0.3491 | 0.6545 | 0.6955 |
| `hachimi_no_difficulty_signal`：两个都关 | 0.6937 | 0.2927 | 0.3378 | 0.6958 | 0.7147 |

现象很清楚：

- 两个 difficulty 信号都关掉后，`consistency` 最高，达到 `0.6937`；
- 两个 difficulty 信号都开时，`item_P / item_S` 最高；
- 只保留 few-shot 对照、关掉真实 band 时，`item_P` 掉得最明显；
- 只关 few-shot 对照、保留真实 band 时，`item_S` 基本还能保住。

这说明：

> difficulty 信号主要帮助 item-level 难度结构，但会伤害 student-item 个体层面的 consistency。

更直接地说，模型一旦看到题目难度 band，就更容易按“这题整体难不难”去判断，而不是完全根据这个学生遇到这道题的状态来判断。

这对 item-level correlation 有帮助，但对 `overall_consistency` 不一定有帮助。

结论：

> difficulty 信号是条件必要模块，不是无条件必要模块。

如果主目标是 `overall_consistency`，当前最强候选反而是 `hachimi_no_difficulty_signal`。  
如果主目标是 `item_P / item_S`，baseline 仍然最好。

后续不应该再把 difficulty 当成一个整体模块讨论。  
必须拆成：

- few-shot 难度对照；
- 直接真实难度 band；
- 两者都不用。

---

## 8. 第四结论：state-step 不一定比 state-single 全面更好

对比多步和单步：

| 对比 | consistency | item_P | student_P |
|---|---:|---:|---:|
| `baseline_hachimi_state_step` | 0.6703 | 0.3469 | 0.6757 |
| `hachimi_state_single` | 0.6653 | 0.3041 | 0.6898 |
| `history_only_state_step` | 0.6752 | 0.2912 | 0.6606 |
| `history_only_state_single` | 0.6717 | 0.2726 | 0.7087 |

多步 state-step 的优势主要在 `item_P / item_S`。  
但在 `student_P / student_S` 上，单步版本反而更好。

这说明：

> 多步生成确实有用，但它的作用不是全面提升所有指标。

它更像是在帮助模型保留题目层面的难度结构。  
如果目标转向“学生之间强弱差异”，单步版本可能更干净。

结论：

> state-step 是条件必要模块。

不能简单删，但也不能继续默认它一定优于 state-single。

---

## 9. 第五结论：最终回答人称不能随便改

`hachimi_third_person_response` 的结果很差：

| variant | acc | consistency | item_P | student_P |
|---|---:|---:|---:|---:|
| baseline | 0.6939 | 0.6703 | 0.3469 | 0.6757 |
| `hachimi_third_person_response` | 0.5634 | 0.5852 | 0.3162 | 0.6764 |

学生层级相关性几乎没变，但 accuracy 和 consistency 大幅下降。

这说明第三人称可以用于内部状态判断，但最终学生答案仍应保持学生作答形式。

结论：

> 内部第三人称，外部第一人称，这个边界必须保留。

不要把“第三人称状态层”误解成“最终回答也写第三人称”。

---

## 10. 模块必要性分类

| 模块 | 当前结论 | 理由 |
|---|---|---|
| 第三人称状态层 | 必要 | direct variants 全面明显下降 |
| `StudentItemInteractionDecision` | 必要 | 它是 direct 与 state 路线的核心差别之一 |
| `ItemResponseState + ConstraintBundle` | 必要 | 状态边界缺失后 student/item 指标大幅掉 |
| 最终第一人称学生回答 | 必要 | 第三人称最终回答使 consistency 大幅下降 |
| Hachimi persona | 条件必要 | 保 item-level 有用，但 consistency 不依赖它 |
| few-shot 难度对照 | 条件必要 | 单独保留时不够强，和真实 band 一起最保 item-level |
| 真实 difficulty band | 条件必要/当前有害 | 保 item-level 有用，但对 consistency 有明显伤害 |
| 全部 difficulty 信号 | 条件必要 | item-level 目标下有用，consistency 目标下应关掉 |
| state-step generation | 条件必要 | 保 item-level 有用，但 student-level 不一定最优 |
| `StudentModel` | 暂不单独定论 | 本轮没有单独绕开它，只能证明状态链整体必要 |
| `StudentInternalSignals` | 条件必要 / 可简化 | consistency 小幅提升，但 student_P/student_S 下降 |
| `ProblemRequirementProfile` | 暂不单独定论 | 本轮没有单独绕开它，但 item-level 结果说明题目层对象仍重要 |

---

## 11. 当前最小有效链路候选

本轮不能只按最高 `consistency` 选主线。  
不同目标下，候选链路不同。

### 11.1 平衡型主线

`baseline_hachimi_state_step`

优点：

- `item_P = 0.3469`，本轮最高；
- `item_S = 0.3990`，本轮最高；
- `student_P/S` 稳定；
- `consistency = 0.6703`，虽不是最高，但没有明显落后。

适合继续作为“综合主线”。

### 11.2 consistency 优先候选

`hachimi_no_difficulty_signal`

优点：

- `consistency = 0.6937`，本轮最高；
- `acc = 0.7326`，本轮最高；
- `student_P = 0.6958`，高于 baseline；
- `student_S = 0.7147`，高于 baseline。

缺点：

- `item_P` 从 `0.3469` 降到 `0.2927`；
- `item_S` 从 `0.3990` 降到 `0.3378`。

如果后续目标是把 consistency 再往上拉，可以重点研究这个版本。

### 11.3 简化链路候选

`history_only_state_single`

优点：

- 不用 Hachimi；
- 不用多步 state-step；
- `consistency = 0.6717`，略高于 baseline；
- `student_P = 0.7087`，本轮最高；
- `student_S = 0.7152`，本轮最高。

缺点：

- `item_P = 0.2726`，题目层结构损失明显。

如果老师追问“最简方法能到什么程度”，这个版本很重要。

---

## 12. 下一步建议

下一轮不要继续盲目扩组合。  
应该做三件事：

1. **字段级审计**
   - 看 `StudentModel`、`StudentInternalSignals`、`ProblemRequirementProfile` 里哪些字段真的被用上；
   - 删除只写出来但不影响判断的字段。

2. **重做 difficulty anchor 的用法**
   - 不要把 few-shot 难度对照和真实 difficulty band 混成一个模块；
   - 如果主目标是 consistency，先使用 `hachimi_no_difficulty_signal`；
   - 如果必须保 item-level，再研究如何只把难度用于题目画像，而不进入学生会不会做对的硬判断。

3. **对比两个候选主线**
   - 综合主线：`baseline_hachimi_state_step`
   - consistency 主线：`hachimi_no_difficulty_signal`
   - 简化主线：`history_only_state_single`
   - 重点看它们在学生分组、题目分组上的误差来源。

---

## 13. 最终结论

本轮最重要的结论是：

> XES 强模型 harness 的核心不是 Hachimi，也不是 difficulty 信号，而是第三人称状态层。

更具体地说：

- direct 路线必须放弃；
- 内部第三人称状态层必须保留；
- 最终输出仍必须是学生式第一人称回答；
- Hachimi、difficulty 信号、state-step 都是条件必要模块，不是无条件必要模块；
- 当前 baseline 仍是最好的 item-level 综合版本；
- 如果优先拉 `overall_consistency`，当前最强候选是 `hachimi_no_difficulty_signal`。

所以后续 XES 侧的工作重点应该从“加模块”转为：

> 保留状态层，压缩外围模块，找最小有效链路。

---

## 14. 已执行的主线更新

根据补充实验，XES 强模型主线已经移除 difficulty 信号。

第一块独立 revisit 报告：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_revisit_block1_difficulty_signal_20260512.md`

具体含义是：

- 默认不传 `difficulty_anchor_context`；
- 默认不传 `real_difficulty_band`；
- 保留相关命令行开关，只用于复现实验和做对照；
- 主线 generation path 只使用学生历史/画像、题面、题目结构画像和第三人称状态层。

对应代码更新：

- `D:\Study\sii\MathStudent\xes\run_student_conditioned_benchmark.py`
- `D:\Study\sii\MathStudent\xes\src\student_conditioned_benchmark.py`

当前主线候选从原来的 `baseline_hachimi_state_step` 更新为：

> `hachimi_no_difficulty_signal`

它在本轮 60×96 common-test 上的结果是：

- `accuracy = 0.7326`
- `overall_consistency = 0.6937`
- `student_P = 0.6958`
- `student_S = 0.7147`
- `item_P = 0.2927`
- `item_S = 0.3378`

这不是说 difficulty 信息永远没用。  
它仍然可以用于 item-level 分析、离线解释和消融对照。  
但它不再进入当前 XES 强模型主线的默认生成路径。

---

## 15. 后续 revisit 顺序

第一块已经完成：

1. difficulty 信号
   - 结论：从默认 generation path 移除。

接下来建议按这个顺序继续：

2. `StudentInternalSignals`
   - 结论：不是强必要模块；
   - full signals 对 consistency 有小幅帮助；
   - no-signals 对 student_P/student_S 更好。

3. `StudentModel` 字段
   - 重点区分硬字段和软字段；
   - `math_task_capability_profile` 进入硬判断，优先保留；
   - 自我效能、SRL、control-value 等需要字段级验证。

4. `ProblemRequirementProfile` 字段
   - 操作复杂度、抽象度、作答格式等进入硬判断；
   - justification / notes 可能只是解释性字段。

5. `state-step` 生成
   - 继续比较多步状态生成和单步状态生成；
   - 重点判断是否值得为了 item-level 保留复杂度。

第二块独立 revisit 报告：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_revisit_block2_internal_signals_20260512.md`

---

## 16. 2026-05-13 全序列更新

第二轮顺序跑完了 12 个主实验，完整总结见：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_revisit_full_sequence_20260513.md`

这轮最重要的新结论有三条：

1. `StudentInternalSignals` 不是强必要模块
   - 去掉后 `consistency` 只小幅下降
   - 但 `student_P / student_S` 明显上升

2. `StudentItemInteractionDecision` 不能删
   - 虽然删掉后表面 `accuracy / consistency` 升高
   - 但 `item_P` 和 `student_P` 近乎崩掉
   - 说明那不是更好的学生模拟，而是更粗的统一作答

3. 当前默认 `ConstraintBundle` 太紧
   - `hachimi_no_difficulty_signal_loose_constraints` 成了这轮里最强的新候选
   - `consistency = 0.7134`
   - `item_P = 0.2899`
   - `student_P = 0.7080`
   - `student_S = 0.7404`

因此，这份总审计报告的当前更新结论是：

> XES strong harness 后续 revisit 的第一优先级，已经从“继续删外围模块”切到“重做 ConstraintBundle 的约束强度”。
