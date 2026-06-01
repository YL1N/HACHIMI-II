# XES 强模型 Harness Revisit 实验 TODO 与运行配置（2026-05-12）

## 1. 目标

这轮实验只服务一个问题：

> XES 强模型 harness 里哪些模块真的必要，哪些可以简化，哪些可能有害？

这不是为了找一个临时最高分 prompt。  
判断标准是：方法链更短、更清楚，同时核心指标不明显下降。

---

## 2. TODO List

### TODO 1：固定基准设置

先把所有实验锁在同一批样本上。

- 固定 cohort：`D:\Study\sii\MathStudent\xes\configs\common_test_60x96_20260507.json`
- 学生数：`60`
- 每个学生测试题：`96`
- 历史题数：`30`
- 抽样种子：`42`
- 并发：`50`
- 模型：`qwen`
- 输出根目录：`D:\Study\sii\MathStudent\xes\outputs\xes_strong_ablation_60x96_20260512`

这样每个 variant 面对的是同一批学生、同一批题，差异才主要来自 harness 模块。

### TODO 2：先跑单模块消融

第一轮只看单个模块拿掉或替换后的影响。

要跑的 variant：

| variant | 改动 | 验证点 |
|---|---|---|
| `baseline_hachimi_state_step` | 当前主线 | 基准 |
| `history_only_state_step` | 去掉 Hachimi，只用 XES 历史 | Hachimi 是否必要 |
| `hachimi_direct` | 去掉第三人称状态生成链，直接生成 | 状态层是否必要 |
| `hachimi_state_single` | 多步状态生成改成单步状态生成 | state-step 是否必要 |
| `hachimi_no_difficulty_anchor` | 去掉 difficulty anchor | 难度锚点是否必要 |
| `hachimi_third_person_response` | 输出人称从第一人称改第三人称 | 回答人称是否影响指标 |

### TODO 3：再跑组合消融

第二轮看模块之间有没有组合效应。

要跑的 variant：

| variant | 组合 | 验证点 |
|---|---|---|
| `history_only_direct` | 无 Hachimi + direct | 极简链路下限 |
| `history_only_state_single` | 无 Hachimi + 单步状态生成 | Hachimi 是否只在多步链里有用 |
| `history_only_no_difficulty_anchor` | 无 Hachimi + 无 difficulty anchor | 难度锚点是否依赖 Hachimi |
| `hachimi_direct_no_difficulty_anchor` | 有 Hachimi + direct + 无 difficulty anchor | 状态层和难度锚点是否共同贡献 |
| `hachimi_state_single_no_difficulty_anchor` | 有 Hachimi + 单步 + 无 difficulty anchor | 多步生成是否依赖难度锚点 |
| `history_only_direct_no_difficulty_anchor` | 无 Hachimi + direct + 无 difficulty anchor | 最小强模型链路下限 |

### TODO 4：汇总指标

每轮跑完后都生成汇总报告：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md`

重点看：

1. `overall_consistency`
2. `student_P`
3. `student_S`
4. `item_P`
5. `item_S`
6. `failure_rate`

accuracy 只作为辅助指标。  
如果 accuracy 高了但 consistency 或相关性掉了，不算方法更好。

### TODO 5：写模块必要性审计报告

最后写：

- `D:\Study\sii\MathStudent\xes\reports\xes_strong_harness_module_necessity_audit_20260512.md`

每个模块给四类结论之一：

- 必要：拿掉明显变差；
- 条件必要：只在某些组合里有用；
- 冗余：拿掉变化很小；
- 有害：拿掉反而更好。

---

## 3. 运行配置

主脚本：

- `D:\Study\sii\MathStudent\xes\run_strong_harness_ablation_60x96_20260512.ps1`

汇总脚本：

- `D:\Study\sii\MathStudent\xes\summarize_strong_ablation_60x96.py`

核心参数已经写进 PowerShell 脚本：

| 参数 | 值 |
|---|---|
| `max_students` | `60` |
| `history_size` | `30` |
| `test_size` | `96` |
| `sampling_seed` | `42` |
| `fixed_cohort_path` | `configs/common_test_60x96_20260507.json` |
| `official_correctness_mode` | `rules_only` |
| `max_concurrency` | `50` |
| `llm_model` | `qwen` |
| `llm_temperature` | `0.2` |
| `llm_max_tokens` | `2000` |
| `llm_response_format_json` | 开启 |

---

## 4. 具体怎么跑

### 4.1 推荐顺序

不要一口气先跑所有组合。  
推荐顺序是：

1. 跑 baseline；
2. 跑单模块消融；
3. 汇总一次；
4. 根据结果跑组合消融；
5. 再汇总；
6. 写必要性结论。

### 4.2 只跑 baseline

在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\xes\run_strong_harness_ablation_60x96_20260512.ps1 -MaxConcurrency 50 -Variants baseline_hachimi_state_step
```

### 4.3 跑第一轮单模块消融

```powershell
powershell -ExecutionPolicy Bypass -File .\xes\run_strong_harness_ablation_60x96_20260512.ps1 -MaxConcurrency 50 -Variants baseline_hachimi_state_step,history_only_state_step,hachimi_direct,hachimi_state_single,hachimi_no_difficulty_anchor,hachimi_third_person_response
```

### 4.4 汇总第一轮结果

```powershell
python .\xes\summarize_strong_ablation_60x96.py
```

### 4.5 跑第二轮组合消融

```powershell
powershell -ExecutionPolicy Bypass -File .\xes\run_strong_harness_ablation_60x96_20260512.ps1 -MaxConcurrency 50 -Variants history_only_direct,history_only_state_single,history_only_no_difficulty_anchor,hachimi_direct_no_difficulty_anchor,hachimi_state_single_no_difficulty_anchor,history_only_direct_no_difficulty_anchor
```

### 4.6 汇总全部结果

```powershell
python .\xes\summarize_strong_ablation_60x96.py
```

### 4.7 如果确认要全量一次跑完

不传 `-Variants` 就会跑脚本里的全部 variant：

```powershell
powershell -ExecutionPolicy Bypass -File .\xes\run_strong_harness_ablation_60x96_20260512.ps1 -MaxConcurrency 50
```

---

## 5. 输出位置

每个 variant 会输出到：

```text
D:\Study\sii\MathStudent\xes\outputs\xes_strong_ablation_60x96_20260512\<variant>\run_*
```

日志会输出到：

```text
D:\Study\sii\MathStudent\xes\outputs\xes_strong_ablation_60x96_20260512\_logs
```

汇总报告会输出到：

```text
D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md
```

---

## 6. 判断规则

以 `baseline_hachimi_state_step` 为基准。

初筛规则：

- `overall_consistency` 下降超过 `0.02`：该模块倾向于有贡献；
- `student_P/S` 明显下降：该模块对学生差异建模有贡献；
- `item_P/S` 明显下降：该模块对题目难度结构有贡献；
- 指标几乎不变：该模块可能冗余；
- 指标反而上升：该模块可能有害或实现方式不佳。

这里的 `0.02` 只是第一轮筛查阈值，不是最终显著性结论。

---

## 7. 不作弊约束

本轮实验必须遵守：

- generation path 不使用真实测试题正确标签；
- 不使用真实学生测试作答内容；
- 不按学生 ID 或题目 ID 特判；
- 不根据评测结果后处理答案；
- 固定 cohort 只用于保证不同 variant 面对同一批样本；
- 指标只在生成完成后离线计算。

---

## 8. 最终交付物

这轮 revisit 最后应该交付三份东西：

1. `D:\Study\sii\MathStudent\xes\reports\xes_strong_ablation_results_20260512.md`
   - 实验指标表；

2. `D:\Study\sii\MathStudent\xes\reports\xes_strong_harness_module_necessity_audit_20260512.md`
   - 模块必要性结论；

3. 如有必要，更新 `D:\Study\sii\MathStudent\xes\reports\xes_strong_harness_manual_20260512.md`
   - 把最终保留下来的最小有效链路写回方法说明书。

