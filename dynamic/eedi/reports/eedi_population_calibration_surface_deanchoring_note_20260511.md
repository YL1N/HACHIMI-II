# EEDI population calibration 去表层锚定说明（2026-05-11）

## 这次改了什么

- `population_calibration_summary` 不再携带 `gold_student_turn`
- 不再携带 `response_style_tags`
- 不再携带 `top_response_families`
- 不再携带 `exemplar_snippets`

## 为什么这样改

目标很明确：

- 保留应该压缩的结构层先验：
  - `knowledge_type`
  - `error_locus`
  - `error_mechanism`
  - `codable_error_rate`
- 去掉不该被 few-shot 直接锁死的表层锚点：
  - 具体学生原句
  - 固定措辞
  - 固定犹豫方式
  - 固定局部反应路径模板

也就是说，few-shot 现在更严格地只服务于：

`third-person structural state inference`

而不服务于：

`surface imitation`

## 方法立场

这不是为了做结果补丁，而是为了维持方法边界：

- calibration 是群体先验，不是答案脚本
- calibration 是结构校准，不是表层模仿
- generation 只能吃压缩后的结构信息，不能吃原始 exemplar 句子

## 对强版和弱版的影响

- 强版：继续把 calibration 用在 `StudentContextProfile / InteractionState / StateTransition / ErrorBlueprint`
- 弱版：继续把 calibration 用在 `StudentContextProfile / StudentPrior / 编译层约束`
- 两边都减少了对“学生腔调”的隐式锚定

## 预期结果

更理想的方向应该是：

- `same_knowledge / same_locus / same_mechanism / error_realization` 仍然受益
- 表层表达多样性不要被过度压扁

