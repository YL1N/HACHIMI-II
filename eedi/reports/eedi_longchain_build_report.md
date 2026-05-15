# EEDI 长链路实现报告

## 本次实现覆盖了什么

- 按 `eedi/重构.md` 把 `DialogueContext -> StudentContextProfile -> TutorMoveProfile -> InteractionState -> StateTransitionPrediction -> ConstraintBundle -> StudentTurnGeneration -> DynamicViolationCheck -> Optional One-Step Retry` 主链跑通。
- 所有核心 prompt 集中在 `eedi/src/prompts.py`。
- 生成阶段改成严格单步协议，只有最后一步允许输出最终 `student turn`。
- 每个样本的阶段对象和生成轨迹都会实时落到 `stage_traces.jsonl`。
- 加入了硬规则动态失真检查、边界样本 LLM 复核、一次局部重试。

## 这次修改改变了哪个对象或哪个环节

1. 把原来的简化 `student_model` 改成 `StudentContextProfile`，不再直接压成 low/medium/high 稳定人格标签。
2. 把原来的简化 `student_turn_state` 改成文档要求的 `InteractionState`。
3. 新增 `StateTransitionPrediction` 和 `ConstraintBundle`，避免从状态直接旁路到回复。
4. 把生成器改成单步协议 + 违例检查 + 一次重试。

## 理论依据

- `StudentContextProfile` 用 Bandura / Zimmerman / Pekrun 做描述性分析，用 ICAP 做原生参与层级。
- `TutorTurnProfile` 受 ZPD / scaffolding 约束。
- `InteractionState` 和 `StateTransitionPrediction` 体现第三人称状态解析与渐进转移。
- `DynamicViolationCheck` 聚焦三类失真：过快跃迁、错误路径断裂、成熟化过度。

## 怎么避免作弊

- generation path 只吃当前题、历史对话、当前 tutor turn、第三人称状态与转移、规则编译约束。
- 没有把 gold next student turn、官方 act/correctness/kcs/persona 标注带入生成链。
- 没有做题号特判、模板特判、目标指标回调。

## 输出位置

- 最近一次运行输出目录：`D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_block9_1000_20260515\constraint_no_specific_error_realization`
- 实时阶段轨迹：`stage_traces.jsonl`
- 最终预测：`predictions.jsonl` / `turn_level_predictions.csv`
- 聚合指标：`metrics.json`
