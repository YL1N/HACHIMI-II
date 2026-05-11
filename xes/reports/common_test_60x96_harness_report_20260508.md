# XES common-test harness report

## 实验设置

- 样本：60名学生，poor/low/medium/high 各15名。
- 测试：96道共同测试题，所有指标只在这96题上计算。
- 历史：每名学生30道非测试题历史，按个人时间序列三段均匀取样。
- 固定样本配置：`D:\Study\sii\MathStudent\xes\configs\common_test_60x96_20260507.json`

## 核心指标

| run | acc | item_P | item_S | student_P | student_S | overall_consistency |
|---|---|---|---|---|---|---|
| strong+hachimi | 0.7007 | 0.3013 | 0.3298 | 0.6782 | 0.6984 | 0.6767 |
| strong history only | 0.6988 | 0.2988 | 0.3433 | 0.6601 | 0.6680 | 0.6700 |
| weak 1.7b | 0.2672 | 0.1359 | 0.1920 | -0.2681 | -0.2008 | 0.3582 |
| weak 3b | 0.2347 | 0.3124 | 0.3954 | 0.1561 | 0.1178 | 0.3538 |
| weak 7b | 0.3205 | 0.2085 | 0.2031 | -0.0995 | -0.1163 | 0.4035 |

## 四档 Consistency

| run | poor | low | medium | high |
|---|---|---|---|---|
| strong+hachimi | 0.5813 | 0.6194 | 0.7042 | 0.8021 |
| strong history only | 0.5847 | 0.6243 | 0.6882 | 0.7826 |
| weak 1.7b | 0.4271 | 0.3701 | 0.3347 | 0.3007 |
| weak 3b | 0.4382 | 0.3590 | 0.3236 | 0.2944 |
| weak 7b | 0.4437 | 0.4062 | 0.3944 | 0.3694 |

## 指标说明

- `acc`：模型实际做对题数 / 总题数，也就是整体预测正确率。
- `item_P / item_S`：题目正确率与真实题目正确率的 Pearson / Spearman。
- `student_P / student_S`：学生个人正确率与真实学生个人正确率的 Pearson / Spearman。
- `overall_consistency`：先对每个学生算逐题对错一致率，再对全部学生取平均。

## 五组模型预测分数

| run | pred_accuracy | pred_score_96 |
|---|---|---|
| strong+hachimi | 0.7007 | 67.2667 |
| strong history only | 0.6988 | 67.0833 |
| weak 1.7b | 0.2672 | 25.6500 |
| weak 3b | 0.2347 | 22.5333 |
| weak 7b | 0.3205 | 30.7667 |

## 五组模型四档预测分数

| run | poor_acc | poor_score | low_acc | low_score | medium_acc | medium_score | high_acc | high_score |
|---|---|---|---|---|---|---|---|---|
| strong+hachimi | 0.5965 | 57.2667 | 0.6285 | 60.3333 | 0.7493 | 71.9333 | 0.8285 | 79.5333 |
| strong history only | 0.6014 | 57.7333 | 0.6389 | 61.3333 | 0.7389 | 70.9333 | 0.8160 | 78.3333 |
| weak 1.7b | 0.2771 | 26.6000 | 0.2625 | 25.2000 | 0.2632 | 25.2667 | 0.2660 | 25.5333 |
| weak 3b | 0.2326 | 22.3333 | 0.2319 | 22.2667 | 0.2354 | 22.6000 | 0.2389 | 22.9333 |
| weak 7b | 0.3271 | 31.4000 | 0.3194 | 30.6667 | 0.3118 | 29.9333 | 0.3236 | 31.0667 |

## 真实学生分数参考

- 共同测试总题数：96。
- 真实学生总体平均正确率：`0.8306`
- 真实学生总体平均分：`79.7333 / 96`

| 档次 | 真实正确率 | 真实平均分(96题制) |
|---|---|---|
| poor | 0.7125 | 68.4000 |
| low | 0.8174 | 78.4667 |
| medium | 0.8604 | 82.6000 |
| high | 0.9319 | 89.4667 |

## 输出位置

- strong+hachimi: `D:\Study\sii\MathStudent\xes\outputs\common_test_60x96\strong_hachimi\run_20260507_171156`
- strong history only: `D:\Study\sii\MathStudent\xes\outputs\common_test_60x96\strong_history_only\run_20260507_190056`
- weak 1.7b: `D:\Study\sii\MathStudent\xes\outputs\common_test_60x96\weak_qwen3_1_7b\run_20260507_235850`
- weak 3b: `D:\Study\sii\MathStudent\xes\outputs\common_test_60x96\weak_qwen2_5_3b\run_20260508_012325`
- weak 7b: `D:\Study\sii\MathStudent\xes\outputs\common_test_60x96\weak_qwen2_5_7b\run_20260508_023633`
- case dump: `D:\Study\sii\MathStudent\xes\outputs\common_test_60x96\case_dumps\weak_student_15745_question_1456.json`
