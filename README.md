<p align="center">
  <img src="figures/xilin_poem_xingshu.svg" alt="横看成岭侧成峰，远近高低各不同。不识庐山真面目，只缘身在此山中。——苏轼《题西林壁》" width="640">
</p>

<p align="center"><sub>横看成岭侧成峰，远近高低各不同。不识庐山真面目，只缘身在此山中。——苏轼《题西林壁》</sub></p>

<p align="center"><b>简体中文</b> · <a href="README.en.md">English</a></p>

<h1 align="center">HACHIMI-II</h1>

<p align="center">
  一套面向<b>学生模拟</b>的元方法实现仓库，用第三人称状态建模对抗大模型的「能力泄露」。
</p>

<p align="center">
  <a href="#快速开始"><img src="https://img.shields.io/badge/Python-3.13-blue" alt="Python"></a>
  <a href="#数据集与任务"><img src="https://img.shields.io/badge/datasets-5-success" alt="datasets"></a>
  <a href="#方法边界"><img src="https://img.shields.io/badge/paradigm-third--person%20state-orange" alt="paradigm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="license"></a>
</p>

---

## 这是什么

当你直接让大模型「扮演一个学生」去答题或对话时，模型给出的往往是**它自己**会怎么答——准确、流畅、几乎不犯真实学生会犯的错。模拟出来的「学生」既不复现真实学生的能力水平，也不复现真实学生的错误结构。我们称之为**能力泄露（competence leakage）**。

HACHIMI-II 不是一组各自为政的数据集脚本，而是**一套统一的学生模拟元方法**，它的核心主张是：

> **先在第三人称视角把学生建模成一个状态，再在该状态的边界之内生成当前这一步的学生行为。**

先从山外看清「庐山」的轮廓，再回到山中落下这一笔——而不是一上来就「身在此山中」。

它在两类任务上实例化：

- **静态模拟**：单题、单步的学生作答（数学与自然科学）；
- **动态模拟**：多轮、逐步推进的辅导对话。

---

## 核心结果

在 5 个数据集上，HACHIMI-II 同时压住能力泄露并复现真实学生的错误结构（全部指标从 per-sample 记录重算）。

**静态题目作答**——同时取得最高对错一致率、最小逐学生正确率分布距离（W₁）、最高学生排序相关：

| 数据集 | Agree ↑ | W₁ ↓ | Student ρ ↑ | 最强 baseline W₁ |
|---|---|---|---|---|
| XES3G5M | **0.752** | **0.039** | **0.691** | 0.327 |
| Eedi | **0.606** | **0.046** | **0.703** | 0.119 |
| ENEM | **0.630** | **0.169** | **0.668** | 0.409 |

> baseline 的模拟正确率跟随模型自身能力，而非真实学生：ENEM 真实约 0.39 而 baseline 模拟约 0.82；XES3G5M 真实约 0.83 而 baseline 模拟约 0.50。HACHIMI-II 紧贴真实水平（ENEM 0.384、XES3G5M 0.828）。

**动态辅导对话**——已实现错误结构召回（SRec）数倍于最强 baseline：

| 数据集 | SRec ↑ (HACHIMI-II) | 最强 baseline SRec |
|---|---|---|
| Eedi QATD2k | **0.399** | ≤ 0.180 |
| Khan/CoMTA | **0.649** | ≤ 0.113 |

> 完整的功能一致性（κ_func / MCC_func）、错误状态指标（BAcc_err / MCC_err）、校准（Calib）与消融对照见 [`reports/core_ablation_20260611/component_analysis/`](reports/core_ablation_20260611/component_analysis/)。

---

## 数据集与任务

| 形态 | 目录 | 数据集 | 任务 |
|---|---|---|---|
| 静态 | `static/xes/` | XES3G5M | 数学题作答模拟 |
| 静态 | `static/eedi-static/` | Eedi | 数学诊断题模拟 |
| 静态 | `static/enem/` | ENEM | 自然科学跨学科作答模拟 |
| 动态 | `dynamic/eedi/` | Eedi / QATD2k | 辅导对话逐轮模拟 |
| 动态 | `dynamic/khan/` | Khan / CoMTA | 辅导对话迁移实验 |

---

## 快速开始

```bash
git clone https://github.com/ZeroLoss-Lab/HACHIMII-YL.git
cd HACHIMII-YL
pip install -r requirements.txt   # 核心 harness 仅需标准库；各子项目按需补充依赖
```

每个数据集自带独立入口、配置与报告。例如：

```bash
# 静态：XES3G5M 学生作答模拟
python static/xes/run_experiments.py

# 静态：ENEM 自然科学
python static/enem/run_enem_static_benchmark.py

# 动态：Eedi / QATD2k 辅导对话
python dynamic/eedi/run_eedi_experiments.py

# 动态：Khan / CoMTA
python dynamic/khan/run_khan_experiments.py
```

> 生成需要一个 OpenAI 兼容的 LLM 端点（通过各脚本的 `--llm_base_url` / `--llm_model` / `--llm_api_key` 指定）。各入口脚本的完整参数见 `--help`。

---

## 仓库结构

```text
static/
  xes/           # XES3G5M  静态数学做题模拟
  eedi-static/   # Eedi     静态数学诊断题模拟
  enem/          # ENEM     自然科学静态跨学科模拟
  baselines/     # 静态 baseline（Direct RP / Prompt-C / Profile-C）

dynamic/
  eedi/          # Eedi / QATD2k  动态辅导对话模拟
  khan/          # Khan / CoMTA   动态辅导对话迁移实验
  baselines/     # 动态 baseline（+ Agent-Mem）

reports/         # 实验报告与论文用结果（component analysis 等）
figures/         # 图与素材
```

原则：`static/` 与 `dynamic/` 按模拟形态隔离；每个数据集保留自己的入口、配置、报告与源码；不做顶层统一 wrapper；原始数据、缓存与实验输出不进 Git。

---

## 元方法通用接口

所有实例化共享同一套骨架：

```
Learner Context → Task / Interaction Context → Learner-Task Fit
                → State Layer → Harness / Constraint → Surface Realization
```

| 阶段 | 含义 |
|---|---|
| `Learner Context` | 这个学生是谁 |
| `Task / Interaction Context` | 当前任务或当前对话轮次是什么 |
| `Learner-Task Fit` | 这个学生遇到这个任务会怎样 |
| `State Layer` | 生成前的第三人称状态判断 |
| `Harness / Constraint` | 把状态翻译成生成边界 |
| `Surface Realization` | 当前一步的学生行为 |

迁移到新任务时，**不要先写 prompt**：先按这些坑位确定需要哪些信息，再用具体任务的教育理论去填。

---

## 文档导航

| 文档 | 内容 |
|---|---|
| [`META_METHOD_GUIDE.md`](META_METHOD_GUIDE.md) | 元方法总说明 |
| [`STATIC_SIMULATION_GUIDE.md`](STATIC_SIMULATION_GUIDE.md) | 静态模拟方法 |
| [`DYNAMIC_SIMULATION_GUIDE.md`](DYNAMIC_SIMULATION_GUIDE.md) | 动态模拟方法 |
| [`AGENT_META_METHOD_PLAYBOOK.md`](AGENT_META_METHOD_PLAYBOOK.md) | Codex / agent 迁移手册 |
| [`DATASET_EXPANSION_PLAN.md`](DATASET_EXPANSION_PLAN.md) | 多数据集扩展计划 |
| [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | 项目定位与边界 |

---

## 方法边界

明确**不做**：

- 不直接 role-play 学生；
- 不跳过第三人称状态层；
- 不把真实标签、未来回复、官方评测注释放进生成链；
- 不按题号或学生号做特判；
- 不靠后处理修改答案；
- 不靠「更像学生一点」的 prompt 补丁堆效果。

---

## 庐山之喻

> 横看成岭侧成峰，远近高低各不同。
> 不识庐山真面目，只缘身在此山中。

这首诗就是 HACHIMI-II 的方法论隐喻。

- **横看成岭侧成峰，远近高低各不同**：同一个学生，从不同视角看会呈现不同面貌——题目作答是一种切面，辅导对话是另一种切面，能力水平、错误结构、知识掌握各成一「峰」。任何单一视角都只是局部。
- **不识庐山真面目，只缘身在此山中**：直接让模型以第一人称「扮演」学生，就是「身在此山中」——模型困在自己的能力与视角里，生成的是它自己的影子（能力泄露），看不清学生的真实面目。

HACHIMI-II 的做法，是先跳出山来：**第三人称地把学生建模成一个状态**，从外部勾勒出「庐山」的轮廓边界，再回到山中、在这条边界之内生成当下这一步的学生行为。先识其真面目，再落其一峰一岭。

---

## 引用

如果本仓库对你的研究有帮助，欢迎引用（论文信息待补充）：

```bibtex
@misc{hachimi2,
  title  = {HACHIMI-II: Third-Person State Modeling for Student Simulation},
  author = {ZeroLoss Lab},
  year   = {2026},
  note   = {https://github.com/ZeroLoss-Lab/HACHIMII-YL}
}
```

## 许可

本项目以 [MIT 许可](LICENSE) 发布。
