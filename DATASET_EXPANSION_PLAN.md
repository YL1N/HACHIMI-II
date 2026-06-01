# 多数据集实验扩展计划

## 1. 当前目录规则

后续所有数据集按模拟形态放置：

- `static/`：静态做题模拟
- `dynamic/`：动态交互模拟

已经完成迁移：

- `static/xes/`：XES 静态主验证集
- `dynamic/eedi/`：EEDI / QATD2k 动态主验证集

---

## 2. 待扩展数据集

| 模拟形态 | 学科 | 数据集 | 角色 |
| --- | --- | --- | --- |
| 静态做题模拟 | 数学 | XES3G5M | 静态主验证集 |
| 静态做题模拟 | 数学 | Eedi NeurIPS Education Challenge | 数学诊断题 / distractor / misconception 相关验证 |
| 静态做题模拟 | 数学 | EduData-Math | 对标 Agent4Edu 的静态补充集 |
| 动态交互模拟 | 数学 | Eedi Question-Anchored Tutoring Dialogues 2k / QATD2k | 动态主验证集 |
| 动态交互模拟 | 数学 | Khan Academy Tutoring Accuracy Dataset / CoMTA | 动态数学跨平台验证 |
| 静态做题模拟 | 物理 | EduData-Physics | 静态跨学科鲁棒性 |
| 动态交互模拟 | 非数学理科 / STEM | 待定 | 需要继续找公开可获取、非大学、有真实师生交互记录的数据 |

---

## 3. 新数据集落位原则

### 3.1 静态数据集

放到：

`static/<dataset_name>/`

适合的任务形态：

- 给定学生历史和当前题目；
- 只预测当前题目作答；
- 样本之间相对独立；
- 不需要维护多轮状态更新。

### 3.2 动态数据集

放到：

`dynamic/<dataset_name>/`

适合的任务形态：

- 给定当前轮之前的交互历史；
- 只预测当前下一步学生行为；
- 学生状态会随多轮交互变化；
- 需要处理 tutor / system / student 的回合关系。

---

## 4. 迁移时不能改变的方法骨架

无论新数据集放到 `static/` 还是 `dynamic/`，都必须保留元方法骨架：

`Context -> State -> Constraint -> Action`

也就是：

1. 先定义当前时点可见上下文；
2. 再做第三人称状态判断；
3. 再把状态翻译成生成边界；
4. 最后只生成当前一步学生行为。

不能因为换数据集就退回：

`Context -> Direct Answer`

---

## 5. 当前下一步

建议下一步按这个顺序补：

1. `static/eedi_neurips/`
2. `static/edudata_math/`
3. `dynamic/comta/`
4. `static/edudata_physics/`
5. `dynamic/<stem_dialogue_dataset>/`

这样可以先补齐数学静态，再补数学动态跨平台，最后做跨学科鲁棒性。
