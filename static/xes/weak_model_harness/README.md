# XES 弱模型 Harness

这个目录单独承载 **弱模型版本** 的 XES 静态学生模拟工作。

目的只有一个：

> 在不改动现有强模型 harness 的前提下，单独为“小模型/弱模型”搭一套更硬、更短、更结构化的模拟链路。

当前先放两类东西：

1. **模型探针**
   - 先确认某个小模型到底是“不会做题”，还是“会做但不会按要求输出”。
2. **后续弱模型 harness**
   - 后面新的学生画像压缩、题目需求压缩、状态判定、约束编译、短输出生成，都只放在这里。

当前已经进入 formal v2：

- `StudentState`
- `TaskState`
- `TaskSupportProfile`
- `EvidenceBundle`
- `CoachingCard`
- `ErrorCard`
- `StudentItemState`
- `ResponseSpace`

## 当前文件

- `configs/bailian_small_models.json`
  - 百炼小模型候选配置
- `run_small_model_probe.py`
  - 小模型能力/指令跟随区分探针
- `run_weak_student_benchmark.py`
  - 弱模型正式批量实验入口
- `src/support_profile.py`
  - 题目支持卡编译
- `src/compile_cards.py`
  - evidence / coaching / error / response 边界编译
- `src/weak_actor.py`
  - 弱模型在线状态判断与答案生成
- `src/validate.py`
  - 显式协议校验

## 当前判定原则

一个模型只有同时满足下面两点，才适合拿来做“弱模型 + harness”实验：

1. **裸做真实三年级数学题时，正确率明显不高**
2. **在不需要解题、只需要照着输出标准答案时，能稳定按格式输出**

也就是：

- 如果“给答案它都输出不利索”，那主要是 **指令跟随问题**
- 如果“给答案能输出对，但自己做题做不对”，那主要是 **能力问题**

只有第二种，才符合我们要的弱模型定义。
