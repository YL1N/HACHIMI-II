<p align="center">
  <img src="figures/xilin_poem_xingshu.svg" alt="横看成岭侧成峰，远近高低各不同。不识庐山真面目，只缘身在此山中。——苏轼《题西林壁》" width="820">
</p>

<p align="center"><sub>横看成岭侧成峰，远近高低各不同。不识庐山真面目，只缘身在此山中。——苏轼《题西林壁》</sub></p>

<p align="center"><b>简体中文</b> · <a href="README.en.md">English</a></p>

<h1 align="center">HACHIMI-II</h1>

<p align="center">
  从角色扮演到<b>学习者行为建模</b>：面向学生模拟的方法实现，用第三人称预测对抗大模型的「能力泄露」。
</p>

<p align="center">
  论文：<i>HACHIMI-II: From Role-Play to Learner Behavior Modeling for Faithful Student Simulation</i>
  （<a href="https://arxiv.org/abs/2610.19654">arXiv</a> · <a href="paper/HACHIMI-II.pdf">PDF</a>）
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2610.19654"><img src="https://img.shields.io/badge/arXiv-2610.19654-b31b1b" alt="arXiv"></a>
  <a href="#快速开始"><img src="https://img.shields.io/badge/Python-3.13-blue" alt="Python"></a>
  <a href="#数据集与任务"><img src="https://img.shields.io/badge/datasets-5-success" alt="datasets"></a>
  <a href="#方法边界"><img src="https://img.shields.io/badge/paradigm-third--person%20prediction-orange" alt="paradigm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="license"></a>
</p>

---

## 这是什么

当你直接让大模型「扮演一个学生」去答题或对话时，角色提示只给了一段学生描述，却没有刻画这个学生知道什么、此刻会怎么做，于是模型用**它自己**的能力去填补空白。结果是：模拟学生的能力水平由模型决定，学生之间几乎没有差别，真实学生会犯的错也很少被复现。我们称之为**能力泄露（competence leakage）**。

HACHIMI-II 的做法是**建模学习者的行为**，把学生模拟改写成对这个学习者下一步行为的**第三人称预测**：

> **先在第三人称视角刻画这个学生和他此刻的状态，再在该状态的边界之内生成当前这一步的学生行为。**

先从山外看清「庐山」的轮廓，再回到山中落下这一笔——而不是一上来就「身在此山中」。

它在两类任务上实例化：

- **题目作答模拟**：给定学生的作答历史和一道目标题，预测这个学生在这道题上的作答（数学与自然科学）；
- **辅导对话模拟**：给定已有的师生对话，只预测学生的下一轮回复。

---

## 核心结果

在 5 个数据集上，HACHIMI-II 同时压住能力泄露并复现真实学生的错误结构。

**题目作答**：同时取得最高对错一致率、最小逐学生正确率分布距离（W₁）、最高学生排序相关。

| 数据集 | Agree ↑ | W₁ ↓ | Student ρ ↑ | 最强 baseline W₁ |
|---|---|---|---|---|
| XES3G5M | **0.752** | **0.039** | **0.691** | 0.327 |
| Eedi | **0.606** | **0.046** | **0.703** | 0.119 |
| ENEM | **0.630** | **0.169** | **0.668** | 0.409 |

> baseline 的模拟正确率跟随模型自身能力，而非真实学生：ENEM 真实约 0.39 而 baseline 模拟约 0.82；XES3G5M 真实约 0.83 而 baseline 模拟约 0.50。HACHIMI-II 紧贴真实水平（ENEM 0.384、XES3G5M 0.828）。

**辅导对话**：完整复现真实错误（知识类型、错误环节、错误机制三项全部一致）的比例是最强 baseline 的 1.8 倍和 5.1 倍。

| 数据集 | Rec_struct ↑ | 最强 baseline Rec_struct | F1_err ↑ | 最强 baseline F1_err |
|---|---|---|---|---|
| Eedi QATD2k | **0.315** | 0.172 | **0.561** | 0.248 |
| Khan/CoMTA | **0.565** | 0.110 | **0.464** | 0.183 |

> 功能一致性（κ_func / MCC_func）、错误状态指标（BAcc_err / MCC_err）、错误结构（Prec_struct / F1_struct）以及三项消融（去除画像先验 / 学习者状态 / 行为约束）的完整结果见论文和 [`results/`](results/)。

---

## 数据集与任务

| 形态 | 目录 | 数据集 | 规模 | 任务 |
|---|---|---|---|---|
| 题目作答 | `static/xes/` | XES3G5M | 60 学生 × 96 题 | 小学数学作答模拟 |
| 题目作答 | `static/eedi-static/` | Eedi | 480 学生 × 107 题 | 数学诊断题模拟 |
| 题目作答 | `static/enem/` | ENEM 2024 | 7,200 学生 × 24 题 | 自然科学作答模拟 |
| 辅导对话 | `dynamic/eedi/` | Eedi QATD2k | 17,256 轮 | 辅导对话逐轮模拟 |
| 辅导对话 | `dynamic/khan/` | Khan/CoMTA | 917 轮 | 辅导对话逐轮模拟 |

数据集需从各自的公开来源获取，本仓库不再分发。

---

## 快速开始

```bash
git clone https://github.com/YL1N/HACHIMI-II.git
cd HACHIMI-II
pip install -r requirements.txt   # 核心流程只用标准库；部分评测组件需要 numpy 和 rouge_score
```

所有入口脚本都通过三个参数连接一个 OpenAI 兼容的对话接口：

```bash
--llm_base_url <https://your-endpoint/v1>
--llm_model    <model-name>
--llm_api_key  <api-key-or-dummy>
```

论文结果使用 Qwen3.5-397B 作为模拟主干、GPT-5.4 作为评测裁判，也可以换成任意 OpenAI 兼容的模型。

```bash
# 题目作答：XES3G5M
python static/xes/run_student_conditioned_benchmark.py --llm_base_url ... --llm_model ... --llm_api_key ...

# 题目作答：Eedi / ENEM
python static/eedi-static/run_eedi_static_benchmark.py --llm_base_url ... --llm_model ... --llm_api_key ...
python static/enem/run_enem_static_benchmark.py        --llm_base_url ... --llm_model ... --llm_api_key ...

# 辅导对话：Eedi QATD2k（主流程）
python dynamic/eedi/run_eedi_experiments.py --llm_base_url ... --llm_model ... --llm_api_key ...

# 辅导对话：Khan/CoMTA
python dynamic/khan/run_khan_experiments.py --llm_base_url ... --llm_model ... --llm_api_key ...
```

baseline 的入口是 `static/baselines/run_static_baselines.py` 和 `dynamic/baselines/run_dynamic_baselines.py`。所有入口都支持 `--dry_run`（或 `--prepare_only`），可以不联网先跑通。

---

## 仓库结构

```text
static/            题目作答模拟
  xes/             XES3G5M（含学生队列构建：题库筛选、Rasch 拟合）
  eedi-static/     Eedi 诊断题
  enem/            ENEM 2024 自然科学（文字题与图文题）
  baselines/       题目作答 baseline（Direct RP / Prompt-C / Profile-C）
dynamic/           辅导对话模拟
  eedi/            Eedi QATD2k（主流程）
  khan/            Khan/CoMTA
  baselines/       辅导对话 baseline（另含 Agent-Mem）
  evaluation/      由裁判标签重算对话指标
results/           与论文表格一一对应的指标汇总
paper/             论文 PDF
figures/           README 素材
```

原则：题目作答与辅导对话按模拟形态隔离；每个数据集保留自己的入口、配置与源码；原始数据、缓存与实验输出不进 Git。

---

## 方法骨架

两类任务共享同一套四步流程：

```
学生模型 → 学习者状态 → 行为约束编译 → 约束下生成与检查
```

| 步骤 | 含义 |
|---|---|
| 学生模型 | 这个学生是谁：由可见历史汇总出的画像，并匹配一条 HACHIMI-1M 学生画像作为先验 |
| 学习者状态 | 这个学生面对当前题目或当前这轮对话会怎样：可达知识、活跃的错误模式、作答把握、本轮的交互动作 |
| 行为约束编译 | 用固定映射把状态翻译成生成边界：可用知识与推理深度、需要保留的错误、不确定程度、回复形式与步数 |
| 约束下生成与检查 | 在边界之内写出这一步的学生行为，违反约束就重新生成 |

迁移到新任务时，**不要先写 prompt**：先按这些步骤确定需要哪些信息，再用具体任务的教育理论去填。

---

## 文档导航

| 文档 | 内容 |
|---|---|
| [`STATIC_SIMULATION_GUIDE.md`](STATIC_SIMULATION_GUIDE.md) | 题目作答模拟的方法链、数据边界与各数据集参数 |
| [`DYNAMIC_SIMULATION_GUIDE.md`](DYNAMIC_SIMULATION_GUIDE.md) | 辅导对话模拟的方法链、数据边界与各数据集参数 |
| [`README.en.md`](README.en.md) | 英文说明，含 `results/` 中各指标的定义 |
| 各子目录的 `README.md` | 对应数据集或 baseline 的运行说明 |
| [`paper/HACHIMI-II.pdf`](paper/HACHIMI-II.pdf) | 论文全文，附录给出了对话流程的 prompt |

---

## 方法边界

明确**不做**：

- 不直接 role-play 学生；
- 不跳过第三人称的学习者状态；
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

如果本仓库对你的研究有帮助，欢迎引用：

```bibtex
@article{jiang2026hachimiii,
  title   = {{HACHIMI-II}: From Role-Play to Learner Behavior Modeling for Faithful Student Simulation},
  author  = {Jiang, Yilin and Tan, Fei and Yin, Xuanyu and Leng, Jing and Zhou, Aimin},
  journal = {arXiv preprint arXiv:2610.19654},
  year    = {2026}
}
```

学生画像先验来自 HACHIMI-1M：

```bibtex
@inproceedings{jiang2026hachimi,
  title     = {{HACHIMI}: Scalable and Controllable Student Persona Generation via Orchestrated Agents},
  author    = {Jiang, Yilin and Tan, Fei and Yin, Xuanyu and Leng, Jing and Zhou, Aimin},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2026},
  year      = {2026}
}
```

## 许可

本项目以 [MIT 许可](LICENSE) 发布。
