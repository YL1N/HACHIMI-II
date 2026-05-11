# EEDI 目录说明
`eedi/` 是面向 EEDI 长链路学生交互的新工作区，这里不复用 `xes/` 的入口和核心对象。
当前最小主链是：
- 读取 EEDI 对话与题目元数据
- 从历史对话构建当前学生画像
- 解析当前 tutor 回合任务
- 解析学生当前交互状态
- 生成一个下一步 student turn
- 导出 turn-level 预测结果

当前默认官方评测只跑不依赖训练的 4 个指标：
- Cosine Similarity
- ROUGE-L
- Correctness via GPT judge
- Error Similarity via GPT judge

对应官方 eval 分组是：
- `sim-text`
- `sim-corr-errs`

下面 3 个需要额外 fine-tuned 模型的指标目前不再作为默认必跑项：
- `sim-acts`
- `sim-ks`
- `tutor-ppl`
