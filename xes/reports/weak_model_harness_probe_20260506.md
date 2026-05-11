# 弱模型 Harness 探针结论（2026-05-06）

## 1. 这次做了什么

为了避免把“不会按要求输出”误判成“不会做题”，这次单独做了一个弱模型探针。

新目录：

- `D:\Study\sii\MathStudent\xes\weak_model_harness`

这个目录和现有强模型 harness 分开，后续弱模型版本都只在这里做。

## 2. 探针怎么判

每个模型都做三类测试：

1. **format copy**
   - 不给题目，只给标准答案
   - 要求模型只照抄答案
   - 这个高，说明最基本的输出格式没问题
2. **gold render**
   - 给真实题面，但同时直接告诉它标准答案
   - 要求模型只输出标准答案
   - 这个高，说明它在真实题面干扰下仍能按要求输出
3. **math solve**
   - 只给题目，让它自己做
   - 这个低，才说明主要是解题能力弱

所以我们要找的不是“输出乱”，而是：

> format copy / gold render 高，但 math solve 低

## 3. 当前实测结果

结果目录：

- `D:\Study\sii\MathStudent\xes\weak_model_harness\outputs\run_20260506_212817`

核心结果：

- `qwen3-0.6b`
  - format copy = 1.000
  - gold render = 0.875
  - math solve correct = 0.125
  - 结论：更像能力不足，不是单纯指令跟随差
- `qwen3-1.7b`
  - format copy = 0.875
  - gold render = 1.000
  - math solve correct = 0.250
  - 结论：更像能力不足，不是单纯指令跟随差
- `qwen2.5-3b-instruct`
  - format copy = 1.000
  - gold render = 0.625
  - math solve correct = 0.375
  - 结论：能力不足和指令跟随问题并存
- `qwen3-4b`
  - format copy = 1.000
  - gold render = 1.000
  - math solve correct = 0.500
  - 结论：更像能力不足，但已经没那么弱了

## 4. 当前推荐

如果目标是做“弱模型 + harness 帮助”主实验，当前推荐顺序是：

1. `qwen3-1.7b`
2. `qwen3-0.6b`

原因：

- 这两个模型已经证明不是单纯输出乱
- 它们确实本来就不太会做这些三年级数学题
- 其中 `qwen3-1.7b` 比 `qwen3-0.6b` 更可能在后续 harness 下保持基本稳定性

所以：

> `qwen3-1.7b` 适合作为弱模型主版本，`qwen3-0.6b` 适合作为更弱的补充版本。
