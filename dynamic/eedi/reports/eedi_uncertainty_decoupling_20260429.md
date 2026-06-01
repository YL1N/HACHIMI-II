# EEDI 不确定性偏置修正

## 问题

旧版生成链把下面三件事绑得过紧：

1. 学生还没真正学会
2. 学生当前仍在错误路径上
3. 学生这一轮必须表现得很犹豫、很困惑、很像在求确认

这会带来一个直接后果：

- 模型容易把“明确的学生错误”生成成
  - 半确认的正确说法
  - 泛化困惑
  - 低承诺 help-seeking

于是很多样本根本进不了“模型也犯错、学生也犯错”的 error 比较集合。

## 修正原则

这次修正只做一件事：

> 把“错误连续性”和“不确定表达”拆开。

也就是：

- 允许学生继续错，但说得比较直接。
- 不再把“还在错误路径上”默认实现成“必须带明显犹豫口气”。
- 只在局部证据支持时，才保留显式困惑、求确认、求帮助。

## 具体改动

### 1. 状态 prompt 改口径

在 `InteractionState` 和 `StateTransition` prompt 里显式加入：

- 错误不等于 tentative
- 学生可以错误但局部上说得很肯定
- 只有当历史和 tutor move 支持时，才预测显式 uncertainty / clarification / help-seeking

### 2. 约束编译改口径

旧逻辑里：

- `commitment != committed`
- 或 `no_uptake / surface_uptake`

就会大面积触发 `must_preserve_local_confusion`

新版改成更窄：

- 只有 `attempt_readiness == not_ready`
- 且 help-seeking 的局部状态支持

才保留这个约束。

### 3. 直接作答不再被 committed 独占

旧逻辑把 `allow_direct_answer` 绑在：

- `commitment == committed`

这会错误压制“带错误但直接”的学生回答。

新版改成：

- 只要已经 ready to attempt，且不是 avoidant
- 就允许直接给出本轮答案或本轮局部数学主张

### 4. retry 不再强制打回 tentative

旧版 `over_fast_transition` retry 会把回复重新压回 `tentative`。

新版只限制：

- 不要突然变成 polished mastery

但不再默认要求加重犹豫语气。

## 预期效果

这次修正的目标不是让模型“更自信”，而是让模型：

- 更容易把错误明确说出来
- 更少退化成泛化困惑
- 更少把 tutor 已经局部推进后的学生 turn 写成“半确认的正确说法”

换句话说，目标是提升：

- error realization

而不是单纯提升表面确定性。
