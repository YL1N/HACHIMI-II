# HACHIMII

HACHIMII 不是单一数据集脚本集合，而是一套面向学生模拟的元方法实现仓库。

核心思想是：

> 先做第三人称状态建模，再在状态边界内生成当前一步学生行为。

它既可以用于：

- **静态模拟**：单题、单步学生作答；
- **动态模拟**：多轮、逐步推进的学生交互。

---

## 1. 先看什么

如果你第一次看这个仓库，建议按这个顺序：

1. 元方法总说明：`META_METHOD_GUIDE.md`
2. 总方法报告：`reports/hachimii_meta_method_report_20260601.md`
3. 静态方法介绍：`STATIC_SIMULATION_GUIDE.md`
4. 动态方法介绍：`DYNAMIC_SIMULATION_GUIDE.md`
5. 多数据集扩展计划：`DATASET_EXPANSION_PLAN.md`

---

## 2. 仓库结构

```text
static/
  xes/           # XES 静态数学做题模拟
  eedi-static/   # EEDI 静态数学诊断题模拟
  enem/          # ENEM 自然科学静态跨学科模拟

dynamic/
  eedi/          # EEDI / QATD2k 动态辅导对话模拟
  khan/          # Khan / CoMTA 动态辅导对话迁移实验
```

原则：

- `static/` 和 `dynamic/` 按模拟形态隔离；
- 每个数据集保留自己的入口、配置、报告和源码；
- 不做顶层统一 wrapper；
- 原始数据、缓存和实验输出不进 Git。

---

## 3. 元方法通用接口

HACHIMII 的通用骨架是：

`Learner Context -> Task / Interaction Context -> Learner-Task Fit -> State Layer -> Harness / Constraint -> Surface Realization`

含义：

- `Learner Context`：这个学生是谁；
- `Task / Interaction Context`：当前任务或当前对话轮次是什么；
- `Learner-Task Fit`：这个学生遇到这个任务会怎样；
- `State Layer`：生成前的第三人称状态判断；
- `Harness / Constraint`：把状态翻译成生成边界；
- `Surface Realization`：当前一步学生行为。

迁移到新任务时，不要先写 prompt。先按这些坑位确定需要哪些信息，再用具体任务的教育理论去填。

---

## 4. 方法边界

明确不做：

- 不直接 role-play 学生；
- 不跳过第三人称状态层；
- 不把真实标签、未来回复、官方评测注释放进生成链；
- 不按题号或学生号做特判；
- 不靠后处理修改答案；
- 不靠“更像学生一点”的 prompt 补丁堆效果。

---

## 5. 一句话理解

这个仓库记录的是：

> 同一套学生模拟元方法，分别在静态做题、动态辅导对话、数学和自然科学任务上的实例化。

