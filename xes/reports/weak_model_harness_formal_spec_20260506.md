# 弱模型 Harness 正式方法规约（2026-05-06）

## 1. 目标

本方法的目标是：

> 让弱模型在一组学生画像条件下，生成的群体作答分布尽量逼近真实学生群体作答分布。

这里的“逼近”优先指：

1. 学生总正确率分布接近
2. 高中低差学生之间有区分度
3. 题目正确率序列与真实学生相关
4. 题目难度排序与真实学生相关

## 2. 方法边界

本方法不是：

- 强模型在线替弱模型决定答案
- 弱模型只负责说话
- 通过真实标签反推当前题该对该错

本方法要求：

- 强模型只做上游编译
- 弱模型在线自己产出 `StudentItemState`
- 弱模型在线自己生成最终答案

## 3. 理论对齐

### 3.1 Evidence-Centered Design

本方法按 ECD 划分为：

- `StudentState`
  - 学生在数学任务上的稳定能力表示
- `TaskState`
  - 题目对知识、形式与负担的要求表示
- `StudentItemState`
  - 学生面对当前题目的当前状态判断
- `ResponseSpace`
  - 该状态下允许的输出边界

### 3.2 认知负荷与支架原则

当前 harness 允许做的帮助是：

- 降低题面噪声
- 降低画像表征负担
- 统一输出空间

当前 harness 不允许做的帮助是：

- 直接给解题步骤
- 直接给正确路线
- 直接给这题该对该错

## 4. 当前正式对象

### 4.1 StudentState

字段：

- 年级
- 学业水平
- 算术流畅性
- 应用题迁移
- 多步稳定性
- 几何直觉
- 规律识别
- 选择题排除能力
- 填空精度
- 困难题坚持度
- 猜测倾向
- 置信校准
- 格式纪律
- 主要错误族

### 4.2 TaskState

字段：

- 题型
- 前置知识
- 操作复杂度
- 抽象层次
- 知识整合需求
- 表征转换需求
- 输出格式需求
- 可猜性
- 感知难度
- Q-matrix 属性列表（当前先用 prerequisite_knowledge 占位）

### 4.3 StudentItemState

字段：

- `reachability`
- `likely_outcome`
- `confidence_band`
- `explanation_cap`
- `primary_error_family`

### 4.4 ResponseSpace

字段：

- `answer_mode`
- `max_tokens`
- `response_style`
- `allowed_commitment`
- `allowed_error_families`

## 5. 当前正式链路

1. 强模型生成 `StudentModel`
2. 强模型生成 `ProblemRequirementProfile`
3. harness 编译为 `StudentState` 与 `TaskState`
4. 弱模型在线生成 `StudentItemState`
5. harness 检查 `StudentItemState` 是否越界
6. 弱模型在线生成最终答案
7. harness 检查答案输出是否越界
8. 用现有 benchmark 评测层计算指标

如果第 4 步或第 6 步越界：

- 允许一次显式协议纠正重试
- 若仍失败，则显式记录失败样本
- 不允许静默改写答案、静默补值或跳过不记

## 6. 当前已实现入口

- `D:\Study\sii\MathStudent\xes\weak_model_harness\run_weak_student_benchmark.py`

这是当前正式版批量入口。

## 7. 当前仍需继续完善

1. 更严格的课程标准属性体系
2. 真正人工/理论驱动的 Q-matrix
3. 更正式的错误类型表
4. 失败重试策略的进一步规范化
