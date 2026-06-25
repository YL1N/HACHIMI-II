<p align="center">
  <img src="figures/xilin_poem_xingshu.svg" alt="横看成岭侧成峰，远近高低各不同。不识庐山真面目，只缘身在此山中。——苏轼《题西林壁》" width="720">
</p>

<p align="center"><sub>横看成岭侧成峰，远近高低各不同。不识庐山真面目，只缘身在此山中。——苏轼《题西林壁》</sub></p>

<p align="center"><b>简体中文</b> · <a href="README.en.md">English</a></p>

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
2. Codex / agent 迁移手册：`AGENT_META_METHOD_PLAYBOOK.md`
3. 总方法报告：`reports/hachimii_meta_method_report_20260601.md`
4. 静态方法介绍：`STATIC_SIMULATION_GUIDE.md`
5. 动态方法介绍：`DYNAMIC_SIMULATION_GUIDE.md`
6. 多数据集扩展计划：`DATASET_EXPANSION_PLAN.md`

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

---

## 庐山之喻

> 横看成岭侧成峰，远近高低各不同。
> 不识庐山真面目，只缘身在此山中。

这首诗就是 HACHIMII 的方法论隐喻。

- **横看成岭侧成峰，远近高低各不同**：同一个学生，从不同视角看会呈现不同面貌——题目作答是一种切面，辅导对话是另一种切面，能力水平、错误结构、知识掌握各成一"峰"。任何单一视角都只是局部。
- **不识庐山真面目，只缘身在此山中**：直接让模型以第一人称"扮演"学生，就是"身在此山中"——模型困在自己的能力与视角里，生成的是它自己的影子（能力泄露），看不清学生的真实面目。

HACHIMII 的做法，是先跳出山来：**第三人称地把学生建模成一个状态**，从外部勾勒出"庐山"的轮廓边界，再回到山中、在这条边界之内生成当下这一步的学生行为。先识其真面目，再落其一峰一岭。
