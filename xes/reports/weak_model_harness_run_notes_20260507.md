# XES 弱模型 Harness 运行补充说明（2026-05-07）

## 1. 这份补充说明写什么

这份文档只补三件和运行稳定性有关的事情：

1. `task_support_profiles` 现在支持增量落盘
2. 全量实验现在支持 `--resume_run_dir` 续跑
3. `support_profile` 的 schema repair 更稳了

这些改动不改变方法边界，也不改变“强模型只做上游编译、弱模型在线作答”的职责划分。

---

## 2. 本次涉及的代码

- `D:\Study\sii\MathStudent\xes\weak_model_harness\src\support_profile.py`
- `D:\Study\sii\MathStudent\xes\weak_model_harness\run_weak_student_benchmark.py`

---

## 3. 这次具体补了什么

### 3.1 `task_support_profiles` 增量落盘

以前这里是整批算完才一次性写盘。

问题是：

- 独立题目数一多，这一步会跑很久
- 中途如果炸掉，前面已经编译好的结果全丢
- 外部看起来像“卡住”，不方便盯进度

现在改成：

- 每成功编译一题，就把当前 `task_support_profiles.partial.json` 写出来
- 全部完成后，再写正式的 `task_support_profiles.json`

这样做的作用很直接：

- 失败不会把前面成果全部丢掉
- 可以看到它到底已经推进到哪了

### 3.2 `--resume_run_dir` 续跑

现在全量实验中断后，可以直接从已有 run 目录继续跑。

这意味着：

- 已有的 `benchmark_summary.json`
- 已有的 `problem_profiles.json`
- 已有的 `task_support_profiles.json`
- 已有的 `student_models.jsonl`
- 已有的 `predictions.jsonl`

都会被复用，不需要从头再来。

这次 `3b` 和 `7b` 的提速续跑，就是这么做的。

### 3.3 更稳的 schema repair

`src/support_profile.py` 里现在补了两层稳定性：

1. 更稳的枚举值规范化
2. 失败后的 repair 重试

它解决的是这样一类问题：

- 上游强模型明明理解了题目
- 但把一个字段的合法值写到了另一个字段里
- 结果不是“方法错”，而是“schema 炸”

现在这类错误更容易被修正，而不是直接让整轮全量实验报废。

---

## 4. 运行时现在能看到什么

全量日志里至少会看到两类进度：

- `task_support_profile built`
- `prediction progress`

所以现在一轮实验不再是黑箱长跑。

---

## 5. 这几项改动的意义

这几项改动解决的是运行问题，不是结果问题。

更准确地说，它们证明了两件事：

1. 当前 weak-model harness 已经能稳定跑完整量实验
2. 如果结果不好，那就是方法本身还不够好，不再是脚本没跑稳
