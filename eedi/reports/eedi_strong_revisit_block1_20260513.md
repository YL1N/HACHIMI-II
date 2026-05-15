# EEDI strong harness 模块必要性 revisit：block1 报告（2026-05-13）

## 1. 这份报告回答什么问题

这份报告回答两个问题：

1. EEDI strong harness 是否也需要像 XES 一样做 revisit？
2. 在 **不破坏同一套元方法骨架** 的前提下，EEDI 当前 strong 主线里，哪些辅助层值得保留，哪些不值得动？

这里的“同一套元方法骨架”指的是：

> `可见历史 -> 第三人称状态层 -> 约束编译 -> 当前学生回合生成`

这次我们 revis​it 的不是“要不要第三人称状态层”，而是：

- `population calibration` 要不要保留；
- `ConstraintBundle` 当前是不是太紧；
- `违规审查 / retry` 这一层要不要保留。

---

## 2. 为什么这次 EEDI revisit 和 XES revisit 可以放在同一个元方法框架里

XES 那边的 revisit 最后告诉我们：

- 不要暴露 difficulty 信号；
- 默认 `ConstraintBundle` 太紧。

但 EEDI 不一定会得到同样结论。

这并不冲突。

因为真正要统一的不是每个数据集的最佳超参，而是方法结构：

- 都必须先做第三人称状态判断；
- 都必须把状态翻译成生成边界；
- 都必须在边界里生成学生回复。

所以：

> 如果 EEDI 最后发现 `population calibration` 应该保留、`ConstraintBundle` 不该放松，这仍然是同一种元方法，只是另一种任务下的局部最优实现不同。

---

## 3. 本轮 block1 怎么跑的

### 3.1 评测集

这次 block1 先不直接上 4334 全量，而是先用固定的 1000-task revisit 床：

- config：`D:\Study\sii\MathStudent\eedi\configs\run_strong_population_calibrated_test1000_20260511.json:1`
- generation 目标任务数：`1000`
- 并发：`32`
- detached eval：五个核心指标

这样做的目的很简单：

- 先看趋势；
- 先确认开关实现没问题；
- 先确认哪个方向值得上更贵的全量。

### 3.2 跑了哪些版本

这轮一共跑了 5 个版本：

| version | 改动 |
|---|---|
| `baseline_pc_default` | 当前 strong 基线 |
| `no_population_calibration` | 关闭 population calibration |
| `pc_loose_constraints` | 放松 `ConstraintBundle` |
| `pc_no_retry` | 关闭 violation 后的二次 retry |
| `pc_hard_violation_only` | 关闭 LLM violation review，只保留硬规则 |

批跑脚本：

- `D:\Study\sii\MathStudent\eedi\run_strong_revisit_1000_20260513.ps1:1`

汇总脚本：

- `D:\Study\sii\MathStudent\eedi\summarize_strong_revisit_1000.py:1`

结果根目录：

- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_1000_20260513`

---

## 4. 结果总表

> 注意：五个版本因为少量 generation failure，最终 detached eval 行数在 `953` 到 `956` 之间，不是完全同一批行。所以这轮结论是 **screening 级**，不是最终全量定版。

| version | consistency | same_knowledge | same_locus | same_mechanism | error_realization | retries | remaining_violations | failed_tasks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline_pc_default` | `0.5927` | `0.7671` | `0.6438` | `0.6575` | `0.6460` | `312` | `215` | `2` |
| `no_population_calibration` | `0.5889` | `0.6986` | `0.6438` | `0.6027` | `0.6293` | `342` | `255` | `1` |
| `pc_hard_violation_only` | `0.5763` | `0.7333` | `0.6000` | `0.6133` | `0.6696` | `70` | `51` | `2` |
| `pc_loose_constraints` | `0.5630` | `0.7222` | `0.6111` | `0.6389` | `0.6429` | `380` | `256` | `2` |
| `pc_no_retry` | `0.5507` | `0.7500` | `0.6184` | `0.7105` | `0.6909` | `0` | `348` | `4` |

汇总文件：

- `D:\Study\sii\MathStudent\eedi\outputs\eedi_strong_revisit_1000_20260513\summary.json:1`

---

## 5. 直接结论

## 5.1 当前 block1 里，基线仍然是最稳的版本

如果优先看我们最重视的指标：

- `consistency`
- `error_realization`

那么表面上看：

- `pc_no_retry` 的 `error_realization` 最高；
- `pc_hard_violation_only` 也把 `error_realization` 拉高了；
- 但 **`consistency` 最高的仍然是 `baseline_pc_default`**。

而且：

- `pc_no_retry` 的 `consistency` 掉到了 `0.5507`；
- `pc_loose_constraints` 的 `consistency` 也掉到了 `0.5630`；
- `pc_hard_violation_only` 也低于 baseline。

所以如果问：

> 当前 EEDI strong 主线里，这五个版本谁最适合作为默认版本？

这轮答案仍然是：

> **`baseline_pc_default` 仍然最稳。**

---

## 5.2 EEDI 上，population calibration 目前不能像 XES difficulty 信号那样直接拿掉

`no_population_calibration` 相比 baseline：

- `consistency`：`0.5889 < 0.5927`
- `same_knowledge`：`0.6986 < 0.7671`
- `same_locus`：持平
- `same_mechanism`：`0.6027 < 0.6575`
- `error_realization`：`0.6293 < 0.6460`

这说明至少在这轮 1000-task screening 上：

> `population calibration` 对 EEDI 不是一个可以轻易删掉的“多余先验层”。

这和 XES 的 difficulty 信号结论不同，但并不矛盾。

更准确地说：

- XES 里伤人的，是把题目难度直接暴露成强先验；
- EEDI 这里保留下来的，是围绕“类似 tutor move + 类似局部情境”的群体先验摘要；
- 它仍然在第三人称状态推断层里起作用，而不是直接控制下一句内容。

所以 EEDI 这里更像是在说：

> 群体先验摘要在长链路对话任务里暂时仍有信息价值。

---

## 5.3 当前 EEDI `ConstraintBundle` 没有出现 XES 那种“默认太紧”的证据

`pc_loose_constraints` 是这轮最重要的对照之一。

它本来是用来检查：

> EEDI 当前 strong 的约束是不是也像 XES 一样太紧。

结果是：

- `consistency` 从 `0.5927` 掉到 `0.5630`
- `same_knowledge` 从 `0.7671` 掉到 `0.7222`
- `same_locus` 从 `0.6438` 掉到 `0.6111`
- `same_mechanism` 也没变好
- `error_realization` 基本没赚到

这说明：

> 至少在 EEDI 这条链路上，当前 `ConstraintBundle` 还不能被简单归类为“写得太紧”。

也就是说：

- XES 上“放松约束更好”；
- EEDI 上这轮却是“放松约束更差”。

这正好支持我们现在想讲的那句话：

> 同一元方法可以在不同任务上有不同的局部最优实现。

这个说法也和我们前面一直在用的教育测评/学习理论是一致的：

- Assessment Triangle 强调先分清 latent cognition、可观察证据和解释链路，而不是直接把表面输出当能力本体；
- Evidence-Centered Design 强调先定义要推断的状态，再决定看什么证据、允许什么输出；
- ICAP 强调同样一段内容，不同参与方式对应的学习状态并不一样。

参考：

- National Academies, *Knowing What Students Know*: <https://nap.nationalacademies.org/read/10019/chapter/3>
- Evidence-Centered Design 综述：<https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.00853/full>
- ICAP framework: <https://icap.education.asu.edu/research/>

---

## 5.4 retry 层目前仍然值得保留

`pc_no_retry` 的现象很有意思：

- `same_mechanism = 0.7105`，五个版本里最高；
- `error_realization = 0.6909`，也是最高；
- 但 `consistency = 0.5507`，五个版本里最低；
- `remaining_violations = 348`，也是最高；
- `failed_tasks = 4`，工程稳定性最差。

这说明不 retry 的版本更容易把“错”直接说出来，但问题是：

- 它更容易在不该错的时候也错；
- 更容易把局部状态边界冲破；
- 于是总目标里最关键的 `consistency` 被明显拖垮。

所以这轮更合理的结论不是“retry 没用”，而是：

> retry 在 EEDI strong 里仍然是有价值的，它的主要作用不是抬高 `same_mechanism`，而是把输出重新压回预测状态边界，保住 `consistency`。

---

## 5.5 LLM violation review 目前也不能直接关

`pc_hard_violation_only` 的结果比 `pc_no_retry` 好一些，但仍然没有超过 baseline。

它的特征是：

- `consistency` 低于 baseline；
- `error_realization` 高于 baseline；
- `retries` 和 `remaining_violations` 明显更低。

这里要特别小心解释：

> `remaining_violations` 不能直接被理解成“这个版本更好”。

因为：

- baseline 用的是“硬规则 + LLM review”；
- `pc_hard_violation_only` 用的是“只看硬规则”；
- 两边的 violation 判定口径本身就变了。

所以更稳妥的解释是：

- 只保留硬规则，会让系统更少触发二次修正；
- 但它也会损失一部分细粒度状态对齐能力；
- 最终体现在 `consistency` 回落。

因此当前更合理的结论是：

> LLM violation review 目前仍有保留价值，至少不能在这轮证据下直接删掉。

---

## 6. 模块必要性分类（block1 版）

| 模块 | 当前结论 | 说明 |
|---|---|---|
| 第三人称状态链整体 | 必须保留 | 这轮没有碰它，因为它是元方法骨架 |
| `population calibration` | 当前应保留 | 关闭后 4 项核心指标下降，暂不支持删除 |
| `ConstraintBundle` | 必须保留 | 而且当前没有证据说明它默认过紧 |
| generation retry | 当前应保留 | 关闭后 `consistency` 明显下滑，失败和剩余违规上升 |
| LLM violation review | 当前偏保留 | 关闭后 `consistency` 回落，暂不支持只留硬规则 |

---

## 7. 这轮结果对“元方法”叙事意味着什么

这轮最重要的不是某个单项指标涨没涨，而是：

> EEDI 的 revisit 结论和 XES 不完全一样，但它仍然清楚地落在同一个元方法框架里。

更具体地说：

- XES 告诉我们：difficulty 信号不该暴露，约束太紧会伤主线；
- EEDI 告诉我们：群体校准目前还该保留，约束也不能随便放松，retry / review 层也还有价值。

所以最终能讲成一句话：

> **统一的是“第三人称状态推断 -> 约束编译 -> 受限生成”这套高层方法；不统一的是每个任务里哪些局部辅助层最优。**

这恰好更像一个元方法，而不是一个只能在单一数据集上成立的 prompt recipe。

---

## 8. 当前 block1 结论

如果只基于这轮 EEDI revisit block1：

1. strong baseline 仍然是当前最稳版本；
2. `population calibration` 目前不建议删；
3. 当前 `ConstraintBundle` 不建议按 XES 的结论直接放松；
4. `retry` 和 `LLM violation review` 暂时都不建议删。

所以 block1 结束后，EEDI 当前默认 strong 版本 **暂不改主线**。

---

## 9. 下一步怎么做

block1 结束后，真正值得继续的不是再反复折腾外围工程层，而是做字段级 revisit：

1. `StudentContextProfile`
   - 哪些心理分析字段真在后续起作用；
2. `TutorTurnProfile`
   - 哪些 tutor move 字段是必要的；
3. `InteractionState / StateTransitionPrediction`
   - 哪些状态标签是必须保留的；
4. `ErrorBlueprint`
   - 详细错误结构到底要细到哪一层。

也就是说，下一轮 revisit 的重点会从：

> “外围辅助层要不要保留”

转向：

> “第三人称状态层内部，哪些字段真的是有效结构，哪些只是解释性冗余。”
