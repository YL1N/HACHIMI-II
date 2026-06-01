# EEDI 弱模型 Harness v2.1 报告（2026-05-09）

## 1. 这次改了什么

v2.1 只改一件关键事：

> 不再把强模型 `ErrorBlueprint` 直接喂给弱模型 packet。

现在是：

- `local_error_state` 决定这轮是否真的要走具体错误实现；
- `strong_error_blueprint` 只保留做分析对照；
- 弱模型看到的是弱侧的局部错误判断，而不是强侧预写好的错误落点。

这次升级的目的很直接：

- 降低“过度犯错”；
- 把 `consistency` 拉回来；
- 保留 `error_realization`。

---

## 2. 本次正式跑

- 运行目录：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_v21_commitment_first_20260509_fix1`
- 生成成功：`983`
- 生成失败：`17`
- detached eval 行数：`944`

---

## 3. 结果对比

顺序统一为：

`consistency / same_knowledge / same_locus / same_mechanism / error_realization`

| 版本 | consistency | same_knowledge | same_locus | same_mechanism | error_realization |
| --- | ---: | ---: | ---: | ---: | ---: |
| 强版 | 0.6679 | 0.7949 | 0.5897 | 0.5897 | 0.3514 |
| 弱版 v1 | 0.6142 | 0.7241 | 0.5517 | 0.6207 | 0.2613 |
| 弱版 v2 | 0.5669 | 0.7333 | 0.5667 | 0.6833 | 0.5714 |
| 弱版 v2.1 | 0.6069 | 0.7209 | 0.5116 | 0.6512 | 0.3839 |

---

## 4. 这次说明了什么

### 4.1 v2 的问题

v2 明显是“过度犯错”：

- `error_realization` 太高；
- `same_mechanism` 也被拉高；
- 但 `consistency` 掉得太多。

### 4.2 v2.1 的修正

v2.1 把强蓝图从 causal path 挪走后：

- `consistency` 回升；
- `error_realization` 回落；
- `same_mechanism` 仍然高于强版；
- 整体更像“有错但不乱错”。

### 4.3 现在的判断

v2.1 不是最终版，但比 v2 更平衡。

它说明：

- 不是弱模型不行；
- 也不是必须继续加错误；
- 真正要做的是把“是否该具体犯错”先卡住。

---

## 5. 下一步

后续如果继续改，重点应该放在：

1. 先更稳地判断这一轮**要不要**输出 codable math error；
2. 再决定具体的 Newman / Radatz 落点；
3. 不要再让强版错误蓝图直接控制 packet。

