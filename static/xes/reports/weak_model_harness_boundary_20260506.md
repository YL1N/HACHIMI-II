# 弱模型 Harness 边界（2026-05-06）

## 1. 当前原则

弱模型版本的目标不是让强模型在线替弱模型做题，而是：

> 先把学生画像和题目要求编译成结构化环境，再让弱模型自己在这个环境里作答。

所以当前边界是：

- 强模型可以做离线或上游编译
- 弱模型必须在线自己产出当前 student-item state 和最终答案

## 2. 强模型允许做什么

- 从历史作答和画像生成 `StudentModel`
- 从题面生成 `ProblemRequirementProfile`
- 把长文本压缩成结构化 card

## 3. 强模型不允许做什么

- 不允许在线直接判这题该对还是错
- 不允许在线直接替弱模型选最终答案
- 不允许把真实标签伪装成推断结果塞回链路

## 4. 弱模型当前必须做什么

- 在 `StudentState + TaskState` 条件下，自行产出 `StudentItemState`
- 在 `StudentItemState + ResponseSpace` 条件下，自行生成最终答案

## 5. 当前第一版对象

- `StudentState`
- `TaskState`
- `StudentItemState`
- `ResponseSpace`

这四个对象是弱模型在线链路的最小闭环。

## 6. 当前已跑通的最小链路

当前 smoke 已经跑通：

- 强模型构建 `StudentModel`
- 强模型构建 `ProblemRequirementProfile`
- harness 编译成 `StudentState` 与 `TaskState`
- 弱模型在线生成 `StudentItemState`
- 弱模型在线生成最终答案

这说明当前版本已经不是“强模型在线代替弱模型做决定，弱模型只说话”。

## 7. 当前还没完成的部分

这版仍然只是最小可运行链路，不是最终正式方案。

还缺：

1. 理论上更严格的属性体系与题目 Q-matrix
2. 更规范的错误类型体系
3. 更严格的边界检查与失败重试
4. 批量运行入口与正式评测
