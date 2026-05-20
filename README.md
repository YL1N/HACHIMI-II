# HACHIMII

HACHIMII 不是单一任务脚本集合，而是一套**面向学生模拟的元方法实现仓库**。

我们的核心思想是：

> 先做第三人称状态建模，再在状态边界内生成下一步学生行为。

它既能用于：

- **静态模拟**：单题、单步学生作答；
- **动态模拟**：多轮、逐步推进的学生交互。

---

## 1. 先看什么

如果你是第一次来到这个仓库，建议按这个顺序看：

1. 元方法总说明：[META_METHOD_GUIDE.md](META_METHOD_GUIDE.md)
2. 静态方法介绍：[STATIC_SIMULATION_GUIDE.md](STATIC_SIMULATION_GUIDE.md)
3. 动态方法介绍：[DYNAMIC_SIMULATION_GUIDE.md](DYNAMIC_SIMULATION_GUIDE.md)

---

## 2. 仓库里有什么

### `xes/`

XES 是这套元方法在**静态单题学生模拟**上的应用。

关注：

- 方法介绍：[STATIC_SIMULATION_GUIDE.md](STATIC_SIMULATION_GUIDE.md)
- XES 最终版说明：[xes/reports/xes_strong_harness_manual_20260512.md](xes/reports/xes_strong_harness_manual_20260512.md)
- 设计依据（内部阅读）：[xes/reports/xes_strong_harness_revisit_final_report_20260513.md](xes/reports/xes_strong_harness_revisit_final_report_20260513.md)

### `eedi/`

EEDI 是这套元方法在**动态 turn-level 学生交互模拟**上的应用。

关注：

- 方法介绍：[DYNAMIC_SIMULATION_GUIDE.md](DYNAMIC_SIMULATION_GUIDE.md)
- EEDI 最终版说明：[eedi/reports/eedi_strong_harness_manual_20260512.md](eedi/reports/eedi_strong_harness_manual_20260512.md)
- 设计依据（内部阅读）：[eedi/reports/eedi_strong_revisit_final_decision_20260519.md](eedi/reports/eedi_strong_revisit_final_decision_20260519.md)

---

## 3. 这套元方法的通用接口

不管任务是静态还是动态，我们都尽量按同一骨架做：

`Context -> State -> Constraint -> Action`

含义是：

- `Context`：当前时点真实可见的信息；
- `State`：第三人称状态判断；
- `Constraint`：把状态翻译成生成边界；
- `Action`：当前这一步学生行为。

如果你要把这套思想迁移到别的任务，优先看：

- [META_METHOD_GUIDE.md](META_METHOD_GUIDE.md)

---

## 4. 方法边界

我们明确不做下面这些事：

- 直接 role-play 学生；
- 跳过第三人称状态层；
- 把评测标签塞回生成链；
- 用题号或学生号做特判；
- 靠后处理修答案。

---

## 5. 一句话理解本仓库

这个仓库记录的不是“两套互不相干的代码”，而是：

> 同一套学生模拟元方法，分别在静态任务和动态任务上的两种实现。
