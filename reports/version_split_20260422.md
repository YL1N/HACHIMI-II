# XES / EEDI 版本拆分说明
这次拆分的目的只有一个：把旧版 XES 静态试卷方法和新版 EEDI 长链路交互方法彻底分开，降低耦合，避免以后继续在同一套入口和对象上硬拧。

## 现在的目录边界
- `xes/`
  - 保留原来的 XES 静态单题方法
  - 有自己的 `run_experiments.py`
  - 有自己的 `configs/`
  - 有自己的 `reports/`
  - 有自己的 `outputs/`
- `eedi/`
  - 新建的 EEDI 长链路版本
  - 有自己的 `run_eedi_experiments.py`
  - 有自己的 `src/`
  - 有自己的 `reports/`
  - 后续输出写到自己的 `outputs/`

## 明确不做的事
- 不做顶层兼容包装入口
- 不把顶层 `run_experiments.py` 改成转发到 `xes/` 或 `eedi/`
- 不让 `eedi/` import `xes/` 的核心模块
- 不把两个版本继续揉成一套共享运行链

## 这次已经完成的事
- 旧版实现已归到 `xes/`
- `xes/` 已补自己的默认配置文件
- `xes/` 已补自己的根因实验计划与历史报告副本
- `xes/` 已补自己的默认冻结题集与关键历史 `metrics.json`
- `eedi/` 已建独立最小链路：
  - 读取 EEDI 对话
  - 构建学生稳定特征
  - 解析当前 tutor 回合任务
  - 解析学生当前回合状态
  - 生成当前 student turn
  - 导出 turn-level 结果

## 后续工作原则
- 如果继续做 XES，只在 `xes/` 里改
- 如果继续做 EEDI，只在 `eedi/` 里改
- 除非你明确要求，否则不再尝试抽共享层
- 后续主线默认放在 `eedi/`
