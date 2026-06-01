# EEDI-static 原图直答实验报告（2026-05-25）

## 1. 实验目的

之前 EEDI-static 在 OCR 文本直答上效果很差。

本实验只回答一个问题：

> 如果不使用 OCR 文本，而是直接把原始题目图片发给多模态模型，模型能不能正常做题？

这不是学生模拟实验，而是数据可用性检查。

它用于判断：

- EEDI-static 低分主要来自模型能力不足；
- 还是来自 OCR 文本损坏、选项顺序混乱、视觉信息缺失。

## 2. 实验设置

- 数据集：EEDI-static clean 黄金题集
- 配置文件：`static/eedi-static/configs/eedi_static_common_test_676x265_text_only_clean_20260520.json`
- 题目数：265
- 输入：原始题目图片
- 不输入：OCR 文本、学生历史、学生画像、真实学生答案
- 输出：四选一答案
- 答案映射：A/B/C/D 分别映射为 1/2/3/4
- 模型端点：`qwen3.5-397b`
- 端点类型：OpenAI-compatible chat/completions
- 运行目录：`static/eedi-static/outputs/eedi_static_image_direct_solve/run_20260525_184724`

## 3. 端点检查

本轮先做了两个 smoke test：

1. 文本 chat completion 可用。
2. 图片 `image_url` base64 输入可用。

注意：

- 该端点默认会输出 reasoning。
- 调用时需要传入 `chat_template_kwargs={"enable_thinking": false}`。
- 否则短输出会被 reasoning 占满，正文答案可能为空。

## 4. 结果

| 版本 | 输入 | 题目数 | 正确数 | 准确率 |
|---|---:|---:|---:|---:|
| OCR 直答 | OCR 文本 | 265 | 100 | 0.3774 |
| 原图直答 | 原始图片 | 265 | 207 | 0.7811 |

原图直答比 OCR 直答高：

- 正确数：+107
- 准确率：+0.4038

## 5. 交叉对比

| OCR 是否答对 | 原图是否答对 | 题目数 |
|---|---|---:|
| 错 | 对 | 122 |
| 对 | 对 | 85 |
| 错 | 错 | 43 |
| 对 | 错 | 15 |

解释：

- 有 122 道题 OCR 文本直答错，但原图直答对。
- 这说明 OCR 文本路线确实损失了大量关键信息。
- 原图也有 58 道错题，说明题目本身仍有难度，但不是“一塌糊涂”的 OCR-only 状态。

## 6. 按难度分层

这里用训练集经验正确率做离线分层，只用于分析，不进入生成链路。

| 难度层 | 题目数 | 平均训练正确率 | 原图直答准确率 |
|---|---:|---:|---:|
| 困难 | 88 | 0.4072 | 0.6591 |
| 中等 | 88 | 0.5607 | 0.8295 |
| 简单 | 89 | 0.7178 | 0.8539 |

原图直答正确率和题目经验正确率的 Pearson 相关为 `0.2136`。

这说明图片直答结果大体符合“简单题更容易答对”的方向，但相关性不强。

## 7. 按学科主题

| 主题 | 题目数 | 原图直答准确率 |
|---|---:|---:|
| Number | 178 | 0.8483 |
| Algebra | 56 | 0.6786 |
| Geometry and Measure | 31 | 0.5806 |

几何题最低，符合预期：这类题更依赖图形读数、角度、位置关系和视觉细节。

## 8. 结论

本轮结论很明确：

> EEDI-static 之前的低分主要不是因为模型完全不会做数学题，而是 OCR 文本输入严重破坏了题目信息。

因此，如果继续做 EEDI-static 静态模拟，应当优先走原图输入路线，而不是 OCR 文本路线。

后续如果要把 EEDI-static 接入静态学生模拟元方法，应采用：

`学生历史 + 学生画像 + 第三人称状态判断 + 当前题目原图 + 受限学生作答`

而不是：

`学生历史 + 学生画像 + OCR 文本 + 受限学生作答`

## 9. 方法边界

本实验没有使用：

- 真实学生当前题作答；
- 当前题真实正确/错误标签；
- 题目经验正确率作为生成提示；
- 题目 ID 特判；
- 生成后改答案。

本实验使用真实答案只做离线评测。

所以它是一个数据输入质量检查，不是指标作弊。

## 10. 代码入口

- 脚本：`static/eedi-static/run_image_direct_solve.py`
- 核心模块：`static/eedi-static/src/image_direct_solve.py`
- 测试：`static/eedi-static/tests/test_image_direct_solve.py`

复现实验命令：

```powershell
$env:OPENAI_API_KEY="<INF_API_KEY>"
python static/eedi-static/run_image_direct_solve.py `
  --llm_base_url "https://cge8kkjh9jgqcmjqkgpdedqqaog8gbkb.openapi-qb-ai.sii.edu.cn/v1" `
  --llm_model qwen3.5-397b `
  --max_concurrency 16 `
  --task_retry_attempts 3 `
  --max_tokens 1024 `
  --output_root static/eedi-static/outputs/eedi_static_image_direct_solve
```
